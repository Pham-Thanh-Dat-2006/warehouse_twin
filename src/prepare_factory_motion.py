#!/usr/bin/env python3
"""Extract real Comau USD joints and solve a scripted pick/place motion offline."""
import json
import math
from pathlib import Path
from project_paths import PROJECT_ROOT, CONFIG_DIR, ASSET_MANIFEST, ENVIRONMENT_USD
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from pxr import Usd,UsdGeom,UsdPhysics,Gf
from factory_kinematics import forward
from factory_surfaces import measure_belt,CONTACT_GAP


def main():
    root=PROJECT_ROOT
    manifest=json.loads(ASSET_MANIFEST.read_text())
    stage=Usd.Stage.Open(manifest['assets']['arm']);xc=UsdGeom.XformCache()
    asset_root=stage.GetDefaultPrim().GetPath()
    def frame(pos,q):return Gf.Matrix4d(Gf.Rotation(Gf.Quatd(q)),Gf.Vec3d(pos))
    rig={'base':[list(row) for row in xc.GetLocalToWorldTransform(stage.GetPrimAtPath(str(asset_root)+'/base_link'))],'joints':[]}
    for i in range(1,7):
        p=stage.GetPrimAtPath(str(asset_root)+f'/joints/joint_{i}');j=UsdPhysics.RevoluteJoint(p)
        b0,b1=j.GetBody0Rel().GetTargets()[0],j.GetBody1Rel().GetTargets()[0]
        f0=frame(j.GetLocalPos0Attr().Get(),j.GetLocalRot0Attr().Get())
        f1=frame(j.GetLocalPos1Attr().Get(),j.GetLocalRot1Attr().Get())
        w0=xc.GetLocalToWorldTransform(stage.GetPrimAtPath(b0));w1=xc.GetLocalToWorldTransform(stage.GetPrimAtPath(b1))
        relative=f1*w1*(f0*w0).GetInverse();axis=j.GetAxisAttr().Get()
        rest=relative.ExtractRotation().GetAngle()*relative.ExtractRotation().GetAxis()['XYZ'.index(axis)]
        rig['joints'].append({'parent':b0.name,'child':b1.name,'axis':axis,
            'f0':[list(row) for row in f0],'f1':[list(row) for row in f1], 'rest':math.radians(rest),
            'low':math.radians(j.GetLowerLimitAttr().Get()),'high':math.radians(j.GetUpperLimitAttr().Get())})
    rest=np.array([j['rest'] for j in rig['joints']])
    for name,m in forward(rig,rest).items():
        actual=np.array(xc.GetLocalToWorldTransform(stage.GetPrimAtPath(str(asset_root)+'/'+name)))
        assert np.max(np.abs(m-actual))<1e-4,(name,np.max(np.abs(m-actual)))
    bounds=([j['low']+1e-5 for j in rig['joints']],[j['high']-1e-5 for j in rig['joints']])
    target_rot=np.diag([1.,-1.,-1.]);rng=np.random.default_rng(7)
    scene=Usd.Stage.Open(str(ENVIRONMENT_USD));belt=measure_belt(scene,0)
    pick_z=belt['top']+CONTACT_GAP+belt['parcel_size'][2]+.24-1.1
    targets=[('home',[2.2,.45,1.65]),('above_pick',[2.4,.45,pick_z+.25]),('pick',[2.4,.45,pick_z]),
             ('lift',[2.4,.45,1.55]),('transfer',[2.4,-.45,1.55]),('place',[2.4,-.45,pick_z]),
             ('above_place',[2.4,-.45,1.55])]
    solutions={};previous=rest
    for name,target in targets:
        def residual(q):
            m=forward(rig,q)['link_6']
            orientation=Rotation.from_matrix((m[:3,:3]@target_rot.T).T).as_rotvec()
            return np.r_[m[3,:3]-target,.35*orientation,1e-5*(q-previous)]
        best=None
        seeds=[previous,rest]+[rng.uniform(bounds[0],bounds[1]) for _ in range(12)]
        for seed in seeds:
            result=least_squares(residual,np.clip(seed,np.array(bounds[0])+1e-6,np.array(bounds[1])-1e-6),bounds=bounds,max_nfev=250)
            error=np.linalg.norm(residual(result.x)[:6])
            if best is None or error<best[0]:best=(error,result.x)
            if error<1e-5:break
        assert best[0]<.002,(name,best[0])
        previous=best[1];solutions[name]=previous.tolist()
        print('IK OK',name,'residual',round(best[0],7))
    keys=[(0,'home'),(.6,'above_pick'),(1.2,'pick'),(1.35,'pick'),(2.1,'lift'),(3.4,'transfer'),
          (4.0,'place'),(4.15,'place'),(4.8,'above_place'),(6.4,'home')]
    plan={'rig':rig,'solutions':solutions,'keyframes':[{'time':t,'q':solutions[name]} for t,name in keys],
          'attach_time':1.2,'release_time':4.15,'duration':6.4,'tool_length':.24,
          'pick_x_offset':-.45,'place_x_offset':.45,'belt_top':belt['top'],
          'parcel_height':belt['parcel_size'][2],'contact_gap':CONTACT_GAP}
    output=CONFIG_DIR/'factory_motion_plan.json';output.write_text(json.dumps(plan,indent=2))
    print('Saved',output)


if __name__=='__main__':main()
