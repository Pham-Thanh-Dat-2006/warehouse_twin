"""Export measured warehouse bounds and initial joints to a small web schematic manifest."""
import argparse,json
from pathlib import Path
from pxr import Usd,UsdGeom,Gf
from project_paths import ENVIRONMENT_USD,CONFIG_DIR
from factory_kinematics import forward
from factory_surfaces import measure_belt
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--stage',default=str(ENVIRONMENT_USD));p.add_argument('--output',default=str(CONFIG_DIR/'web_scene.json'))
args=p.parse_args();stage=Usd.Stage.Open(args.stage);assert stage
cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render])
xc=UsdGeom.XformCache()
def bbox(prim):
 b=cache.ComputeWorldBound(prim).ComputeAlignedRange()
 return {'center':[round(float(x),4) for x in b.GetMidpoint()],'size':[round(float(x),4) for x in b.GetSize()]}
racks=[]
for side in ('Left','Right'):
 for bay in stage.GetPrimAtPath('/Warehouse/Assets/Racks/'+side).GetChildren():
  racks.append(dict(id=bay.GetName(),side=side,**bbox(bay)))
arms=[]
for row in range(2):
 for cell in range(4):
  path=f'/Warehouse/Zones/Assembly/Line{row}/Arm{cell}/N220_27/UnitsAndAxes/Model'
  points=[]
  for name in ('base_link',)+tuple(f'link_{j}' for j in range(1,7)):
   prim=stage.GetPrimAtPath(path+'/'+name);assert prim
   points.append([float(v) for v in xc.GetLocalToWorldTransform(prim).ExtractTranslation()])
  arms.append({'id':row*4+cell+1,'points':points,'base':[11+cell*10,(10,23)[row]-2.4,1.1]})
loads=[]
for prim in stage.GetPrimAtPath('/Warehouse/Zones/Staging').GetChildren():
 if prim.GetName().startswith('Load'):loads.append(bbox(prim))
data={'version':1,'schematic':True,'width':120,'height':80,'racks':racks,'arms':arms,'loads':loads,
      'belts':[measure_belt(stage,i) for i in range(4)],
      'forklifts':[[112,16],[108,28],[20,55]],'gantries':[[16,65],[112,53]],
      'control_room':{'center':[112,69,5],'size':[14,18,4.2]},
      'note':'Static bounds measured from saved USD; lightweight proxy geometry, not a CAD/Isaac render.'}
plan=json.loads((CONFIG_DIR/'factory_motion_plan.json').read_text())
motion=[]
for key in plan['keyframes']:
 frames=forward(plan['rig'],key['q'])
 points=[frames[name][3,:3].tolist() for name in ('base_link',)+tuple(j['child'] for j in plan['rig']['joints'])]
 m=Gf.Matrix4d(*frames['link_6'].reshape(-1).tolist())
 points.append(list(m.Transform(Gf.Vec3d(0,0,plan['tool_length']))))
 motion.append({'time':key['time'],'points':points})
data['demo_arm_keyframes']=motion
assert len(racks)==40 and len(arms)==8
target=Path(args.output);temporary=target.with_suffix(target.suffix+'.tmp')
temporary.write_text(json.dumps(data,separators=(',',':')))
temporary.replace(target)
print('PASS: exported',len(racks),'measured racks,',len(arms),'initial arm chains,',len(loads),'staging loads to',args.output)
