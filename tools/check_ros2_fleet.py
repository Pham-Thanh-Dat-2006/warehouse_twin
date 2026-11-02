#!/usr/bin/env python3
"""Read-only ROS 2 check: odom coordinates and TF for all Ridgeback robots.
Run with /usr/bin/python3 after sourcing ROS 2 Humble. Publishes no commands.
"""
import argparse
import math
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=8.0)
    parser.add_argument('--require-map', action='store_true', help='Wait for map->base TF from SLAM')
    parser.add_argument('--check-start', action='store_true', help='Check map poses against warehouse spawn positions; before routes only')
    args = parser.parse_args()
    if args.check_start:
        args.require_map = True
    if args.seconds <= 0:
        parser.error('--seconds must be positive')

    import rclpy
    from rclpy.node import Node
    from rclpy.time import Time
    from rclpy.qos import qos_profile_sensor_data
    from nav_msgs.msg import Odometry
    from tf2_ros import Buffer, TransformListener

    rclpy.init()
    node = Node('check_ros2_fleet')
    buffer = Buffer()
    listener = TransformListener(buffer, node, spin_thread=False)
    samples = {}
    world_samples = {}
    subscriptions = []
    for i in range(1, 7):
        subscriptions.append(node.create_subscription(
            Odometry, f'/robot{i}/warehouse_pose',
            lambda msg, i=i: world_samples.__setitem__(i, msg), qos_profile_sensor_data))
        subscriptions.append(node.create_subscription(
            Odometry, f'/robot{i}/odom',
            lambda msg, i=i: samples.__setitem__(i, msg), qos_profile_sensor_data))

    def tf(parent, child):
        if not buffer.can_transform(parent, child, Time()):
            return None
        return buffer.lookup_transform(parent, child, Time())

    start = time.monotonic()
    failed = False
    try:
        while rclpy.ok() and time.monotonic() - start < args.seconds:
            rclpy.spin_once(node, timeout_sec=0.1)
            ready = all(i in samples and
                        tf(f'robot{i}/odom', f'robot{i}/base_link') and
                        tf(f'robot{i}/base_link', f'robot{i}/rplidar_link')
                        and (not args.require_map or tf(f'robot{i}/map', f'robot{i}/base_link'))
                        for i in range(1, 7))
            if ready and time.monotonic() - start > 1:
                break
        print('robot | odom pose (x,y,yaw_deg) | TF odom->base | TF base->lidar | map pose', flush=True)
        starts = [(10,33),(10,38.2),(10,43.4),(110,35.6),(110,40.8),(110,46)]
        for i in range(1, 7):
            ns = f'robot{i}'
            msg = samples.get(i)
            odom_tf = tf(f'{ns}/odom', f'{ns}/base_link')
            lidar_tf = tf(f'{ns}/base_link', f'{ns}/rplidar_link')
            map_tf = tf(f'{ns}/map', f'{ns}/base_link')
            pose = 'MISSING'
            if msg:
                p, q = msg.pose.pose.position, msg.pose.pose.orientation
                yaw = math.degrees(math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z)))
                pose = f'({p.x:.2f}, {p.y:.2f}, {yaw:.1f})'
            map_pose = 'chua co (binh thuong neu chua chay SLAM)'
            if map_tf:
                p = map_tf.transform.translation
                map_pose = f'({p.x:.2f}, {p.y:.2f})'
                if args.check_start:
                    x0,y0 = starts[i-1]
                    error = math.hypot(p.x-x0,p.y-y0)
                    map_pose += f' start_error={error:.2f}m'
                    failed |= error > 1.0
            if i in world_samples:
                wp=world_samples[i].pose.pose.position
                map_pose += f' world=({wp.x:.2f},{wp.y:.2f})'
                if map_tf:
                    delta=math.hypot(map_tf.transform.translation.x-wp.x,map_tf.transform.translation.y-wp.y)
                    map_pose += f' map/world_diff={delta:.2f}m'
            print(f'{ns} | {pose} | {"OK" if odom_tf else "MISSING"} | '
                  f'{"OK" if lidar_tf else "MISSING"} | {map_pose}')
            failed |= not (msg and odom_tf and lidar_tf) or (args.require_map and not map_tf)
        print('PASS: du lieu/TF' + (' va toa do kho' if args.check_start else '') + ' cua ca 6 xe'
              if not failed else 'FAIL: thieu TF hoac sai toa do kho; chua gui route')
    finally:
        listener.unregister()
        node.destroy_node()
        rclpy.shutdown()
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
