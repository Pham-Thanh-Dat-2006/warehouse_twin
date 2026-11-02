"""Validate authored map geometry and corridor without starting Isaac/GPU.
Run with the same OpenUSD environment as build_warehouse_map.sh.
"""
import json
import sys
from pathlib import Path
from project_paths import ENVIRONMENT_USD
from pxr import Usd, UsdGeom, UsdPhysics, Sdf

path = sys.argv[1] if len(sys.argv) > 1 else str(ENVIRONMENT_USD)
stage = Usd.Stage.Open(path)
assert stage and stage.GetDefaultPrim(), 'USD missing/defaultPrim invalid'
meta = stage.GetRootLayer().customLayerData
counts = json.loads(meta['model_counts'])
expected = {'rack':40, 'arm':8, 'worker':20, 'packing_table':6,
            'crane':2, 'forklift':3, 'conveyor_packing':2, 'fan':5, 'entrance':1}
for kind, count in expected.items():
    assert counts.get(kind) == count, (kind, counts.get(kind), count)
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.guide])
checked = 0
for prim in stage.Traverse():
    if str(prim.GetPath()).startswith('/Warehouse/Robots/'):
        continue
    if prim.HasAPI(UsdPhysics.RigidBodyAPI):
        assert not UsdPhysics.RigidBodyAPI(prim).GetRigidBodyEnabledAttr().Get(), f'Dynamic prop: {prim.GetPath()}'
    if not prim.HasAPI(UsdPhysics.CollisionAPI):
        continue
    if str(prim.GetPath()) == '/Warehouse/Architecture/CollisionPlane':
        continue
    r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
    if r.IsEmpty():
        continue
    lo, hi = r.GetMin(), r.GetMax()
    assert not (lo[2] < 3 and hi[2] > .01 and lo[0] < 116 and hi[0] > 4
                and lo[1] < 48 and hi[1] > 32), f'Corridor blocked: {prim.GetPath()}'
    assert not (lo[2] < 3 and hi[2] > .01 and lo[0] < 64 and hi[0] > 59
                and lo[1] < 79.0 and hi[1] > 49), f'Central rack aisle blocked: {prim.GetPath()}'
    checked += 1
assert counts.get('wall_panel', 0) >= 50, 'Wall panel facade missing'
for side in ('Left','Right'):
    root = stage.GetPrimAtPath('/Warehouse/Assets/Racks/'+side)
    assert root and len(root.GetChildren()) == 20, 'Rack block: '+side
right = stage.GetPrimAtPath('/Warehouse/Zones/Crane/Gantry1/UnitsAndAxes')
assert abs(right.GetAttribute('xformOp:rotateXYZ').Get()[2] - 180) < 1e-5, 'Right gantry orientation'
# These models must actually contain referenced geometry, not only placeholder boxes.
for key in ('N220_27', 'MachineOperator', 'Table0', 'Gantry0', 'Fan0', 'Entrance', 'Panel00'):
    matches = [p for p in stage.Traverse() if p.GetName() == key]
    assert matches, key
    assert any(c.IsA(UsdGeom.Mesh) for p in matches for c in Usd.PrimRange(p)), f'No mesh: {key}'
print('PASS:', counts)
print('PASS: static props, actual referenced meshes, corridor clear;', checked, 'colliders')

# Check local texture/MDL paths; NVIDIA streaming URLs resolve inside Isaac.
missing = set()
for layer in stage.GetUsedLayers():
    def check_asset(path):
        attr = layer.GetObjectAtPath(path)
        if not isinstance(attr, Sdf.AttributeSpec) or attr.typeName not in (
                Sdf.ValueTypeNames.Asset, Sdf.ValueTypeNames.AssetArray):
            return
        values = attr.default
        values = values if attr.typeName == Sdf.ValueTypeNames.AssetArray and values is not None else [values]
        for value in values:
            if not isinstance(value, Sdf.AssetPath) or not value.path or '://' in value.path:
                continue
            if '/' not in value.path and value.path.endswith('.mdl'):
                continue
            file = Path(layer.realPath).parent / value.path
            if '<UDIM>' in str(file):
                exists = bool(list(file.parent.glob(file.name.replace('<UDIM>', '*'))))
            else:
                exists = file.exists()
            if not exists:
                missing.add(str(file.resolve()))
    layer.Traverse(Sdf.Path.absoluteRootPath, check_asset)
assert not missing, 'Missing local asset files: ' + repr(sorted(missing))
print('PASS: local texture/MDL dependencies; NVIDIA textures use HTTPS streaming')

assert not stage.GetPrimAtPath('/Warehouse/Lighting/HexGrid'), 'Hex-grid lamps still present'
robot_root = stage.GetPrimAtPath('/Warehouse/Robots')
positions = [(10,33),(10,38.2),(10,43.4),(110,35.6),(110,40.8),(110,46)]
assert meta.get('mobile_robot_count') == 6
for i,(x,y) in enumerate(positions,1):
    p = stage.GetPrimAtPath(f'/Warehouse/Robots/Ridgeback_{i:02d}')
    assert p, f'Missing robot{i}'
    pos = UsdGeom.XformCommonAPI(p).GetXformVectors(Usd.TimeCode.Default())[0]
    assert abs(pos[0]-x)<1e-4 and abs(pos[1]-y)<1e-4, (i,pos)
    r = cache.ComputeWorldBound(p).ComputeAlignedRange()
    assert not r.IsEmpty() and abs(r.GetMin()[2]-.002)<.01, (i,r)
    subprims = list(Usd.PrimRange(p, Usd.TraverseInstanceProxies()))
    assert any(c.IsA(UsdGeom.Mesh) for c in subprims), f'Robot{i} geometry missing'
    assert any(c.HasAPI(UsdPhysics.ArticulationRootAPI) for c in subprims), f'Robot{i} articulation missing'
    assert any(c.HasAPI(UsdPhysics.RigidBodyAPI) and UsdPhysics.RigidBodyAPI(c).GetRigidBodyEnabledAttr().Get()
               for c in subprims), f'Robot{i} physics disabled'
print('PASS: 6 Ridgeback+UR5, spawn positions, grounding, active articulation; hex lamps removed')
