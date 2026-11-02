"""Offline test with real USD assets; stubs only the GUI event/timeline API."""
import sys
import os
import types
import math
import time
import json
from pathlib import Path
from project_paths import ROS2_USD
from pxr import Usd,UsdGeom,Gf
from factory_surfaces import support_height,CONTACT_GAP,roller_top

stage=Usd.Stage.Open(os.environ.get('WAREHOUSE_TEST_STAGE',str(ROS2_USD)))
assert stage
playing=[True];clock=[0.]
class Timeline:
    def get_current_time(self):return clock[0]
    def is_playing(self):return playing[0]
    def get_timeline_event_stream(self):return types.SimpleNamespace(create_subscription_to_pop=lambda *a,**k:object())
modules={name:types.ModuleType(name) for name in ('omni','omni.usd','omni.kit','omni.kit.app','omni.timeline','omni.physics','omni.physics.core')}
modules['omni'].usd=modules['omni.usd'];modules['omni'].kit=modules['omni.kit']
modules['omni.kit'].app=modules['omni.kit.app'];modules['omni'].timeline=modules['omni.timeline']
modules['omni.usd'].get_context=lambda:types.SimpleNamespace(get_stage=lambda:stage)
modules['omni.timeline'].get_timeline_interface=lambda:Timeline()
modules['omni.timeline'].TimelineEventType=types.SimpleNamespace(STOP=3)
modules['omni'].physics=modules['omni.physics'];modules['omni.physics'].core=modules['omni.physics.core']
physics_callbacks=[]
modules['omni.physics.core'].get_physics_simulation_interface=lambda:types.SimpleNamespace(
    subscribe_physics_on_step_events=lambda **kw:(physics_callbacks.append(kw['on_update']) or object()))
modules['omni.kit.app'].get_app=lambda:types.SimpleNamespace(get_update_event_stream=lambda:types.SimpleNamespace(create_subscription_to_pop=lambda *a,**k:object()))
sys.modules.update(modules)
from factory_live import start_factory
before=list(stage.GetSessionLayer().subLayerPaths)
ros_enabled='--ros' in sys.argv
driver=start_factory(stage=stage,ros_enabled=ros_enabled)
assert len(driver.boxes)==4 and sum(len(cells) for cells in driver.arms)==8
assert len(driver.payloads)==6
def check_belt_contacts():
    cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),['default','render'])
    for i,line in enumerate(driver.lines):
        belt=driver.belts[i]
        for item,mover in zip(line.parcels,driver.boxes[i]):
            if item.mode not in ('flow','waiting'):continue
            bound=cache.ComputeWorldBound(mover.prim).ComputeAlignedRange()
            deck=support_height(belt,item.x,mover.size[0]/2)
            assert abs(bound.GetMin()[2]-deck-CONTACT_GAP)<1e-5,(i,item.index,bound,deck)
check_belt_contacts()
for i in (2,3):
    belt=driver.belts[i]
    scan=stage.GetPrimAtPath(belt['scanner']['path'])
    assert abs(roller_top(scan)-belt['top'])<1e-5
    item=driver.lines[i].parcels[0]
    item.x=driver.lines[i].x1+3.5
with Usd.EditContext(stage,driver.layer):driver.render()
check_belt_contacts()
for i in (2,3):
    box=driver.boxes[i][0]
    assert abs(box.last_world.Transform(box.local_center)[2]-(driver.belts[i]['top']+CONTACT_GAP+box.size[2]/2))<.01
driver.reset()
with Usd.EditContext(stage,driver.layer):driver.render()
print('PASS: 52 carton bottoms contact measured rollers; A61 scanner aligned and level, no phantom incline')
# Force one real pick pose and verify suction TCP coincides with the carton top.
line=driver.lines[0];arm=line.arms[0];arm.parcel=0;arm.age=1.2
item=line.parcels[0];item.x=arm.pick;item.mode='carried';item.arm=0
with Usd.EditContext(stage,driver.layer):driver.render()
xc=UsdGeom.XformCache()
model='/Warehouse/Zones/Assembly/Line0/Arm0/N220_27/UnitsAndAxes/Model'
ee=xc.GetLocalToWorldTransform(stage.GetPrimAtPath(model+'/link_6'))
tcp=ee.Transform(Gf.Vec3d(0,0,.24))
parcel=driver.boxes[0][0].prim
bound=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render]).ComputeWorldBound(parcel).ComputeAlignedRange()
center=bound.GetMidpoint()
assert math.hypot(tcp[0]-center[0],tcp[1]-center[1])<.005,(tcp,bound)
assert abs(tcp[2]-bound.GetMax()[2])<.005,(tcp,bound)
old_z=center[2]
arm.age=2.1
with Usd.EditContext(stage,driver.layer):driver.render()
bound=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render]).ComputeWorldBound(parcel).ComputeAlignedRange()
assert bound.GetMidpoint()[2]>old_z+.4
print('PASS: real Comau FK reaches the carton within 5mm, carton follows the lifted vacuum tool')
# Exercise release/return and all other cells through actual USD xform writes.
driver.reset()
for _ in range(100):
    for line in driver.lines:line.step(.2)
    with Usd.EditContext(stage,driver.layer):driver.render()
    check_belt_contacts()
assert all(a.cycles>0 for line in driver.lines for a in line.arms)
for cells in driver.arms:
    for cell in cells:
        for op in cell['ops'].values():
            assert all(math.isfinite(x) for row in op.Get() for x in row)
print('PASS: all 8 real-model arms complete cycles and author finite USD transforms')
# Master reception controls both load visuals and factory hold/resume.
driver.master={'version':1,'running':True,'held':False,'robots':{'1':{'loaded':True}}};driver.master_at=__import__('time').monotonic()
driver.physics_step(.05,None);driver.update(None)
assert UsdGeom.Imageable(driver.payloads[0]).GetVisibilityAttr().Get()=='inherited'
old_time=driver.lines[0].time
driver.master['held']=True;driver.physics_step(.05,None);driver.update(None)
assert driver.lines[0].time==old_time
playing[0]=False;driver.update(None)
assert driver.lines[0].time==old_time
print('PASS: AGV cargo state display and master/pause holding')
# Regression: display timeline stays at 0, but real physics ticks drive all motion.
driver.reset();driver.master=None;playing[0]=True
assert len(physics_callbacks)==1
initial_x=driver.lines[2].parcels[0].x
initial_transform=driver.boxes[2][0].op.Get()
for _ in range(400):
    physics_callbacks[0](.05,None);driver.update(None)
assert clock[0]==0.,'Display timeline must remain frozen for this regression'
assert driver.sim_time>19.99
assert driver.lines[2].parcels[0].x>initial_x+5.9
assert driver.boxes[2][0].op.Get()!=initial_transform
assert all(a.cycles>0 for line in driver.lines for a in line.arms)
assert sum(line.output for line in driver.lines)>0
# A large accumulated step is consumed, never discarded by an arbitrary <1s gate.
before_time=driver.sim_time
physics_callbacks[0](1.2,None);driver.update(None)
assert abs(driver.sim_time-before_time-1.2)<1e-8
print('PASS: frozen zero display timeline + physics ticks drive real conveyor transforms, all 8 arms and outfeed')
# Stop resets; Pause does not reset or accumulate hidden catch-up motion.
driver.timeline_event(types.SimpleNamespace(type=3));playing[0]=False;driver.update(None)
assert all(line.time==0 for line in driver.lines)
assert driver.physics_steps==0
if ros_enabled:
    # Reproduce Kit's uninitialized default context, with the bundled SDK rclpy.
    # ROS_DOMAIN_ID must be isolated from the user's running AGVs for this test.
    import os
    assert int(os.environ.get('ROS_DOMAIN_ID','0'))!=0,'Use an isolated ROS_DOMAIN_ID for --ros'
    import rclpy
    from rclpy.context import Context
    from rclpy.node import Node
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.signals import SignalHandlerOptions
    from std_msgs.msg import String,Bool
    assert not rclpy.get_default_context().ok()
    assert driver.executor.context is driver.ros_context
    peer_ctx=Context();rclpy.init(args=[],context=peer_ctx,signal_handler_options=SignalHandlerOptions.NO)
    peer=Node('factory_test_peer',context=peer_ctx)
    peer_ex=SingleThreadedExecutor(context=peer_ctx);peer_ex.add_node(peer)
    received=[]
    production_received=[]
    heartbeat_sub=peer.create_subscription(Bool,'/warehouse/factory_heartbeat',lambda msg:received.append(msg.data),10)
    production_sub=peer.create_subscription(String,'/warehouse/factory_telemetry',lambda msg:production_received.append(json.loads(msg.data)),10)
    state_pub=peer.create_publisher(String,'/warehouse/factory_state',10)
    try:
        expected={'version':1,'running':True,'held':True,'robots':{'2':{'loaded':True}}}
        deadline=time.monotonic()+8.
        while time.monotonic()<deadline:
            state_pub.publish(String(data=json.dumps(expected)))
            driver.update(None);peer_ex.spin_once(timeout_sec=.02)
            if driver.master==expected and True in received and production_received:break
        assert not driver.failed
        assert driver.master==expected,'Factory did not receive ROS state'
        assert True in received,'Factory did not publish healthy heartbeat'
        assert len(production_received[-1]['belts'])==4
        assert len(production_received[-1]['arms'])==8
        assert len(production_received[-1]['arms'][0]['points'])==8
        assert len(production_received[-1]['belts'][0]['parcels'])==13
        parcel=production_received[-1]['belts'][0]['parcels'][0]
        assert len(parcel['position'])==3 and all(math.isfinite(v) for v in parcel['position'])
        assert UsdGeom.Imageable(driver.payloads[1]).GetVisibilityAttr().Get()=='inherited'
        assert not rclpy.get_default_context().ok(),'Factory altered Kit default context'
        print('PASS: bundled SDK ROS receives factory state and publishes heartbeat with default context uninitialized')
        # A failed spin must be reported once, never retried each rendering frame.
        calls=[]
        def fail_spin(**kwargs):
            calls.append(1);raise RuntimeError('injected transport failure')
        driver.executor.spin_once=fail_spin
        import contextlib,io
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            driver.update(None);driver.update(None)
        assert driver.failed and len(calls)==1
        deadline=time.monotonic()+2.
        while time.monotonic()<deadline and False not in received:
            peer_ex.spin_once(timeout_sec=.02)
        assert False in received,'Failed driver did not publish unhealthy heartbeat'
        print('PASS: transport failure stops polling after one attempt and publishes unhealthy heartbeat')
    finally:
        driver.stop()
        peer_ex.shutdown();peer.destroy_node();peer_ctx.shutdown()
driver.stop()
assert list(stage.GetSessionLayer().subLayerPaths)==before
assert not stage.GetPrimAtPath('/Warehouse/Robots/Ridgeback_01/ridgeback/base_link/FactoryPayload')
print('PASS: rewind/reset and session-layer cleanup; saved warehouse untouched')
