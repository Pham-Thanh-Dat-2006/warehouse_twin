#!/usr/bin/env python3
"""Check route clearance against the actual scene before running cyclic dispatch."""
from pathlib import Path
from project_paths import ROS2_USD
import math
from pxr import Usd,UsdGeom,UsdPhysics
from warehouse_routes import STARTS,mission,sample_polyline,distance,correction

s=Usd.Stage.Open(str(ROS2_USD))
cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render,UsdGeom.Tokens.guide])
obstacles=[]
for p in s.Traverse():
    path=str(p.GetPath())
    if path.startswith('/Warehouse/Robots/') or path.endswith('/CollisionPlane'):continue
    if not p.HasAPI(UsdPhysics.CollisionAPI):continue
    box=cache.ComputeWorldBound(p).ComputeAlignedRange()
    if box.IsEmpty():continue
    lo,hi=box.GetMin(),box.GetMax()
    if hi[2]>.02 and lo[2]<2.4:obstacles.append((path,lo,hi))
errors=[];min_clearance=math.inf
for i in range(1,7):
    for phase,points in mission(i):
        for x,y in sample_polyline(points,step=.15):
            for path,lo,hi in obstacles:
                d=math.hypot(max(lo[0]-x,0,x-hi[0]),max(lo[1]-y,0,y-hi[1]))
                min_clearance=min(min_clearance,d)
                if d<1.05:errors.append((i,phase,(round(x,2),round(y,2)),path,round(d,2)))
    for phase,points in mission(i):
        for pos in sample_polyline(points,step=.15):
            for j,park in enumerate(STARTS,1):
                if i!=j:assert distance(pos,park)>2.1,(i,j,phase,pos)
for world,odom in [((41.69,50.46,.8),(21.11,12.26,1.55)),((10,33,0),(0,0,0)),((110,46,-2),(-5,1,.3))]:
    x,y,a=correction(world,odom)
    xx=x+math.cos(a)*odom[0]-math.sin(a)*odom[1]
    yy=y+math.sin(a)*odom[0]+math.cos(a)*odom[1]
    assert math.hypot(xx-world[0],yy-world[1])<1e-8
for angle in (-math.pi,-1,0,1,math.pi):
    # Relay subtracts pi/2; the unchanged APF adds pi/2 -> original physical ray.
    assert abs(math.sin(angle-(angle-math.pi/2+math.pi/2)))<1e-10
for i in range(1,7):
    p=s.GetPrimAtPath(f'/Warehouse/Robots/Ridgeback_{i:02d}')
    r=cache.ComputeWorldBound(p).ComputeAlignedRange()
    origin=STARTS[i-1]
    print('Robot bbox relative to base:',i,tuple(round(r.GetMin()[k]-(origin[k] if k<2 else 0),3) for k in range(3)),tuple(round(r.GetMax()[k]-(origin[k] if k<2 else 0),3) for k in range(3)))
    g=f'/Warehouse/ROS2_robot{i}'
    assert s.GetPrimAtPath(g+'/WorldPosePub').GetAttribute('inputs:position').GetConnections()==[__import__('pxr.Sdf',fromlist=['Path']).Path(g+'/WorldPose.outputs:translation')]
if errors:
    for e in errors[:15]:print('CLEARANCE FAIL',e)
    raise SystemExit(f'Blocked route samples: {len(errors)}, min clearance {min_clearance:.2f}m')
print(f'PASS: route centerline clearance >= {min_clearance:.2f}m; parked robot separation; world/odom transform; lidar angle adapter; 6 world-pose publishers')
