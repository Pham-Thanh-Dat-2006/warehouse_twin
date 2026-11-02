"""Live scripted factory layer for an already-open Isaac warehouse stage.
No physical gripper/contact solver: Comau uses its real USD joint frames (FK),
cartons follow conveyors/tool transforms, AGV loads follow dispatcher events.
"""
import json
import math
import time
from pathlib import Path
from project_paths import CONFIG_DIR, ASSET_MANIFEST


def start_factory(stage=None,ros_enabled=True):
    import builtins
    import omni.usd
    import omni.kit.app
    import omni.timeline
    import omni.physics.core
    from pxr import Usd,Sdf,UsdGeom,UsdPhysics,Gf
    import numpy as np
    from factory_cycle_core import create_factory
    from factory_kinematics import forward,angles_at
    from factory_surfaces import measure_belt,support_height,translate_world,CONTACT_GAP

    if getattr(builtins,'warehouse_factory_driver',None):
        builtins.warehouse_factory_driver.stop()
    stage=stage or omni.usd.get_context().get_stage()
    if stage is None or not stage.GetPrimAtPath('/Warehouse/ROS2_robot1'):
        raise RuntimeError('Open warehouse_ros2_ridgeback.usd first')
    plan=json.loads((CONFIG_DIR/'factory_motion_plan.json').read_text())
    manifest=json.loads(ASSET_MANIFEST.read_text())
    def gf(matrix):return Gf.Matrix4d(*np.array(matrix).reshape(-1).tolist())

    class Mover:
        def __init__(self,prim):
            self.prim=prim
            cache=UsdGeom.XformCache()
            self.initial=cache.GetLocalToWorldTransform(prim)
            self.parent_inv=cache.GetLocalToWorldTransform(prim.GetParent()).GetInverse()
            bound=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render]).ComputeWorldBound(prim).ComputeAlignedRange()
            self.center=bound.GetMidpoint();self.size=bound.GetSize()
            self.local_center=self.initial.GetInverse().Transform(self.center)
            self.last_world=Gf.Matrix4d(self.initial)
            self.op=UsdGeom.Xformable(prim).MakeMatrixXform()
            self.op.Set(self.initial*self.parent_inv)
            for p in Usd.PrimRange(prim):
                if p.HasAPI(UsdPhysics.CollisionAPI):UsdPhysics.CollisionAPI(p).CreateCollisionEnabledAttr(False)
                if p.HasAPI(UsdPhysics.RigidBodyAPI):UsdPhysics.RigidBodyAPI(p).CreateRigidBodyEnabledAttr(False)
        def set(self,world):
            self.op.Set(world*self.parent_inv);self.last_world=Gf.Matrix4d(world)
        def free(self,x,z=None):
            m=Gf.Matrix4d(self.initial)
            delta=Gf.Vec3d(x-self.center[0],0,0 if z is None else z-self.center[2])
            m.SetTranslateOnly(self.initial.ExtractTranslation()+delta)
            self.set(m);return m
        def visible(self,show):UsdGeom.Imageable(self.prim).GetVisibilityAttr().Set('inherited' if show else 'invisible')

    class LiveFactory:
        def __init__(self):
            self.stage=stage;self.root_id=stage.GetRootLayer().identifier
            self.layer=Sdf.Layer.CreateAnonymous('factory_live.usda')
            stage.GetSessionLayer().subLayerPaths.insert(0,self.layer.identifier)
            self.timeline=omni.timeline.get_timeline_interface()
            self.lines=create_factory();self.boxes=[];self.arms=[];self.treads=[];self.payloads=[]
            self.belts=[measure_belt(stage,i) for i in range(4)]
            self.failed=False;self.closed=False;self.master=None;self.master_at=0.;self.ros=None
            self.executor=None;self.node=None;self.ros_context=None
            self.pending_dt=0.;self.sim_time=0.;self.physics_steps=0;self.reset_requested=False
            self.render_t=None;self.last_status=0.;self.heartbeat_at=0.
            self.telemetry_at=0.
            self.physics_sub=None;self.timeline_sub=None
            self.processed=0;self.state_dirty=True;self.sub=None;self.window=None
            print('[FACTORY LOAD] Building motion layer (4 lines, 8 arms)',flush=True)
            with Usd.EditContext(stage,self.layer):
                self.setup()
                self.render()
            if ros_enabled:
                print('[FACTORY LOAD] Connecting factory ROS node',flush=True)
                self.setup_ros()
            self.physics_sub=omni.physics.core.get_physics_simulation_interface().subscribe_physics_on_step_events(
                on_update=self.physics_step,pre_step=False,order=0)
            self.timeline_sub=self.timeline.get_timeline_event_stream().create_subscription_to_pop(
                self.timeline_event,name='warehouse-factory-reset')
            self.sub=omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(self.update,name='warehouse-factory-live')
            print('[FACTORY] Ready: 4 conveyors, 8 Comau pick/place workcells, 6 AGV load displays; scripted motion',flush=True)

        def setup(self):
            root='/Warehouse/FactoryLive'
            UsdGeom.Xform.Define(stage,root)
            for line_id in range(4):
                assembly=line_id<2;row=line_id if assembly else line_id-2
                path=f'/Warehouse/Zones/Assembly/Line{row}/Conveyor' if assembly else f'/Warehouse/Zones/Packing/Line{row}/Belt/Straight'
                y=(10,23)[row] if assembly else (8,21)[row]
                belt=self.belts[line_id]
                if 'scanner' in belt:
                    scan=belt['scanner']
                    translate_world(stage.GetPrimAtPath(scan['path']),scan['offset'])
                self.boxes.append([Mover(stage.GetPrimAtPath(path+f'/Parcel{i}')) for i in range(13)])
                tracks=[]
                for i in range(28):
                    p=UsdGeom.Cube.Define(stage,root+f'/Belt{line_id}/Tread{i}')
                    p.CreateSizeAttr(1.);p.CreateDisplayColorAttr([Gf.Vec3f(.1,.13,.14)])
                    xf=UsdGeom.XformCommonAPI(p);xf.SetScale(Gf.Vec3f(.035,.9,.001))
                    tracks.append((xf,y,i))
                self.treads.append(tracks)
                cells=[]
                if assembly:
                    for cell in range(4):
                        model=f'/Warehouse/Zones/Assembly/Line{row}/Arm{cell}/N220_27/UnitsAndAxes/Model'
                        prim=stage.GetPrimAtPath(model);assert prim,model
                        for p in Usd.PrimRange(prim):
                            if p.HasAPI(UsdPhysics.CollisionAPI):UsdPhysics.CollisionAPI(p).CreateCollisionEnabledAttr(False)
                            if p.HasAPI(UsdPhysics.RigidBodyAPI):UsdPhysics.RigidBodyAPI(p).CreateRigidBodyEnabledAttr(False)
                            if p.IsA(UsdPhysics.Joint):UsdPhysics.Joint(p).CreateJointEnabledAttr(False)
                        model_world=UsdGeom.XformCache().GetLocalToWorldTransform(prim)
                        ops={}
                        for joint in plan['rig']['joints']:
                            body=stage.GetPrimAtPath(model+'/'+joint['child']);assert body
                            ops[joint['child']]=UsdGeom.Xformable(body).MakeMatrixXform()
                        ee_path=model+'/link_6/VacuumTool'
                        tool=UsdGeom.Cylinder.Define(stage,ee_path+'/Tube')
                        tool.CreateRadiusAttr(.055);tool.CreateHeightAttr(.22)
                        UsdGeom.XformCommonAPI(tool).SetTranslate(Gf.Vec3d(0,0,.11))
                        tool.CreateDisplayColorAttr([Gf.Vec3f(.25,.28,.30)])
                        cup=UsdGeom.Cylinder.Define(stage,ee_path+'/Cup')
                        cup.CreateRadiusAttr(.12);cup.CreateHeightAttr(.025)
                        UsdGeom.XformCommonAPI(cup).SetTranslate(Gf.Vec3d(0,0,.235))
                        cup.CreateDisplayColorAttr([Gf.Vec3f(.04,.04,.04)])
                        cells.append({'ops':ops,'world':model_world,'held':None,'offset':None})
                self.arms.append(cells)
            # Visual-only carton on the rear deck; it does not change robot dynamics.
            for i in range(1,7):
                path=f'/Warehouse/Robots/Ridgeback_{i:02d}/ridgeback/base_link/FactoryPayload'
                p=UsdGeom.Xform.Define(stage,path);api=UsdGeom.XformCommonAPI(p)
                api.SetTranslate(Gf.Vec3d(-.24,0,.38));api.SetScale(Gf.Vec3f(.52,.72,.55))
                a=UsdGeom.Xform.Define(stage,path+'/Units');UsdGeom.XformCommonAPI(a).SetScale(Gf.Vec3f(.01,.01,.01))
                a.GetPrim().GetReferences().AddReference(manifest['assets']['box'])
                for child in Usd.PrimRange(p.GetPrim()):
                    if child.HasAPI(UsdPhysics.CollisionAPI):UsdPhysics.CollisionAPI(child).CreateCollisionEnabledAttr(False)
                    if child.HasAPI(UsdPhysics.RigidBodyAPI):UsdPhysics.RigidBodyAPI(child).CreateRigidBodyEnabledAttr(False)
                UsdGeom.Imageable(p).CreateVisibilityAttr('invisible');self.payloads.append(p.GetPrim())

        def setup_ros(self):
            import rclpy
            from rclpy.context import Context
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.node import Node
            from rclpy.signals import SignalHandlerOptions
            from std_msgs.msg import String,Bool
            self.ros=rclpy;self.ros_context=Context()
            rclpy.init(args=[],context=self.ros_context,signal_handler_options=SignalHandlerOptions.NO)
            self.node=Node('warehouse_factory_live',context=self.ros_context)
            # Kit's default context may be uninitialized after bridge startup.
            # Keep one executor on our own context instead of rclpy.spin_once's global one.
            self.executor=SingleThreadedExecutor(context=self.ros_context)
            self.executor.add_node(self.node)
            self.subscription=self.node.create_subscription(String,'/warehouse/factory_state',self.state,10)
            self.heartbeat=self.node.create_publisher(Bool,'/warehouse/factory_heartbeat',10)
            self.telemetry=self.node.create_publisher(String,'/warehouse/factory_telemetry',10)
            self.string_type=String
            self.bool_type=Bool

        def publish_telemetry(self,now,running):
            if not self.ros or self.failed or now-self.telemetry_at<.5:return
            belts=[];arms=[]
            for i,line in enumerate(self.lines):
                parcels=[]
                for item,mover in zip(line.parcels,self.boxes[i]):
                    pos=mover.last_world.Transform(mover.local_center)
                    parcels.append({'id':item.index,'position':[round(float(v),4) for v in pos],
                                    'mode':item.mode,'visible':item.mode!='outfeed'})
                belts.append({'id':i+1,'name':('Lắp ráp' if i<2 else 'Đóng gói')+f' {i%2+1}',
                              'speed':line.speed,'outputs':line.output,'running':running,'parcels':parcels})
                for arm in line.arms:
                    state=('idle' if arm.parcel is None else 'picking' if arm.age<1.2 else
                           'carrying' if arm.age<3.4 else 'placing' if arm.age<4.15 else 'returning')
                    arms.append({'id':i*4+arm.index+1,'line':i+1,'cell':arm.index+1,
                                 'cycles':arm.cycles,'state':state,
                                 'points':self.arms[i][arm.index].get('joint_points',[])})
            data={'version':1,'factory_time':self.sim_time,'physics_steps':self.physics_steps,
                  'running':running,'failed':self.failed,'belts':belts,'arms':arms,
                  'arm_cycles':sum(a['cycles'] for a in arms),'belt_outputs':sum(b['outputs'] for b in belts)}
            self.telemetry.publish(self.string_type(data=json.dumps(data)))
            self.telemetry_at=now

        def state(self,msg):
            try:
                state=json.loads(msg.data)
                if state.get('version')!=1:return
                self.master=state;self.master_at=time.monotonic();self.state_dirty=True
            except (ValueError,TypeError):pass

        def reset(self):
            self.lines=create_factory()
            self.sim_time=0.;self.pending_dt=0.;self.physics_steps=0;self.render_t=None
            for cells in self.arms:
                for cell in cells:cell['held']=None;cell['offset']=None

        def physics_step(self,dt,*context):
            # Display timeline can stay at zero (the saved stage has start=end=0)
            # while PhysX and /clock keep running. Accumulate authoritative step dt.
            if not self.closed and not self.failed and math.isfinite(dt) and dt>0:
                self.pending_dt+=dt;self.physics_steps+=1

        def timeline_event(self,event):
            if event.type==int(omni.timeline.TimelineEventType.STOP):
                self.reset_requested=True;self.pending_dt=0.

        def render(self):
            for line_id,line in enumerate(self.lines):
                for cell,arm in zip(self.arms[line_id],line.arms):
                    q=angles_at(plan,arm.age if arm.parcel is not None else 0.)
                    frames=forward(plan['rig'],q)
                    for name,op in cell['ops'].items():op.Set(gf(frames[name]))
                    ee=gf(frames['link_6'])*cell['world']
                    points=[(gf(frames[name])*cell['world']).ExtractTranslation()
                            for name in ('base_link',)+tuple(j['child'] for j in plan['rig']['joints'])]
                    points.append(ee.Transform(Gf.Vec3d(0,0,plan['tool_length'])))
                    cell['joint_points']=[[round(float(v),5) for v in point] for point in points]
                    if arm.parcel is not None and not arm.released and arm.age>=plan['attach_time']:
                        parcel=self.boxes[line_id][arm.parcel]
                        if cell['held']!=arm.parcel:
                            item=line.parcels[arm.parcel]
                            z=support_height(self.belts[line_id],arm.pick,parcel.size[0]/2)+parcel.size[2]/2+CONTACT_GAP
                            pickup_matrix=parcel.free(arm.pick,z)
                            pick_ee=gf(forward(plan['rig'],plan['solutions']['pick'])['link_6'])*cell['world']
                            cell['held']=arm.parcel;cell['offset']=pickup_matrix*pick_ee.GetInverse()
                        parcel.set(cell['offset']*ee)
                    else:cell['held']=None;cell['offset']=None
                for item,mover in zip(line.parcels,self.boxes[line_id]):
                    mover.visible(item.mode!='outfeed')
                    if item.mode!='carried':
                        z=support_height(self.belts[line_id],item.x,mover.size[0]/2)+mover.size[2]/2+CONTACT_GAP
                        mover.free(item.x,z)
                for xf,y,index in self.treads[line_id]:
                    x=line.x0+((index*(line.x1-line.x0)/28+line.time*line.speed)%(line.x1-line.x0))
                    xf.SetTranslate(Gf.Vec3d(x,y,self.belts[line_id]['top']+.0005))
            robots={} if self.master is None else self.master.get('robots',{})
            for i,p in enumerate(self.payloads,1):
                show=bool(robots.get(str(i),{}).get('loaded',False))
                UsdGeom.Imageable(p).GetVisibilityAttr().Set('inherited' if show else 'invisible')

        def update(self,event):
            if self.closed:return
            try:
                current=omni.usd.get_context().get_stage()
                if current is None or current.GetSessionLayer()!=stage.GetSessionLayer():
                    self.stop();return
                now=time.monotonic()
                if self.ros and not self.failed:
                    self.executor.spin_once(timeout_sec=0.)
                    if now-self.heartbeat_at>.2:
                        self.heartbeat.publish(self.bool_type(data=not self.failed));self.heartbeat_at=now
                if self.reset_requested:
                    self.reset();self.reset_requested=False
                dt=self.pending_dt;self.pending_dt=0.
                running=self.timeline.is_playing() and not self.failed
                if self.master is not None:
                    running &= bool(self.master.get('running')) and not self.master.get('held') and now-self.master_at<3.
                if running and dt>0.:
                    for line in self.lines:line.step(dt)
                    self.sim_time+=dt
                if self.render_t is None or self.sim_time-self.render_t>=.04 or self.state_dirty:
                    with Usd.EditContext(stage,self.layer):self.render()
                    self.render_t=self.sim_time;self.state_dirty=False
                self.publish_telemetry(now,running)
                if running and now-self.last_status>10:
                    cycles=sum(a.cycles for l in self.lines for a in l.arms)
                    outputs=sum(l.output for l in self.lines)
                    print(f'[FACTORY] mode={"linked" if self.master is not None else "preview"} '
                          f'sim={self.sim_time:.2f}s physics_steps={self.physics_steps} '
                          f'arm_cycles={cycles} belt_outputs={outputs}',flush=True)
                    self.last_status=now
            except Exception as exc:
                if not self.failed:
                    import traceback
                    print('[FACTORY ERROR]',exc)
                    traceback.print_exc()
                    if getattr(self,'heartbeat',None):
                        try:self.heartbeat.publish(self.bool_type(data=False))
                        except Exception:pass
                self.failed=True

        def stop(self):
            if self.closed:return
            self.closed=True;self.sub=None;self.physics_sub=None;self.timeline_sub=None
            try:
                if getattr(self,'heartbeat',None):self.heartbeat.publish(self.bool_type(data=False))
            finally:
                try:
                    if self.executor is not None:self.executor.shutdown(timeout_sec=0.)
                    if self.node is not None:self.node.destroy_node()
                    if self.ros_context is not None and self.ros_context.ok():self.ros_context.shutdown()
                finally:
                    session=stage.GetSessionLayer()
                    session.subLayerPaths=[p for p in session.subLayerPaths if p!=self.layer.identifier]
            print('[FACTORY] Stopped; original USD files preserved')

    driver=object.__new__(LiveFactory)
    try:driver.__init__()
    except Exception:
        if getattr(driver,'layer',None):driver.stop()
        raise
    builtins.warehouse_factory_driver=driver
    return driver


if __name__=='__main__':start_factory()
