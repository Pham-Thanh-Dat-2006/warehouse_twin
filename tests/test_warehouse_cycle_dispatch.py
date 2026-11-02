"""Offline tests of the dispatcher only; no DDS nodes or motor commands created."""
import time
import json
from types import SimpleNamespace as S
from warehouse_cycles import make_cycle_node
from warehouse_routes import STARTS,distance,freshness_issues,match_pose_stamp

Cycles=make_cycle_node(S(dwell=3.0))
class Future:
    def done(self):return True
    def result(self):return S(success=True,message='ok')


def fixture(cls=Cycles):
    n=object.__new__(cls)
    clock=[100.];logs=[];goals=[]
    n.get_clock=lambda:S(now=lambda:S(nanoseconds=int(clock[0]*1e9)))
    n.get_logger=lambda:S(info=lambda text:logs.append(text),error=lambda text:logs.append(text),warning=lambda text:logs.append(text))
    n.client=S(service_is_ready=lambda:True,call_async=lambda r:(goals.append(r) or Future()))
    n.groups=[{'robots':[1,2,3],'idx':0},{'robots':[4,5,6],'idx':0}]
    n.world={i:((x,y,0),time.monotonic(),0) for i,(x,y) in enumerate(STARTS,1)}
    n.scans={i:time.monotonic() for i in range(1,7)}
    n.tf_seen_at=dict(n.scans);n.active={};n.started=False;n.fault=None
    n.seen={(i,stream):(int(clock[0]*1e9),time.monotonic()) for i in range(1,7)
            for stream in ('world','odom','pair','scan')}
    n.stale_since=None;n.stale_description=None;n.resume_after=0.;n.match_skew={}
    n.started_at=time.monotonic()-3;n.ready_since=time.monotonic()-3
    n.last_sim=100.;n.last_sim_wall=time.monotonic()
    n.loads={i:False for i in range(1,7)}
    n.deliveries={'assembly':0,'packing':0};n.completed={i:0 for i in range(1,7)}
    n.factory_messages=[];n.factory_state_at=0.
    n.factory_pub=S(publish=lambda msg:n.factory_messages.append(json.loads(msg.data)))
    n.factory_alive=False;n.factory_heartbeat_at=0.
    enabled={};n.gates={i:S(publish=lambda msg,i=i:enabled.__setitem__(i,msg.data)) for i in range(1,7)}
    return n,clock,logs,goals,enabled

n,clock,logs,goals,enabled=fixture()
for tick in range(6000):
    clock[0]+=.2
    for i,state in n.active.items():
        if enabled.get(i) and state['goal'] is not None:
            x,y=state['points'][state['index']]
            n.world[i]=((x,y,0),time.monotonic(),0)
    for i in range(1,7):
        n.world[i]=(n.world[i][0],time.monotonic(),0)
        n.scans[i]=n.tf_seen_at[i]=time.monotonic()
        for stream in ('world','odom','pair','scan'):
            n.seen[i,stream]=(int(clock[0]*1e9),time.monotonic())
    n.tick()
    assert n.fault is None,n.fault
    assert sum(enabled.values())<=2
    assert sum(enabled.get(i,False) for i in (1,2,3))<=1
    assert sum(enabled.get(i,False) for i in (4,5,6))<=1
    completed={i for i in range(1,7) if any(text.startswith(f'robot{i}: cycle done') for text in logs)}
    if len(completed)==6:break
else:raise AssertionError('Not all 6 robots completed a simulated dispatcher round')
assert {r.robot_namespace for r in goals}=={f'robot{i}' for i in range(1,7)}
assert any('pickup' in text for text in logs) and any('drop' in text for text in logs)
assert all(n.completed[i]>=1 for i in range(1,7)),n.completed
for name,ids in (('assembly',(1,2,3)),('packing',(4,5,6))):
    assert n.deliveries[name]>=3,n.deliveries
    assert sum(n.completed[i] for i in ids)<=n.deliveries[name]<=sum(n.completed[i] for i in ids)+1
n.publish_factory(force=True)
assert n.factory_messages[-1]['deliveries']==n.deliveries
print('PASS: every robot cycles pickup/drop/park, alternation, <=1 moving robot/group; iterations=',tick)

# Pickup/drop dwell completion drives the visible cargo state, never arrival alone.
n,clock,_,_,enabled=fixture();n.tick()
state=n.active[1];state['until']=clock[0]+1
n.publish_factory(force=True)
assert not n.factory_messages[-1]['robots']['1']['loaded']
clock[0]+=1.1
for key in n.seen:n.seen[key]=(int(clock[0]*1e9),time.monotonic())
n.tick();n.publish_factory(force=True)
assert n.factory_messages[-1]['robots']['1']['loaded']
assert n.factory_messages[-1]['robots']['1']['phase']=='drop'
state['until']=clock[0]+1;clock[0]+=1.1
for key in n.seen:n.seen[key]=(int(clock[0]*1e9),time.monotonic())
n.tick();n.publish_factory(force=True)
assert not n.factory_messages[-1]['robots']['1']['loaded']
assert n.factory_messages[-1]['deliveries']['assembly']==1
assert n.factory_messages[-1]['robots']['1']['phase']=='park'
print('PASS: cargo appears after pickup dwell, disappears after drop dwell, delivery counted once')

# Linked mode must hold all AGVs when the factory process vanishes or reports failure.
LinkedCycles=make_cycle_node(S(dwell=3.,require_factory=True))
n,clock,logs,_,enabled=fixture(LinkedCycles)
n.tick()
assert not n.started and not any(enabled.values())
n.factory_heartbeat(S(data=True));n.tick()
assert n.started
n.factory_heartbeat(S(data=False));n.tick()
assert n.stale_since is not None and not any(enabled.values())
n.publish_factory(force=True)
assert n.factory_messages[-1]['held']
n.factory_heartbeat(S(data=True));n.factory_heartbeat_at=time.monotonic()-4
n.tick()
assert not any(enabled.values())
n.fault='shutdown';n.publish_factory(force=True)
assert not n.factory_messages[-1]['running']
print('PASS: required factory heartbeat gates startup/motion; hold/shutdown published to factory')

for mode in ('deviation','reset'):
    n,clock,_,_,enabled=fixture();n.tick()
    clock[0]+=.2
    if mode=='deviation':n.world[1]=((50,50,0),time.monotonic(),0)
    if mode=='reset':clock[0]=1
    n.tick()
    assert n.fault,mode
    assert not any(enabled.values()),mode
print('PASS: cross-track violation and clock reset close every motion gate')

# A short dropout holds all gates, recovers automatically, and does not latch a fault.
n,clock,logs,_,enabled=fixture();n.tick()
n.seen[4,'scan']=(int((clock[0]-.9)*1e9),time.monotonic())
n.tick()
assert n.fault is None and n.stale_since is not None and not any(enabled.values())
assert any('robot4/scan' in line for line in logs)
for stream in ('world','odom','pair','scan'):
    n.seen[4,stream]=(int(clock[0]*1e9),time.monotonic())
n.tick()
assert n.fault is None and n.stale_since is None and not any(enabled.values())
n.resume_after=time.monotonic()-1
n.tick()
assert n.fault is None
print('PASS: transient scan dropout holds gates, names robot4/scan, then recovers')

# A sustained loss still latches a stop and names the failing stream.
n,clock,logs,_,enabled=fixture();n.tick()
n.seen[2,'pair']=(int((clock[0]-1)*1e9),time.monotonic())
n.tick();n.stale_since=time.monotonic()-4;n.tick()
assert n.fault and 'robot2/pair' in n.fault and not any(enabled.values())
print('PASS: persistent paired-data loss still stops all robots')

# Slow real-time factor: 1.1 real seconds but only 0.11 simulated seconds is valid.
seen={(i,stream):(int(99.89*1e9),198.9) for i in range(1,7)
      for stream in ('world','odom','pair','scan')}
assert not freshness_issues(seen,100.,200.)
assert freshness_issues(seen,100.7,200.)
assert freshness_issues(seen,100.,202.)
assert match_pose_stamp(1_000_000_000,{1_015_000_000:object()})==1_015_000_000
assert match_pose_stamp(1_000_000_000,{1_021_000_000:object()}) is None
assert match_pose_stamp(1_000_000_000,{1_000_000_000:object()})==1_000_000_000
print('PASS: separate simulation/wall timeouts and bounded 20ms pose pairing')

# Exercise the actual pose callbacks, not only the timestamp helper.
from nav_msgs.msg import Odometry
n,clock,logs,_,_=fixture()
n.pairs={i:({}, {}) for i in range(1,7)}
n.seen.pop((1,'pair'))
sent=[];n.br=S(sendTransform=sent.append)
def pose_msg(ns,x,y):
    m=Odometry();m.header.stamp.sec=ns//10**9;m.header.stamp.nanosec=ns%10**9
    m.pose.pose.position.x=float(x);m.pose.pose.position.y=float(y)
    m.pose.pose.orientation.w=1.0
    return m
n.pose(1,0,pose_msg(100_000_000_000,10,33))
n.pose(1,1,pose_msg(100_015_000_000,0,0))
assert len(sent)==1 and sent[0].transform.translation.x==10 and sent[0].transform.translation.y==33
n.pose(1,0,pose_msg(100_000_000_000,10,33))
assert len(sent)==1,'Duplicate TF timestamp was published'
n.pose(1,0,pose_msg(100_100_000_000,10,33))
assert len(sent)==1,'Out-of-bound timestamp pairing accepted'
print('PASS: actual callbacks pair 15ms skew; reject old/duplicate or >20ms pairs')

# A user pause closes the gates without becoming a persistent sensor fault.
n,clock,_,_,enabled=fixture();n.tick()
n.last_sim_wall=time.monotonic()-2
n.tick()
assert n.fault is None and not any(enabled.values())
print('PASS: paused simulation holds gates without latching a stale-data error')

from ridgeback_bridge import RidgebackBridge
from rclpy.time import Time
now=Time(nanoseconds=100_000_000_000)
def bridge_case(sim_age,wall_age,allow=True):
    outputs=[]
    b=S(rate=50.,use_gate=True,allowed=allow,gate_at=time.monotonic(),have_odom=True,
        odom_at=time.monotonic()-wall_age,pose_timeout=3.,pose_sim_timeout=.7,
        pose_stamp_ns=100_000_000_000-int(sim_age*1e9),get_clock=lambda:S(now=lambda:now),
        v=.2,w=0.,v_cmd=.3,w_cmd=0.,last_cmd=now,timeout=.5,turn_threshold=0.,
        acc_lin=.5,acc_ang=1.4,yaw=0.,publish=lambda *v:outputs.append(v))
    RidgebackBridge.tick(b)
    return outputs[-1]
assert bridge_case(.11,1.1)[0]>0
assert bridge_case(.8,.1)==(0.,0.,0.)
assert bridge_case(.1,3.1)==(0.,0.,0.)
assert bridge_case(.1,.1,False)==(0.,0.,0.)
print('PASS: bridge tolerates slow RTF but rejects old simulation poses, transport loss and closed gate')
