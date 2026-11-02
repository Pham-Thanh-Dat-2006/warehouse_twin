"""Read-only dashboard integration with actual ROS DDS on an isolated domain."""
import os,sys,json,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
from model import Warehouse
from ros_source import RosSource
import rclpy
from rclpy.node import Node
from rclpy.context import Context
from rclpy.signals import SignalHandlerOptions
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String,Bool

assert int(os.environ.get('ROS_DOMAIN_ID','0'))!=0,'Use an isolated domain'
s=Warehouse(':memory:');source=RosSource(s)
c=Context();rclpy.init(args=[],context=c,signal_handler_options=SignalHandlerOptions.NO)
peer=Node('warehouse_web_test_publisher',context=c)
try:
    pub=peer.create_publisher(Odometry,'/robot1/warehouse_pose',10)
    scan=peer.create_publisher(LaserScan,'/robot1/scan',10)
    clock=peer.create_publisher(Clock,'/clock',10)
    master=peer.create_publisher(String,'/warehouse/factory_state',10)
    telemetry=peer.create_publisher(String,'/warehouse/factory_telemetry',10)
    heartbeat=peer.create_publisher(Bool,'/warehouse/factory_heartbeat',10)
    pose=Odometry();pose.header.stamp.sec=100;pose.pose.pose.position.x=12.;pose.pose.pose.position.y=33.;pose.pose.pose.orientation.w=1.
    tick=Clock();tick.clock.sec=100
    state={'version':1,'run_id':'dds-test','running':True,'held':False,'robots':{'1':{'active':True,'phase':'pickup','loaded':False,'cycle':1}}}
    prod={'version':1,'factory_time':22.,'physics_steps':1320,'running':True,'arm_cycles':12,'belt_outputs':4,'belts':[],'arms':[]}
    deadline=time.monotonic()+8.
    while time.monotonic()<deadline:
        pub.publish(pose);scan.publish(LaserScan());clock.publish(tick)
        master.publish(String(data=json.dumps(state)));telemetry.publish(String(data=json.dumps(prod)));heartbeat.publish(Bool(data=True))
        time.sleep(.05)
        snapshot=s.snapshot()
        if snapshot['robots'][0]['online'] and all(snapshot['connection'].values()):break
    assert snapshot['robots'][0]['pose']['x']==12.,snapshot['robots'][0]
    assert snapshot['production']['belt_outputs']==4,snapshot
    assert snapshot['master']['run_id']=='dds-test'
    assert snapshot['sim_time']==100.
    assert snapshot['robots'][0]['scan_online']
    published=source.node.get_publisher_names_and_types_by_node('warehouse_web_monitor','/')
    assert not any('cmd_vel' in name or 'joint_command' in name or 'motion_enabled' in name for name,_ in published)
    print('PASS: real ROS pose + scan + clock + dispatcher + production + heartbeat reach the web model; monitor publishes no motor commands')
finally:
    source.close();peer.destroy_node();c.shutdown();s.close()
