#!/usr/bin/env python3
"""Author world-pose graph ports and paint cyclic route guides in USD."""
from pathlib import Path
from project_paths import ROS2_USD, ENVIRONMENT_USD
from pxr import Usd,Sdf,UsdGeom,Gf
from warehouse_routes import mission,PICKUPS,DROPS
import math


def mark_cycle_roads(stage):
    traffic=stage.GetPrimAtPath('/Warehouse/Zones/Traffic')
    if traffic:
        for p in list(traffic.GetChildren()):
            if p.GetName().startswith('Lane'):
                stage.RemovePrim(p.GetPath())
    root='/Warehouse/Zones/CycleRoads'
    if stage.GetPrimAtPath(root):stage.RemovePrim(root)
    seen=set();idx=0
    for robot in range(1,7):
        color=(.04,.45,.85) if robot<=3 else (.08,.65,.32)
        for _,points in mission(robot):
            for a,b in zip(points,points[1:]):
                key=(robot<=3,tuple(a),tuple(b))
                if key in seen:continue
                seen.add(key)
                length=math.hypot(b[0]-a[0],b[1]-a[1])
                count=max(1,int(length/1.6))
                angle=math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))
                for j in range(count):
                    t=(j+.5)/count
                    p=UsdGeom.Cube.Define(stage,root+f'/Road{idx}/Dash{j}')
                    p.CreateSizeAttr(1.)
                    xf=UsdGeom.XformCommonAPI(p)
                    xf.SetTranslate(Gf.Vec3d(a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]),.002))
                    xf.SetRotate(Gf.Vec3f(0,0,angle))
                    xf.SetScale(Gf.Vec3f(min(.8,length/count),.10,.003))
                    p.CreateDisplayColorAttr([Gf.Vec3f(*color)])
                idx+=1
    for group in ('assembly','packing'):
        color=(.04,.45,.85) if group=='assembly' else (.08,.65,.32)
        for role,point in (('Pickup',PICKUPS[group]),('Drop',DROPS[group])):
            for side,(dx,dy,sx,sy) in enumerate(((0,-1,2,.12),(0,1,2,.12),(-1,0,.12,2),(1,0,.12,2))):
                p=UsdGeom.Cube.Define(stage,root+f'/{group}_{role}/Edge{side}')
                p.CreateSizeAttr(1.)
                xf=UsdGeom.XformCommonAPI(p)
                xf.SetTranslate(Gf.Vec3d(point[0]+dx,point[1]+dy,.002))
                xf.SetScale(Gf.Vec3f(sx,sy,.003))
                p.CreateDisplayColorAttr([Gf.Vec3f(*color)])


def add_world_pose(s):
    for i in range(1,7):
        g=f'/Warehouse/ROS2_robot{i}'
        assert s.GetPrimAtPath(g+'/OdomPub')
        chassis=f'/Warehouse/Robots/Ridgeback_{i:02d}/ridgeback/base_link'
        assert s.GetPrimAtPath(chassis)
        for name in ('WorldPose','WorldPosePub'):
            if s.GetPrimAtPath(g+'/'+name):s.RemovePrim(g+'/'+name)
        p=s.DefinePrim(g+'/WorldPose','OmniGraphNode')
        p.CreateAttribute('node:type',Sdf.ValueTypeNames.Token).Set('isaacsim.core.nodes.IsaacReadWorldPose')
        p.CreateAttribute('node:typeVersion',Sdf.ValueTypeNames.Int).Set(2)
        p.CreateRelationship('inputs:prim').SetTargets([Sdf.Path(chassis)])
        p.CreateAttribute('outputs:translation',Sdf.ValueTypeNames.Vector3d)
        p.CreateAttribute('outputs:orientation',Sdf.ValueTypeNames.Quatd)
        Sdf.CopySpec(s.GetRootLayer(),g+'/OdomPub',s.GetRootLayer(),g+'/WorldPosePub')
        pub=s.GetPrimAtPath(g+'/WorldPosePub')
        pub.GetAttribute('inputs:topicName').Set('warehouse_pose')
        pub.GetAttribute('inputs:odomFrameId').Set(f'robot{i}/map')
        pub.GetAttribute('inputs:position').SetConnections([Sdf.Path(g+'/WorldPose.outputs:translation')])
        pub.GetAttribute('inputs:orientation').SetConnections([Sdf.Path(g+'/WorldPose.outputs:orientation')])


def main():
    path=ROS2_USD
    s=Usd.Stage.Open(str(path))
    assert s
    add_world_pose(s)
    mark_cycle_roads(s)
    s.GetRootLayer().Save(force=True)
    for i in range(1,7):
        g=f'/Warehouse/ROS2_robot{i}'
        assert s.GetPrimAtPath(g+'/WorldPose').GetRelationship('inputs:prim').GetTargets()
        assert s.GetPrimAtPath(g+'/WorldPosePub').GetAttribute('inputs:topicName').Get()=='warehouse_pose'
        print(f'PASS: robot{i}/warehouse_pose (IsaacReadWorldPose v2)')
    print('Saved',path)
    environment=ENVIRONMENT_USD
    if environment.exists():
        env=Usd.Stage.Open(str(environment))
        mark_cycle_roads(env)
        env.GetRootLayer().Save(force=True)
        print('Updated route floor markings:',environment)


if __name__=='__main__':main()
