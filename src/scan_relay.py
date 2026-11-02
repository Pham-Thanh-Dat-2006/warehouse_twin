#!/usr/bin/env python3
"""Relay raw scan; optional rotated frame compensates the legacy APF +pi/2."""
import argparse
import math
import copy


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ns',nargs='?',default='robot1')
    parser.add_argument('--apf-alignment',action='store_true')
    args=parser.parse_args()
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import LaserScan
    from geometry_msgs.msg import TransformStamped
    from tf2_ros import StaticTransformBroadcaster
    class Relay(Node):
        def __init__(self):
            super().__init__('scan_relay_'+args.ns)
            self.pub=self.create_publisher(LaserScan,f'/{args.ns}/scan_fixed',10)
            self.create_subscription(LaserScan,f'/{args.ns}/scan',self.cb,qos_profile_sensor_data)
            if args.apf_alignment:
                self.br=StaticTransformBroadcaster(self)
                t=TransformStamped();t.header.stamp=self.get_clock().now().to_msg()
                t.header.frame_id=f'{args.ns}/rplidar_link';t.child_frame_id=f'{args.ns}/apf_lidar'
                t.transform.rotation.z=math.sin(math.pi/4);t.transform.rotation.w=math.cos(math.pi/4)
                self.br.sendTransform(t)
        def cb(self,msg):
            if args.apf_alignment:
                msg=copy.deepcopy(msg)
                msg.angle_min-=math.pi/2;msg.angle_max-=math.pi/2
                msg.header.frame_id=f'{args.ns}/apf_lidar'
            self.pub.publish(msg)
    rclpy.init();node=Relay()
    try:rclpy.spin(node)
    except (KeyboardInterrupt,ExternalShutdownException):pass
    except Exception:
        # SIGTERM may invalidate the context while spin is creating a wait set.
        # Preserve normal runtime errors; only a shutdown context ends quietly.
        if rclpy.ok():raise
    finally:node.destroy_node();rclpy.try_shutdown()


if __name__=='__main__':main()
