#!/usr/bin/env python3
"""Cyclic dispatch through unchanged APF; uses Isaac world pose for localization."""
import argparse
import math
import time
import signal
import uuid
from collections import OrderedDict
from warehouse_routes import STARTS, mission, sample_polyline, distance, segment_distance, correction, yaw, freshness_issues, match_pose_stamp


def make_cycle_node(args):
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from geometry_msgs.msg import TransformStamped
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import Bool, String
    from tf2_ros import TransformBroadcaster, StaticTransformBroadcaster
    from multibot_interfaces.srv import SetGoal

    class Cycles(Node):
        def __init__(self):
            super().__init__('warehouse_cycles',parameter_overrides=[rclpy.parameter.Parameter('use_sim_time',value=True)])
            self.br=TransformBroadcaster(self)
            self.root_br=StaticTransformBroadcaster(self)
            roots=[]
            for i in range(1,7):
                t=TransformStamped();t.header.frame_id='warehouse';t.child_frame_id=f'robot{i}/map'
                t.transform.rotation.w=1.0;roots.append(t)
            self.root_br.sendTransform(roots)
            self.world={};self.scans={};self.seen={};self.match_skew={};self.pairs={i:({}, {}) for i in range(1,7)}
            self.gates={i:self.create_publisher(Bool,f'/robot{i}/motion_enabled',10) for i in range(1,7)}
            self.client=self.create_client(SetGoal,'/multimode_controller/set_goal')
            self.groups=[{'robots':[1,2,3],'idx':0},{'robots':[4,5,6],'idx':0}]
            self.active={};self.started=False;self.fault=None;self.started_at=time.monotonic()
            self.last_sim=None;self.last_sim_wall=time.monotonic();self.tf_seen_at={};self.ready_since=None;self.stale_since=None;self.stale_description=None;self.resume_after=0.0
            self.service_started={};self.subs=[]
            self.run_id=uuid.uuid4().hex[:12]
            self.loads={i:False for i in range(1,7)}
            self.deliveries={'assembly':0,'packing':0};self.completed={i:0 for i in range(1,7)}
            self.factory_pub=self.create_publisher(String,'/warehouse/factory_state',10)
            self.factory_state_at=0.;self.factory_alive=False;self.factory_heartbeat_at=0.
            self.factory_sub=self.create_subscription(Bool,'/warehouse/factory_heartbeat',self.factory_heartbeat,10)
            for i in range(1,7):
                self.subs.append(self.create_subscription(Odometry,f'/robot{i}/warehouse_pose',lambda m,i=i:self.pose(i,0,m),qos_profile_sensor_data))
                self.subs.append(self.create_subscription(Odometry,f'/robot{i}/odom',lambda m,i=i:self.pose(i,1,m),qos_profile_sensor_data))
                self.subs.append(self.create_subscription(LaserScan,f'/robot{i}/scan',lambda m,i=i:self.scan(i,m),qos_profile_sensor_data))
            # Wall timer keeps the stop gate alive even when /clock is paused.
            from rclpy.clock import Clock, ClockType
            self.create_timer(.05,self.tick,clock=Clock(clock_type=ClockType.STEADY_TIME))
            self.get_logger().info('Waiting for 6 world poses + odom + scan, reset to original spawns; no SLAM TF in this mode')

        def factory_heartbeat(self,msg):
            self.factory_alive=msg.data;self.factory_heartbeat_at=time.monotonic()

        def publish_factory(self,force=False):
            if getattr(self,'factory_pub',None) is None:return
            now=time.monotonic()
            if not force and now-self.factory_state_at<.2:return
            import json
            robots={}
            for i in range(1,7):
                state=self.active.get(i)
                phase=mission(i)[state['phase']][0] if state is not None else 'parked'
                robots[str(i)]={'loaded':self.loads[i],'phase':phase,'active':state is not None,
                                'completed':self.completed[i],
                                'cycle':self.completed[i]+1 if state is not None else self.completed[i],
                                'at_station':bool(state and state['until']),
                                'destination':'assembly' if i<=3 else 'packing'}
            message={'version':1,'sim_time':self.get_clock().now().nanoseconds*1e-9,
                     'run_id':getattr(self,'run_id','legacy'),
                     'running':self.started and self.fault is None,
                     'held':self.stale_since is not None or getattr(self,'clock_paused',False),
                     'fault':self.fault,'robots':robots,'deliveries':self.deliveries}
            self.factory_pub.publish(String(data=json.dumps(message)))
            self.factory_state_at=now

        def scan(self,i,msg):
            now=time.monotonic()
            stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
            self.scans[i]=now
            self.seen[i,'scan']=(stamp,now)

        def pose(self,i,kind,msg):
            v=msg.pose.pose
            values=(v.position.x,v.position.y,v.position.z,v.orientation.x,v.orientation.y,v.orientation.z,v.orientation.w)
            if not all(math.isfinite(value) for value in values):
                self.stop(f'robot{i}: invalid pose');return
            stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
            cache=self.pairs[i][kind];cache[stamp]=msg
            while len(cache)>100:cache.pop(next(iter(cache)))
            stream='world' if kind==0 else 'odom'
            previous=self.seen.get((i,stream))
            if previous is None or stamp>previous[0]:
                self.seen[i,stream]=(stamp,time.monotonic())
            if kind==0 and (i not in self.world or stamp>self.world[i][2]):
                v=msg.pose.pose
                self.world[i]=((v.position.x,v.position.y,yaw(v.orientation)),time.monotonic(),stamp)
            other_cache=self.pairs[i][1-kind]
            matched=match_pose_stamp(stamp,other_cache,int(getattr(args,'pair_slop',.02)*1e9))
            if other_cache:self.match_skew[i]=min(abs(key-stamp) for key in other_cache)*1e-9
            if matched is None:return
            other=other_cache[matched]
            wm,om=(msg,other) if kind==0 else (other,msg)
            world_stamp=wm.header.stamp.sec*10**9+wm.header.stamp.nanosec
            previous_pair=self.seen.get((i,'pair'))
            if previous_pair is not None and world_stamp<=previous_pair[0]:return
            w,o=wm.pose.pose,om.pose.pose
            tx,ty,a=correction((w.position.x,w.position.y,yaw(w.orientation)),(o.position.x,o.position.y,yaw(o.orientation)))
            tf=TransformStamped();tf.header.stamp=wm.header.stamp
            tf.header.frame_id=f'robot{i}/map';tf.child_frame_id=f'robot{i}/odom'
            tf.transform.translation.x=tx;tf.transform.translation.y=ty
            tf.transform.translation.z=w.position.z-o.position.z
            tf.transform.rotation.z=math.sin(a/2);tf.transform.rotation.w=math.cos(a/2)
            self.br.sendTransform(tf);self.tf_seen_at[i]=time.monotonic()
            self.seen[i,'pair']=(world_stamp,time.monotonic())

        def stop(self,reason):
            if self.fault is None:self.get_logger().error(reason+'; ALL ROBOTS STOPPED. Ctrl+C, reset scene and restart.')
            self.fault=reason
            self.allowed=set()

        def begin(self,group):
            i=group['robots'][group['idx']]
            self.active[i]={'group':group,'phase':0,'points':None,'index':1,'future':None,'until':0,'goal':None,'sent_at':0,'may_move':False,'best':float('inf'),'last_progress':0}
            self.phase(i)

        def phase(self,i):
            state=self.active[i];name,points=mission(i)[state['phase']]
            state['points']=sample_polyline(points);state['index']=1;state['until']=0
            state['future']=None;state['goal']=None;state['may_move']=False;state['best']=float('inf');state['last_progress']=self.get_clock().now().nanoseconds*1e-9
            self.get_logger().info(f'robot{i}: {name}, destination={points[-1]}')

        def gates_off(self):
            for pub in self.gates.values():pub.publish(Bool(data=False))

        def tick(self):
            self.allowed=set()
            try:
                self.dispatch()
            except Exception as exc:
                self.stop(f'Dispatch error: {exc}')
            finally:
                for i,pub in self.gates.items():
                    pub.publish(Bool(data=i in self.allowed))
                self.publish_factory()

        def dispatch(self):
            wall=time.monotonic();sim=self.get_clock().now().nanoseconds*1e-9
            if self.last_sim is not None and sim<self.last_sim-0.05:
                self.stop('Simulation clock reset during a cycle')
            if self.last_sim is None or sim>self.last_sim+1e-6:self.last_sim_wall=wall
            self.last_sim=sim
            if self.fault:return
            # A paused/stalled simulation closes gates without latching a sensor fault.
            if wall-self.last_sim_wall>.5:
                if not getattr(self,'clock_paused',False):
                    self.get_logger().warning('Simulation clock not advancing; gates closed (waiting for Play/frames)')
                self.clock_paused=True
                self.stale_since=None;self.stale_description=None;self.ready_since=None
                if not self.started:self.started_at=wall
                return
            if getattr(self,'clock_paused',False):
                self.clock_paused=False
                self.get_logger().info('Simulation clock resumed; checking streams')
                for state in self.active.values():state['last_progress']=sim
            issues=freshness_issues(self.seen,sim,wall,
                                    getattr(args,'data_timeout',.7),getattr(args,'wall_timeout',3.0))
            if getattr(args,'require_factory',False) and (not self.factory_alive or wall-self.factory_heartbeat_at>3.):
                issues.append('factory driver heartbeat missing/unhealthy')
            ready=not issues
            if not self.started:
                if not ready or not self.client.service_is_ready():
                    if wall-self.started_at>30:
                        self.stop('Startup incomplete: '+ ('; '.join(issues[:8]) if issues else 'APF service unavailable'))
                    return
                if self.ready_since is None:self.ready_since=wall
                if wall-self.ready_since<2:return
                if any(distance(self.world[i][0],STARTS[i-1])>.8 for i in range(1,7)):
                    self.stop('Robots are not at original parking positions; Stop then Play/reset in Isaac');return
                self.started=True
                for group in self.groups:self.begin(group)
            elif not ready:
                description='; '.join(issues[:8])
                if self.stale_since is None:
                    self.stale_since=wall
                    self.get_logger().warning('DATA HOLD (gates closed): '+description)
                    self.stale_description=description
                if wall-self.stale_since>=getattr(args,'recovery_timeout',3.0):
                    skew=', '.join(f'robot{i}={v*1000:.1f}ms' for i,v in sorted(self.match_skew.items()))
                    self.stop('Persistent stale data: '+description+'; nearest world/odom skew: '+skew)
                return
            if self.stale_since is not None:
                self.stale_since=None;self.stale_description=None;self.resume_after=wall+.3
                for state in self.active.values():state['last_progress']=sim
                self.get_logger().info('Data recovered; checking fresh streams before resuming')
            if wall<self.resume_after:return
            for i,state in list(self.active.items()):
                pose=self.world[i][0]
                points=state['points'];idx=state['index']
                if state['until']:
                    if sim<state['until']:continue
                    phase=mission(i)[state['phase']][0]
                    if phase=='pickup':
                        if hasattr(self,'loads'):self.loads[i]=True
                    elif phase=='drop':
                        if hasattr(self,'loads'):
                            self.loads[i]=False
                            self.deliveries['assembly' if i<=3 else 'packing']+=1
                    state['phase']+=1
                    if state['phase']==3:
                        if hasattr(self,'completed'):self.completed[i]+=1
                        group=state['group'];del self.active[i]
                        group['idx']=(group['idx']+1)%3
                        self.get_logger().info(f'robot{i}: cycle done, next robot')
                        self.begin(group);continue
                    self.phase(i);continue
                if segment_distance(pose,points[idx-1],points[idx])>.75:
                    self.stop(f'robot{i} left its corridor by >0.75 m');return
                # Halt on a very close neighbor. Other group and parked robots have priority.
                if any(j!=i and distance(pose,self.world[j][0])<2.0 for j in range(1,7)):
                    self.stop(f'robot{i}: robot separation below 2 m');return
                if state['may_move']:self.allowed.add(i)
                future=state['future']
                if future is not None:
                    if not future.done():
                        if wall-state['sent_at']>5:self.stop(f'robot{i}: APF service timeout')
                        continue
                    try:
                        reply=future.result()
                        if not reply.success:self.stop(f'robot{i}: APF rejected goal: {reply.message}');return
                    except Exception as exc:self.stop(f'APF service failed: {exc}');return
                    state['future']=None;state['goal']=idx;state['may_move']=True
                if distance(pose,points[idx])<(.16 if idx==len(points)-1 else .45):
                    if idx==len(points)-1:
                        state['until']=sim+max(.05,args.dwell)
                        self.allowed.discard(i)
                        self.get_logger().info(f'robot{i}: station reached; dwell {args.dwell}s')
                        continue
                    state['index']+=1;state['goal']=None
                    continue
                if state['goal']==idx:
                    gap=distance(pose,points[idx])
                    if gap<state['best']-.05:state['best']=gap;state['last_progress']=sim
                    elif sim-state['last_progress']>25:
                        self.stop(f'robot{i}: no progress for 25 simulation seconds');return
                if state['goal']!=idx:
                    request=SetGoal.Request();request.robot_namespace=f'robot{i}'
                    request.x,request.y=map(float,points[idx])
                    state['future']=self.client.call_async(request);state['sent_at']=wall;state['best']=float('inf');state['last_progress']=sim
                    continue
                self.allowed.add(i)

    return Cycles


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',action='store_true')
    p.add_argument('--require-factory',action='store_true',help='Require factory animation driver heartbeat')
    p.add_argument('--dwell',type=float,default=3.0)
    p.add_argument('--data-timeout',type=float,default=.7,help='Max source stamp age, simulation seconds')
    p.add_argument('--wall-timeout',type=float,default=3.,help='Max receive silence, real seconds')
    p.add_argument('--recovery-timeout',type=float,default=3.,help='Hold before latching persistent data failure')
    p.add_argument('--pair-slop',type=float,default=.02,help='Max world/odom timestamp mismatch, simulation seconds')
    args=p.parse_args()
    if args.plan:
        for i in range(1,7):
            print(f'robot{i}: '+ ' -> '.join(f'{name}{points[-1]}' for name,points in mission(i)))
        return
    if args.dwell<0 or min(args.data_timeout,args.wall_timeout,args.recovery_timeout)<=0 or not 0<=args.pair_slop<=.05:
        p.error('dwell>=0; timeouts>0; 0<=pair-slop<=0.05')
    import rclpy
    Cycles=make_cycle_node(args)

    from rclpy.signals import SignalHandlerOptions
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    def terminate(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    node=Cycles()
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:
        node.fault='shutdown'
        node.publish_factory(force=True)
        for _ in range(5):
            node.gates_off()
            rclpy.spin_once(node,timeout_sec=.02)
        node.destroy_node();rclpy.shutdown()


if __name__=='__main__':main()
