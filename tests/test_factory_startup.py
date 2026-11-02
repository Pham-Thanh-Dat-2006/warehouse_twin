"""Regression: stalled background loads must not hide startup; camera must cover the warehouse."""
from types import SimpleNamespace as S
from factory_startup import wait_for_assets,set_overview
from pxr import Usd,UsdGeom,Gf

clock=[0.];frames=[];messages=[]
def update():
    clock[0]+=1.;frames.append(clock[0])
app=S(update=update,is_running=lambda:True)
ctx=S(get_stage_loading_status=lambda:(1,0,7))
assert not wait_for_assets(app,ctx,timeout=12.,now=lambda:clock[0],report=lambda text,**kw:messages.append(text))
assert len(frames)==12
assert any('7 background resources' in line for line in messages)
print('PASS: permanently pending resources end the wait, with progress and remaining-resource count')
ctx=S(get_stage_loading_status=lambda:(1,0,int(clock[0]<15)))
assert wait_for_assets(app,ctx,now=lambda:clock[0])
assert clock[0]==15
try:
    wait_for_assets(S(is_running=lambda:False),S(get_stage_loading_status=lambda:(1,0,1)))
except RuntimeError:pass
else:raise AssertionError('Closed app was kept in the loading loop')
print('PASS: finite loading completes; closing the window exits the wait')
stage=Usd.Stage.CreateInMemory()
UsdGeom.Xform.Define(stage,'/Warehouse')
UsdGeom.Camera.Define(stage,'/Warehouse/Camera')
original=stage.GetRootLayer().ExportToString()
viewport=S(camera_path='/OmniverseKit_Persp')
set_overview(stage,viewport)
assert viewport.camera_path=='/Warehouse/Camera'
assert original==stage.GetRootLayer().ExportToString(),'Saved USD camera changed'
camera=UsdGeom.Camera(stage.GetPrimAtPath(viewport.camera_path)).GetCamera()
frustum=camera.frustum
projection=frustum.ComputeViewMatrix()*frustum.ComputeProjectionMatrix()
for x in (0,120):
    for y in (0,80):
        for z in (0,12):
            p=projection.Transform(Gf.Vec3d(x,y,z))
            assert abs(p[0])<1 and abs(p[1])<1 and -1<p[2]<1,(x,y,z,p)
print('PASS: overview covers all 120x80x12m corners; saved USD is unchanged')
