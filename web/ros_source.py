"""Read-only ROS input for the local dashboard; publishes no topics/services."""
import json
import math
import threading


class RosSource:
    def __init__(self, store):
        import rclpy
        from rclpy.context import Context
        from rclpy.node import Node
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.signals import SignalHandlerOptions
        from rclpy.qos import qos_profile_sensor_data
        from nav_msgs.msg import Odometry
        from sensor_msgs.msg import LaserScan
        from rosgraph_msgs.msg import Clock
        from std_msgs.msg import String, Bool
        self.rclpy=rclpy;self.context=Context()
        rclpy.init(args=[],context=self.context,signal_handler_options=SignalHandlerOptions.NO)
        self.node=Node('warehouse_web_monitor',context=self.context)
        self.executor=SingleThreadedExecutor(context=self.context);self.executor.add_node(self.node)
        self.stop=threading.Event();self.store=store;self.subs=[]
        def pose(msg,i):
            p=msg.pose.pose.position;q=msg.pose.pose.orientation
            a=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
            stamp=msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9
            store.pose(i,p.x,p.y,a,stamp)
        def packet(msg, callback):
            try: callback(json.loads(msg.data))
            except (ValueError,TypeError,KeyError) as exc:
                store.ros_error='Dữ liệu ROS không hợp lệ: '+str(exc)
        for i in range(1,7):
            self.subs.append(self.node.create_subscription(Odometry,f'/robot{i}/warehouse_pose',lambda m,i=i:pose(m,i),qos_profile_sensor_data))
            self.subs.append(self.node.create_subscription(LaserScan,f'/robot{i}/scan',lambda m,i=i:store.scan(i),qos_profile_sensor_data))
        self.subs.append(self.node.create_subscription(Clock,'/clock',lambda m:store.update_clock(m.clock.sec+m.clock.nanosec*1e-9),qos_profile_sensor_data))
        self.subs.append(self.node.create_subscription(String,'/warehouse/factory_state',lambda m:packet(m,store.factory_state),10))
        self.subs.append(self.node.create_subscription(String,'/warehouse/factory_telemetry',lambda m:packet(m,store.factory_telemetry),10))
        self.subs.append(self.node.create_subscription(Bool,'/warehouse/factory_heartbeat',lambda m:store.factory_heartbeat(m.data),10))
        self.thread=threading.Thread(target=self.run,daemon=True,name='warehouse-web-ros');self.thread.start()

    def run(self):
        try:
            while not self.stop.is_set():self.executor.spin_once(timeout_sec=.1)
        except Exception as exc:
            if not self.stop.is_set():self.store.ros_error='ROS bị ngắt: '+str(exc)

    def close(self):
        self.stop.set();self.thread.join(timeout=2.)
        self.executor.shutdown(timeout_sec=.2);self.node.destroy_node()
        if self.context.ok():self.context.shutdown()
