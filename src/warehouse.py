# warehouse.py - Isaac Sim 6.1 - reference layout 120 x 80 m
import os
from project_paths import MAPS_DIR, ASSET_MANIFEST

USD_ONLY = os.environ.get('USD_ONLY') == '1'
ENV_ONLY = os.environ.get('ENV_ONLY') == '1'
simulation_app = None
if not USD_ONLY:
    from isaacsim.simulation_app import SimulationApp
    simulation_app = SimulationApp({"headless": True})

from pxr import Gf, Usd, UsdGeom, UsdLux, UsdPhysics

LITE = os.environ.get("LITE") == "1"   # LITE=1: chi san + tuong + robot, de thu nhanh
ROBOT = os.environ.get("ROBOT", "ridgeback").lower()   # create3 | tb4
_base = "warehouse_lite" if LITE else "warehouse_120x80"
if ROBOT != "create3":
    _base += "_" + ROBOT
OUTPUT = os.path.expanduser(os.environ.get("OUTPUT", str(MAPS_DIR / f'{_base}.usd')))

# ------------------------------------------------------------
# ASSETS
# ------------------------------------------------------------
try:
    if USD_ONLY:
        ISAAC_ROOT = os.environ.get('ISAAC_ASSET_ROOT')
    else:
        from isaacsim.storage.native import get_assets_root_path
        ISAAC_ROOT = get_assets_root_path()
except Exception as e:
    print(f"[CANH BAO] get_assets_root_path loi ({e})")
    ISAAC_ROOT = None
if not ISAAC_ROOT:
    ISAAC_ROOT = "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.1"
print("Isaac asset root:", ISAAC_ROOT)

S3 = "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets"
RACK = f"{S3}/ArchVis/Industrial/Racks/RackLarge_A1.usd"
CONVEYOR = f"{ISAAC_ROOT}/Isaac/Props/Conveyors/ConveyorBelt_A08.usd"
PALLET = f"{ISAAC_ROOT}/Isaac/Environments/Simple_Warehouse/Props/SM_PaletteA_01.usd"
BOX = f"{S3}/ArchVis/Industrial/Containers/Cardboard/Cardbox_D1.usd"
FORKLIFT = f"{S3}/DigitalTwin/Assets/Warehouse/Equipment/Forklifts/Forklift_C/Forklift_C01_PR_V_NVD_01.usd"

# ------------------------------------------------------------
# PARAMETERS
# ------------------------------------------------------------
W, D = 120.0, 80.0
WALL_H, WALL_T = 8.0, 0.4

# ------------------------------------------------------------
# STAGE
# ------------------------------------------------------------
stage = Usd.Stage.CreateInMemory()
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)

physics_scene = UsdPhysics.Scene.Define(stage, "/World_PhysicsScene")
physics_scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
physics_scene.CreateGravityMagnitudeAttr().Set(9.81)


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def cube(path, pos, size):
    prim = UsdGeom.Cube.Define(stage, path)
    prim.CreateSizeAttr(1.0)
    api = UsdGeom.XformCommonAPI(prim)
    api.SetTranslate(Gf.Vec3d(*pos))
    api.SetScale(Gf.Vec3f(*size))
    return prim.GetPrim()


def paint(prim, rgb):
    UsdGeom.Gprim(prim).CreateDisplayColorAttr([Gf.Vec3f(*rgb)])


_mpu_cache = {}


def asset_mpu(url):
    if url not in _mpu_cache:
        s = Usd.Stage.Open(url, Usd.Stage.LoadNone)
        _mpu_cache[url] = UsdGeom.GetStageMetersPerUnit(s) if s else 1.0
    return _mpu_cache[url]


def reference(path, asset_url, pos, rot_z=0.0, scale=1.0):
    parent = UsdGeom.Xform.Define(stage, path)
    p_api = UsdGeom.XformCommonAPI(parent)
    p_api.SetTranslate(Gf.Vec3d(*pos))
    p_api.SetRotate(Gf.Vec3f(0, 0, rot_z), UsdGeom.XformCommonAPI.RotationOrderXYZ)
    p_api.SetScale(Gf.Vec3f(scale, scale, scale))

    model = UsdGeom.Xform.Define(stage, path + "/Model")
    model.GetPrim().GetReferences().AddReference(asset_url)
    m = asset_mpu(asset_url)
    UsdGeom.XformCommonAPI(model).SetScale(Gf.Vec3f(m, m, m))
    return parent.GetPrim()


# Actual asset models are required in the default mode. GEOMETRY is explicit.
ASSET_MODE = os.environ.get('ASSET_MODE', 'models').lower()
if ASSET_MODE not in ('models', 'geometry'):
    raise ValueError('ASSET_MODE must be models or geometry')
import json
from pathlib import Path
_manifest_path = Path(os.path.expanduser(os.environ.get(
    'ASSET_MANIFEST', str(ASSET_MANIFEST))))
_manifest = json.loads(_manifest_path.read_text()) if _manifest_path.exists() else {}
MODEL_ASSETS = {
    'rack': RACK, 'box': BOX, 'conveyor': CONVEYOR, 'pallet': PALLET,
    'forklift': f'{ISAAC_ROOT}/Isaac/Props/Forklift/forklift.usd',
    'arm': f'{ISAAC_ROOT}/Isaac/Robots/UniversalRobots/ur10/ur10.usd',
}
MODEL_ASSETS.update(_manifest.get('assets', {}))
for _kind in tuple(MODEL_ASSETS):
    MODEL_ASSETS[_kind] = os.path.expanduser(os.environ.get(
        'ASSET_' + _kind.upper(), MODEL_ASSETS[_kind]))
for _kind in ('worker', 'truck', 'packing_table', 'crane', 'fan', 'entrance', 'conveyor_packing', 'wall_panel', 'ceiling_light'):
    if os.environ.get('ASSET_' + _kind.upper()):
        MODEL_ASSETS[_kind] = os.path.expanduser(os.environ['ASSET_' + _kind.upper()])
if ASSET_MODE == 'models' and not LITE and _manifest.get('errors'):
    raise RuntimeError(f'Asset download incomplete: {_manifest_path}. '
                       'Run build_warehouse_map.sh --download again.')
if ASSET_MODE == 'models' and not LITE:
    missing_kinds = sorted(set(('worker', 'packing_table', 'crane', 'fan', 'entrance',
                                'conveyor_packing', 'wall_panel')) - MODEL_ASSETS.keys())
    if missing_kinds:
        raise RuntimeError('Requested models missing from manifest: ' + ', '.join(missing_kinds))
if ASSET_MODE == 'models' and not LITE:
    WALL_H, WALL_T = 11.1, 0.74
_model_stages = {}
_model_counts = {}


def model_asset(path, kind, pos, size, rot_z=0.0, stretch=False, anchor_origin=False):
    """Validate asset, convert native units/up axis, center XY and ground Z.

    Factory props are static; only Ridgeback robots keep their dynamics.
    Stretch is used for belt modules/boxes, uniform fit for racks/vehicles/arms.
    """
    url = MODEL_ASSETS[kind]
    if url not in _model_stages:
        asset_stage = Usd.Stage.Open(url)
        if asset_stage is None or not asset_stage.GetDefaultPrim():
            raise RuntimeError(f'Asset missing/defaultPrim invalid: {kind}: {url}')
        bound = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [
            UsdGeom.Tokens.default_, UsdGeom.Tokens.render]).ComputeWorldBound(
                asset_stage.GetDefaultPrim()).ComputeAlignedRange()
        if bound.IsEmpty() or not any(p.IsA(UsdGeom.Mesh) for p in Usd.PrimRange(
                asset_stage.GetDefaultPrim(), Usd.TraverseInstanceProxies())):
            raise RuntimeError(f'Asset geometry/payload not loaded: {kind}: {url}')
        _model_stages[url] = asset_stage
        print('MODEL VERIFIED', kind, url, 'mpu=', UsdGeom.GetStageMetersPerUnit(asset_stage),
              'bbox native=', bound.GetSize())
    asset_stage = _model_stages[url]
    wrapper = UsdGeom.Xform.Define(stage, path)
    axes = UsdGeom.Xform.Define(stage, path + '/UnitsAndAxes')
    ax = UsdGeom.XformCommonAPI(axes)
    mpu = UsdGeom.GetStageMetersPerUnit(asset_stage)
    ax.SetScale(Gf.Vec3f(mpu, mpu, mpu))
    up = UsdGeom.GetStageUpAxis(asset_stage)
    ax.SetRotate(Gf.Vec3f(90 if up == UsdGeom.Tokens.y else 0, 0, 0))
    model = UsdGeom.Xform.Define(stage, path + '/UnitsAndAxes/Model')
    model.GetPrim().GetReferences().AddReference(url)
    physics_variant = model.GetPrim().GetVariantSets().GetVariantSet('Physics')
    if 'none' in physics_variant.GetVariantNames():
        physics_variant.SetVariantSelection('none')
    while True:
        instances = [p for p in Usd.PrimRange(model.GetPrim()) if p.IsInstance()]
        if not instances:
            break
        for prim in instances:
            prim.SetInstanceable(False)
    if kind == 'fan':
        # Adapt the supplied portable drum fan for a fixed wall bracket.
        for prim in list(Usd.PrimRange(model.GetPrim())):
            if prim.GetName() in ('sm_drumfan_a01_wheelsbody_01',
                                   'sm_drumfan_a01_wheels_01',
                                   'sm_drumfan_a01_cables_01'):
                prim.SetActive(False)
    for prim in Usd.PrimRange(model.GetPrim()):
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            prim.RemoveAPI(UsdPhysics.ArticulationRootAPI)
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            UsdPhysics.RigidBodyAPI(prim).CreateRigidBodyEnabledAttr(False)
        if prim.IsA(UsdPhysics.Joint):
            UsdPhysics.Joint(prim).CreateJointEnabledAttr(False)
    bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [
        UsdGeom.Tokens.default_, UsdGeom.Tokens.render]).ComputeWorldBound(wrapper.GetPrim()).ComputeAlignedRange()
    dimensions = bb.GetSize()
    # Canonical long-axis alignment precedes the requested placement yaw.
    auto_yaw = 0
    if kind in ('rack', 'forklift', 'crane', 'packing_table', 'conveyor',
                'conveyor_packing', 'wall_panel') and dimensions[1] > dimensions[0]:
        auto_yaw = 90
    ax.SetRotate(Gf.Vec3f(90 if up == UsdGeom.Tokens.y else 0, 0, rot_z+auto_yaw))
    bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [
        UsdGeom.Tokens.default_, UsdGeom.Tokens.render]).ComputeWorldBound(wrapper.GetPrim()).ComputeAlignedRange()
    dimensions = bb.GetSize()
    if any(v <= 1e-6 for v in dimensions):
        raise RuntimeError(f'Invalid dimensions {kind}: {dimensions}')
    scales = [size[j]/dimensions[j] for j in range(3)]
    if not stretch:
        scales = [min(scales)] * 3
        if kind in ('arm', 'worker', 'packing_table', 'fan', 'ceiling_light'):
            scales = [min(1.0, scales[0])] * 3
    api = UsdGeom.XformCommonAPI(wrapper)
    api.SetScale(Gf.Vec3f(*scales))
    center, mn = bb.GetMidpoint(), bb.GetMin()
    api.SetTranslate(Gf.Vec3d(pos[0]-(0 if anchor_origin else center[0]*scales[0]),
                            pos[1]-(0 if anchor_origin else center[1]*scales[1]),
                            pos[2]-mn[2]*scales[2]))
    if kind in ('entrance', 'crane'):
        # Keep door/gantry openings traversable; a bounding box would seal them.
        for prim in Usd.PrimRange(model.GetPrim()):
            if prim.IsA(UsdGeom.Mesh):
                UsdPhysics.CollisionAPI.Apply(prim)
                UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr('none')
    else:
        collider = cube(path + '/StaticCollider',
                        (center[0], center[1], center[2]), tuple(dimensions))
        UsdGeom.Imageable(collider).CreatePurposeAttr(UsdGeom.Tokens.guide)
        UsdPhysics.CollisionAPI.Apply(collider)
    _model_counts[kind] = _model_counts.get(kind, 0) + 1
    return wrapper.GetPrim()


# ------------------------------------------------------------
# HIERARCHY
# ------------------------------------------------------------
for p in ["/Warehouse", "/Warehouse/Architecture", "/Warehouse/Zones",
          "/Warehouse/Assets", "/Warehouse/Assets/Racks",
          "/Warehouse/Assets/Conveyors", "/Warehouse/Assets/Pallets",
          "/Warehouse/Assets/Boxes", "/Warehouse/Assets/Forklifts",
          "/Warehouse/Lighting"]:
    UsdGeom.Xform.Define(stage, p)

# ------------------------------------------------------------
# FLOOR + WALLS
# ------------------------------------------------------------
floor = cube("/Warehouse/Architecture/Floor", (W / 2, D / 2, -0.15), (W, D, 0.30))
paint(floor, (0.62, 0.62, 0.60))   # be tong sang
# San chi de NHIN (khong collision). Va cham dung mat phang (nhu Create > Physics > Ground Plane).
from pxr import UsdShade
cplane = UsdGeom.Plane.Define(stage, "/Warehouse/Architecture/CollisionPlane")
cplane.CreateAxisAttr("Z")
cplane.CreatePurposeAttr(UsdGeom.Tokens.guide)       # an khoi render
UsdPhysics.CollisionAPI.Apply(cplane.GetPrim())
floor_mat = UsdShade.Material.Define(stage, "/Warehouse/Architecture/FloorPhysMat")
_pm = UsdPhysics.MaterialAPI.Apply(floor_mat.GetPrim())
_pm.CreateStaticFrictionAttr(0.8)
_pm.CreateDynamicFrictionAttr(0.8)
_pm.CreateRestitutionAttr(0.0)
UsdShade.MaterialBindingAPI.Apply(cplane.GetPrim()).Bind(
    floor_mat, UsdShade.Tokens.weakerThanDescendants, "physics")

wall_north = cube("/Warehouse/Architecture/Wall_North", (W / 2, D, WALL_H / 2), (W, WALL_T, WALL_H))
wall_south = cube("/Warehouse/Architecture/Wall_South", (W / 2, 0, WALL_H / 2), (W, WALL_T, WALL_H))
wall_west = cube("/Warehouse/Architecture/Wall_West", (0, D / 2, WALL_H / 2), (WALL_T, D, WALL_H))
wall_east = cube("/Warehouse/Architecture/Wall_East", (W, D / 2, WALL_H / 2), (WALL_T, D, WALL_H))

for _w in (wall_north, wall_south, wall_west, wall_east):
    paint(_w, (0.80, 0.80, 0.82))

# Layout theo anh: bac = ke cao, tay = lap rap, nam = dong goi,
# dong = dock + phong dieu khien. Dai y=32..48 danh rieng cho robot.
from pxr import UsdShade
import math

STEEL = (0.16, 0.22, 0.27)
ORANGE = (0.95, 0.32, 0.035)
YELLOW = (0.98, 0.75, 0.06)
BLUE = (0.055, 0.28, 0.45)
BOX_COLORS = [(0.68, 0.48, 0.27), (0.79, 0.62, 0.39), (0.88, 0.75, 0.52)]


def solid(path, pos, size, color, collision=True):
    p = cube(path, pos, size)
    paint(p, color)
    if collision:
        UsdPhysics.CollisionAPI.Apply(p)
    return p


def beam(path, a, b, width, color=STEEL):
    a, b = Gf.Vec3d(*a), Gf.Vec3d(*b)
    p = UsdGeom.Cylinder.Define(stage, path)
    p.CreateRadiusAttr(width / 2)
    p.CreateHeightAttr((b - a).GetLength())
    xf = UsdGeom.Xformable(p)
    xf.AddTranslateOp().Set((a + b) / 2)
    q = Gf.Rotation(Gf.Vec3d(0, 0, 1), (b - a).GetNormalized()).GetQuat()
    xf.AddOrientOp().Set(Gf.Quatf(q))
    paint(p.GetPrim(), color)
    return p.GetPrim()


def line(path, x, y, sx, sy):
    solid(path, (x, y, 0.0015), (sx, sy, 0.003), YELLOW, False)


def outline(path, x, y, sx, sy):
    for j, yy in enumerate((y - sy/2, y + sy/2)):
        line(path + f'/H{j}', x, yy, sx, 0.12)
    for j, xx in enumerate((x - sx/2, x + sx/2)):
        line(path + f'/V{j}', xx, y, 0.12, sy)


def belt(path, x, y, length, kind="conveyor"):
    if ASSET_MODE == 'models':
        if kind == 'conveyor_packing':
            belt(path+'/Straight', x, y, length)
            # A61 is a level scanning conveyor; its tall housing is not a ramp.
            scan=model_asset(path+'/ScanningTransfer', kind,
                        (x+length/2+2,y,0), (4.0,1.6,2.4))
            from factory_surfaces import roller_top,scanner_alignment,translate_world
            top=roller_top(stage.GetPrimAtPath(path+'/Straight/Module0'))
            translate_world(scan,scanner_alignment(scan,top,y))
            worker(path+'/MachineOperator', x+length/2+1.5, y+2.2)
            return
        count = max(1, round(length / 2.0))
        pitch = length / count
        for j in range(count):
            model_asset(path+f'/Module{j}', kind,
                        (x-length/2+(j+0.5)*pitch,y,0), (pitch,1.4,1.2))
        from factory_surfaces import roller_top,CONTACT_GAP
        top=roller_top(stage.GetPrimAtPath(path+'/Module0'))
        for j in range(int(length/2.8)):
            model_asset(path+f'/Parcel{j}', 'box',
                        (x-length/2+1.3+j*2.8,y,top+CONTACT_GAP), (0.85,0.7,0.65), stretch=True)
        return
    solid(path+'/Bed', (x,y,0.95), (length,1.4,0.22), STEEL)
    for side in (-0.76,0.76):
        solid(path+('/RailL' if side<0 else '/RailR'), (x,y+side,1.08), (length,0.10,0.16), (0.7,0.74,0.75))
    for j, dx in enumerate((-length/2+0.5,length/2-0.5)):
        for k, dy in enumerate((-0.5,0.5)):
            solid(path+f'/Leg{j}_{k}', (x+dx,y+dy,0.45), (0.12,0.12,0.9), STEEL)
    for j in range(int(length/0.5)):
        xx=x-length/2+0.25+j*0.5
        solid(path+f'/Roller{j}', (xx,y,1.085), (0.08,1.30,0.045), (0.55,0.59,0.6),False)
    for j in range(int(length/2.8)):
        solid(path+f'/Parcel{j}', (x-length/2+1.3+j*2.8,y,1.42), (0.85,0.7,0.65), BOX_COLORS[j%3])


def worker(path, x, y):
    if ASSET_MODE == 'models' and 'worker' in MODEL_ASSETS:
        model_asset(path, 'worker', (x,y,0), (0.75,0.75,1.85), rot_z=-90)
        return
    # Hinh nhan lap rap: ao xanh, mu bao ho, chan/tay tach rieng.
    solid(path+'/Body',(x,y,1.12),(0.40,0.28,0.60),BLUE,False)
    for j, dx in enumerate((-0.12,0.12)):
        beam(path+f'/Leg{j}',(x+dx,y,0.15),(x+dx,y,0.84),0.14)
        beam(path+f'/Arm{j}',(x+dx*2,y,1.35),(x+dx*3,y+0.20,0.95),0.12,BLUE)
    sphere=UsdGeom.Sphere.Define(stage,path+'/Head')
    sphere.CreateRadiusAttr(0.18)
    UsdGeom.XformCommonAPI(sphere).SetTranslate(Gf.Vec3d(x,y,1.64))
    paint(sphere.GetPrim(),(0.82,0.62,0.43))
    solid(path+'/Helmet',(x,y,1.80),(0.4,0.36,0.10),YELLOW,False)


def arm(path,x,y):
    if ASSET_MODE == 'models':
        solid(path+'/Pedestal',(x,y,0.55),(0.8,0.8,1.1),STEEL)
        model_asset(path+'/N220_27','arm',(x,y,1.1),(3.2,3.2,3.2), rot_z=90, anchor_origin=True)
        return
    solid(path+'/Pedestal',(x,y,0.55),(0.8,0.8,1.1),STEEL)
    points=[(x,y,1.1),(x,y,1.7),(x+0.65,y,2.65),(x+1.45,y,2.15),(x+1.65,y,1.55)]
    for j,(a,b) in enumerate(zip(points,points[1:])):
        beam(path+f'/Link{j}',a,b,0.25,ORANGE)
    for j,p in enumerate(points[1:-1]):
        s=UsdGeom.Sphere.Define(stage,path+f'/Joint{j}')
        s.CreateRadiusAttr(0.22)
        UsdGeom.XformCommonAPI(s).SetTranslate(Gf.Vec3d(*p))
        paint(s.GetPrim(),ORANGE)


def pallet_load(path, x, y, layers=3):
    """Stocked pallet at native pallet size; keep gaps between carton stacks."""
    model_asset(path+'/Pallet', 'pallet', (x,y,0), (1.25,1.0,0.22))
    for level in range(layers):
        for col in range(2):
            for side in range(2):
                model_asset(path+f'/Box{level}_{col}_{side}', 'box',
                            (x+(col-.5)*.58,y+(side-.5)*.38,.22+level*.44),
                            (.56,.36,.44), stretch=True)


rack_positions, conveyors, pallet_positions, box_positions, forklift_positions = [], [], [], [], []
if not LITE:
    # Two separate rack blocks: central aisle x=58.75..64.25 (5.5 m).
    rack_columns = [('Left',j,x) for j,x in enumerate((28,37,46,55))]
    rack_columns += [('Right',j,x) for j,x in enumerate((68,77,86,95))]
    for row,y in enumerate((52.0,57.5,63.0,68.5,74.0)):
        for side,col,x in rack_columns:
            root=f'/Warehouse/Assets/Racks/{side}/Row{row}_Bay{col}'
            rack_positions.append((x,y,0))
            if ASSET_MODE == 'models':
                model_asset(root+'/Rack', 'rack', (x,y,0), (7.5,4.8,8.8))
                # Stock rack is referenced with its own shelf/cargo geometry.
                continue
            for j,dx in enumerate((-3.7,3.7)):
                for k,dy in enumerate((-1.15,1.15)):
                    solid(root+f'/Post{j}_{k}',(x+dx,y+dy,4.4),(0.16,0.16,8.8),BLUE)
            for level,z in enumerate((0.35,2.35,4.35,6.35,8.35)):
                solid(root+f'/Shelf{level}',(x,y,z),(7.5,2.5,0.13),ORANGE)
                if level==4:
                    continue
                for box in range(5):
                    bx=x-2.95+box*1.46
                    solid(root+f'/Load{level}_{box}',(bx,y,z+0.82),(1.30,2.10,1.48),BOX_COLORS[(row+col+level+box)%3])
            beam(root+'/Brace',(x-3.7,y+1.18,0.4),(x+3.7,y+1.18,8.4),0.07)
    # Portable gantries supplied by user, in open staging areas.
    if ASSET_MODE == 'models':
        for j,(x,y) in enumerate(((16,65),(112,53))):
            model_asset(f'/Warehouse/Zones/Crane/Gantry{j}', 'crane',
                        (x,y,0), (11,6,10), rot_z=180 if j == 1 else 0)
    else:
        # Can truc cam trong loi doc ke.
        for j,x in enumerate((24.0,103.0)):
            solid(f'/Warehouse/Zones/Crane/Column{j}',(x,63,5.4),(0.6,0.6,10.8),ORANGE)
        solid('/Warehouse/Zones/Crane/Bridge',(63.5,63,10.4),(80,0.65,0.8),ORANGE)
        solid('/Warehouse/Zones/Crane/Trolley',(69,63,9.7),(2,1.3,0.6),STEEL)
        beam('/Warehouse/Zones/Crane/Cable',(69,63,9.4),(69,63,4.2),0.06)
    # Lap rap phia tay, ben duoi hanh lang ngang.
    for row,y in enumerate((10.0,23.0)):
        root=f'/Warehouse/Zones/Assembly/Line{row}'
        belt(root+'/Conveyor',26,y,38)
        conveyors.append((26,y,0,0))
        outline(root+'/Mark',26,y,42,9)
        for j,x in enumerate((11,21,31,41)):
            arm(root+f'/Arm{j}',x,y-2.4)
            worker(root+f'/Worker{j}',x+2,y+2.1)
        solid(root+'/Cabinet',(6,y+2.4,1.1),(1.0,0.8,2.2),(0.8,0.83,0.83))
    # Dong goi phia nam: bang chuyen, ban, cong quet.
    for row,y in enumerate((8.0,21.0)):
        root=f'/Warehouse/Zones/Packing/Line{row}'
        belt(root+'/Belt',75,y,39, kind='conveyor_packing')
        conveyors.append((75,y,0,0))
        outline(root+'/Mark',77,y,47,9)
        for j,x in enumerate((62,75,88)):
            if ASSET_MODE == 'models':
                model_asset(root+f'/Table{j}', 'packing_table', (x,y+2.8,0),
                            (2.6,1.2,2.1))
            else:
                solid(root+f'/Table{j}',(x,y+2.8,0.9),(2.2,1.3,0.15),(0.65,0.7,0.72))
                for k,dx in enumerate((-0.85,0.85)):
                    solid(root+f'/TableLeg{j}_{k}',(x+dx,y+2.8,0.43),(0.12,1.0,0.86),STEEL)
            worker(root+f'/Worker{j}',x,y+4)
            for k,dy in enumerate((-1,1)):
                solid(root+f'/ScannerPost{j}_{k}',(x,y+dy,1.5),(0.25,0.25,3), (0.77,0.82,0.83))
            solid(root+f'/ScannerTop{j}',(x,y,2.9),(0.45,2.3,0.35),(0.77,0.82,0.83))
            solid(root+f'/Screen{j}',(x-0.1,y-1.14,1.8),(0.4,0.05,0.35),BLUE,False)
    # Dock dong: wall openings va xe tai o ben ngoai kho.
    stage.RemovePrim('/Warehouse/Architecture/Wall_East')
    for j,(ya,yb) in enumerate(((0,5),(13,18),(26,32),(48,80))):
        solid(f'/Warehouse/Architecture/Wall_East_{j}',(120,(ya+yb)/2,4),(0.4,yb-ya,8),(0.65,0.69,0.72))
    # Close the unused opening beside the truck docks; only the two bays stay open.
    solid('/Warehouse/Architecture/DockWallInfill',(120,40,WALL_H/2),
          (WALL_T,16,WALL_H),(0.8,0.8,0.82))
    for j,y in enumerate((9.0,22.0)):
        root=f'/Warehouse/Zones/Dock/Bay{j}'
        solid(root+'/Header',(120,y,6.8),(0.6,8,2.4),STEEL)
        if WALL_H > 8:
            solid(root+'/UpperWall',(120,y,(8+WALL_H)/2),
                  (WALL_T,8,WALL_H-8),(0.8,0.8,0.82))
        for k,dy in enumerate((-4,4)):
            solid(root+f'/DoorPost{k}',(120,y+dy,2.8),(0.7,0.35,5.6),STEEL)
        solid(root+'/Apron',(131,y,-0.15),(22,11,0.3),(0.45,0.47,0.48))
        if ASSET_MODE == 'models' and 'truck' in MODEL_ASSETS:
            model_asset(root+'/Truck', 'truck', (132,y,0), (19,3.8,5))
        else:
            solid(root+'/Truck/Trailer',(130,y,2.3),(14,3.6,4.2),BLUE if j==0 else (0.72,0.75,0.77))
            solid(root+'/Truck/Cab',(139,y,1.9),(3.8,3.6,3.4),ORANGE)
            solid(root+'/Truck/Windshield',(140.92,y,2.6),(0.04,2.8,1.2),(0.15,0.36,0.44),False)
            for k,x in enumerate((125,133,139)):
                for side,dy in enumerate((-1.85,1.85)):
                    beam(root+f'/Truck/Wheel{k}_{side}',(x,y+dy-0.18,0.65),(x,y+dy+0.18,0.65),1.15,(0.055,0.06,0.07))
        for k,x in enumerate((105,110)):
            if ASSET_MODE == 'models':
                model_asset(root+f'/Pallet{k}', 'pallet', (x,y,0), (1.25,1.0,0.22))
                for level in range(3):
                    for col in range(2):
                        for side in range(2):
                            model_asset(root+f'/Load{k}/Box{level}_{col}_{side}', 'box',
                                        (x+(col-.5)*.58,y+(side-.5)*.38,.22+level*.44),
                                        (.56,.36,.44), stretch=True)
            else:
                solid(root+f'/Load{k}',(x,y,0.7),(2,2,1.4),BOX_COLORS[k])
        outline(root+'/Mark',109,y,15,8)
    # Xe nang hinh hoc o khu dock.
    for j,(x,y) in enumerate(((112,16),(108,28),(20,55))):
        root=f'/Warehouse/Zones/Forklifts/F{j}'
        forklift_positions.append((x,y,0,0))
        if ASSET_MODE == 'models':
            model_asset(root+'/Model', 'forklift', (x,y,0), (4.0,1.8,3.6))
            continue
        solid(root+'/Body',(x,y,0.7),(2.3,1.3,1.0),ORANGE)
        solid(root+'/Seat',(x,y,1.45),(0.6,0.7,0.6),STEEL)
        for k,dy in enumerate((-0.55,0.55)):
            solid(root+f'/Mast{k}',(x+1.3,y+dy,1.8),(0.16,0.16,3.6),STEEL)
            solid(root+f'/Fork{k}',(x+2.1,y+dy,0.18),(1.7,0.18,0.12),STEEL)
            for m,dx in enumerate((-0.8,0.8)):
                beam(root+f'/Wheel{k}_{m}',(x+dx,y+dy-0.16,0.4),(x+dx,y+dy+0.16,0.4),0.7,(0.06,0.06,0.06))
    if ASSET_MODE == 'models':
        # Extra humanoids at receiving/staging, outside forklift parking spaces.
        for j,(x,y) in enumerate(((19,57),(19,72),(104,18),(114,26.7))):
            worker(f'/Warehouse/Zones/Staff/Worker{j}', x, y)
        for j,x in enumerate((18,42,66,90,114)):
            model_asset(f'/Warehouse/Architecture/Fans/Fan{j}', 'fan',
                        (x,79.10,7.2), (1.4,1.0,1.4), rot_z=0)
            mount = f'/Warehouse/Architecture/Fans/Mount{j}'
            solid(mount+'/WallPlate',(x,79.58,7.35),(0.85,0.10,1.05),STEEL)
            for side,dx in enumerate((-0.28,0.28)):
                beam(mount+f'/Arm{side}',(x+dx,79.58,7.28),
                     (x+dx,79.05,7.28),0.075)
                beam(mount+f'/Brace{side}',(x+dx,79.58,6.90),
                     (x+dx,79.05,7.28),0.065)
        # Insert the complete entrance module into the west wall.
        stage.RemovePrim('/Warehouse/Architecture/Wall_West')
        entrance = model_asset('/Warehouse/Architecture/Entrance', 'entrance',
                               (0,16,0), (4.8,12,WALL_H), rot_z=0)
        er = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [
            UsdGeom.Tokens.default_, UsdGeom.Tokens.render]).ComputeWorldBound(entrance).ComputeAlignedRange()
        for j,(lo,hi) in enumerate(((0,er.GetMin()[1]),(er.GetMax()[1],D))):
            solid(f'/Warehouse/Architecture/Wall_West_{j}', (0,(lo+hi)/2,4),
                  (WALL_T,hi-lo,8), (0.8,0.8,0.82))
    if ASSET_MODE == 'models':
        # Receiving/storage clusters. Reserve the gantry footprint and forklift bay.
        loads = [(x,y) for y in (51.5,58.5) for x in (6,10,14,18,22)]
        loads += [(x,55) for x in (6,10,14)]
        loads += [(x,y) for y in (72,75.5) for x in (6,10,14,18,22)]
        loads += [(16,65),(112,53)]  # workpiece beneath the left gantry
        loads += [(x,78) for x in range(30,97,6) if x != 60]
        loads += [(x,16.3) for x in (9,19,29,39)]
        loads += [(x,15.2) for x in (56,69,82,95)]
        loads += [(x,28.5) for x in (58,64,70,76,82,88,94)]
        loads += [(x,56.8) for x in (104,109,114,117)]
        for j,(x,y) in enumerate(loads):
            pallet_load(f'/Warehouse/Zones/Staging/Load{j:02d}', x, y)
        for j,(x,y,sx,sy) in enumerate(((13.5,55,22,11), (14,74,22,8),
                                       (76,28.5,41,2.6), (111,56.8,17,2.4))):
            outline(f'/Warehouse/Zones/Staging/Mark{j}', x,y,sx,sy)
        outline('/Warehouse/Zones/Staging/ForkliftBay',20,55,5,3)
        for j,(x,y) in enumerate(((16,65),(112,53))):
            outline(f'/Warehouse/Zones/Crane/WorkCell{j}', x,y,12,6)
        for j,x in enumerate((59.25,63.75)):
            line(f'/Warehouse/Zones/Traffic/RackAisle{j}',x,64,0.12,30)

    # Phong dieu khien kinh tren san lung goc dong bac.
    root='/Warehouse/Zones/ControlRoom'
    solid(root+'/Deck',(112,69,5.0),(14,18,0.4),STEEL)
    solid(root+'/Roof',(112,69,9.2),(14.5,18.5,0.3),STEEL)
    glass=UsdShade.Material.Define(stage,root+'/GlassMaterial')
    shader=UsdShade.Shader.Define(stage,root+'/GlassMaterial/Shader')
    shader.CreateIdAttr('UsdPreviewSurface')
    from pxr import Sdf
    shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.35,0.65,0.75))
    shader.CreateInput('opacity',Sdf.ValueTypeNames.Float).Set(0.24)
    shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(0.12)
    glass.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
    for j,(pos,size) in enumerate((((105,69,7.1),(0.08,18,3.8)),((112,60,7.1),(14,0.08,3.8)),((112,78,7.1),(14,0.08,3.8)))):
        p=solid(root+f'/Glass{j}',pos,size,(0.3,0.6,0.7))
        UsdShade.MaterialBindingAPI.Apply(p).Bind(glass)
    for j,x in enumerate((105,112,119)):
        for k,y in enumerate((60,69,78)):
            solid(root+f'/Post{j}_{k}',(x,y,4.6),(0.22,0.22,9.2),STEEL)
    for j in range(20):
        solid(root+f'/Stair{j}',(101,60+j*0.45,0.125+j*0.25),(2,0.5,0.25),STEEL)
    for j,y in enumerate((64,69,74)):
        solid(root+f'/Console{j}',(114,y,5.9),(3,1.2,1.4),(0.5,0.55,0.58))
        solid(root+f'/Monitor{j}',(113.5,y,7),(0.15,1.1,0.8),BLUE,False)
    # Cot + cua so tren tuong bac/tay; gian thep de ho mai nhu anh.
    for j,x in enumerate(range(0,121,12)):
        solid(f'/Warehouse/Architecture/Column_N{j}',(x,79.5,5.8),(0.35,0.4,11.6),STEEL)
        if x<120:
            solid(f'/Warehouse/Architecture/Window_N{j}',(x+6,79.76,6.3),(10.8,0.06,2.5),(0.5,0.72,0.78),False)
    for j,y in enumerate(range(0,81,10)):
        solid(f'/Warehouse/Architecture/Column_W{j}',(0.5,y,5.8),(0.4,0.35,11.6),STEEL)
        if y<80:
            solid(f'/Warehouse/Architecture/Window_W{j}',(0.24,y+5,6.3),(0.06,8.8,2.5),(0.5,0.72,0.78),False)
    for row,y in enumerate((4,28,52,76)):
        root=f'/Warehouse/Architecture/Trusses/T{row}'
        beam(root+'/Lower',(0,y,10.4),(120,y,10.4),0.20)
        beam(root+'/Upper',(0,y,12.0),(120,y,12.0),0.20)
        for j in range(20):
            beam(root+f'/Web{j}',(j*6,y,10.4 if j%2==0 else 12),(j*6+6,y,12 if j%2==0 else 10.4),0.12)
    for j,x in enumerate((0,24,48,72,96,120)):
        beam(f'/Warehouse/Architecture/Trusses/Long{j}',(x,0,11.6),(x,80,11.6),0.16)
    # Vach hanh lang nam ngoai dai chay, khong tao vat can.
    for j,y in enumerate((31.5,48.5)):
        line(f'/Warehouse/Zones/Traffic/Boundary{j}',60,y,116,0.16)
    for lane,y in enumerate((33,35.6,38.2,40.8,43.4,46)):
        for j in range(24):
            line(f'/Warehouse/Zones/Traffic/Lane{lane}/Dash{j}',3+j*4.8,y,1.4,0.06)

if not LITE and ASSET_MODE == 'models':
    def panel_run(path, start, end, yaw):
        length = math.hypot(end[0]-start[0],end[1]-start[1])
        count = max(1, math.ceil(length/6.0))
        dx,dy = (end[0]-start[0])/count, (end[1]-start[1])/count
        for j in range(count):
            model_asset(path+f'/Panel{j:02d}', 'wall_panel',
                        (start[0]+(j+.5)*dx,start[1]+(j+.5)*dy,0),
                        (abs(dx) if dx else WALL_T, abs(dy) if dy else WALL_T, WALL_H),
                        rot_z=yaw, stretch=True)

    # Read the actual cut spans so panels never seal a dock/entrance opening.
    wall_spans = [p for p in stage.GetPrimAtPath('/Warehouse/Architecture').GetChildren()
                  if p.GetName().startswith('Wall_') or p.GetName() == 'DockWallInfill']
    for prim in wall_spans:
        name = prim.GetName()
        r = UsdGeom.BBoxCache(Usd.TimeCode.Default(),[
            UsdGeom.Tokens.default_,UsdGeom.Tokens.render]).ComputeWorldBound(prim).ComputeAlignedRange()
        lo,hi = r.GetMin(),r.GetMax()
        if 'North' in name:
            start,end,yaw = (lo[0],D),(hi[0],D),180
        elif 'South' in name:
            start,end,yaw = (lo[0],0),(hi[0],0),0
        elif 'West' in name:
            start,end,yaw = (0,lo[1]),(0,hi[1]),-90
        else:
            start,end,yaw = (W,lo[1]),(W,hi[1]),90
        stage.RemovePrim(prim.GetPath())
        panel_run('/Warehouse/Architecture/WallPanels/'+name,start,end,yaw)
    for prim in list(stage.GetPrimAtPath('/Warehouse/Architecture').GetChildren()):
        if prim.GetName().startswith('Window_'):
            stage.RemovePrim(prim.GetPath())

# ------------------------------------------------------------
# ROBOT (chon bang bien moi truong ROBOT=create3 | tb4)
# ------------------------------------------------------------
UsdGeom.Xform.Define(stage, "/Warehouse/Robots")

if not ENV_ONLY:
    if ROBOT == "tb4":
        import glob
        _cands = sorted(glob.glob(os.path.expanduser("~/tb4/turtlebot4_clean*/*.usd*")))
        assert _cands, "Khong thay file USD cua TurtleBot4 trong ~/tb4"
        print("ROBOT USD:", _cands[0])
        bot_xf = UsdGeom.Xform.Define(stage, "/Warehouse/Robots/TB4_01")
        bot_xf.GetPrim().GetReferences().AddReference(_cands[0])
        _vs = bot_xf.GetPrim().GetVariantSets().GetVariantSet("Physics")
        _vs.SetVariantSelection("physx")
        print("TB4 Physics variant =", _vs.GetVariantSelection())
        # go khop co dinh giu xe vao the gioi (do importer tao ra)
        _roots = [p for p in Usd.PrimRange(bot_xf.GetPrim()) if p.GetName() == "root_joint"]
        for p in _roots:
            p.SetActive(False)
            print("TB4 tat", p.GetPath())
    elif ROBOT == "ridgeback":
        # Clearpath Ridgeback + tay UR5 (de di chuyen = 3 khop ao x, y, yaw; tay dung yen)
        RB_USD = os.path.expanduser(os.environ.get("ASSET_RIDGEBACK", MODEL_ASSETS.get("ridgeback", f"{ISAAC_ROOT}/Isaac/Robots/Clearpath/RidgebackUr/ridgeback_ur5.usd")))
        print("ROBOT USD:", RB_USD)
        NUM_ROBOTS = int(os.environ.get("ROBOTS", "6"))
        # xuat phat trong dai ngang giua kho (y 32-48): 3 xe ben trai, 3 xe ben phai, moi xe 1 lan rieng
        RB_POS = [(10.0, 33.0), (10.0, 38.2), (10.0, 43.4),
                  (110.0, 35.6), (110.0, 40.8), (110.0, 46.0)]
        assert 1 <= NUM_ROBOTS <= len(RB_POS)
        for _i in range(1, NUM_ROBOTS + 1):
            _xf = UsdGeom.Xform.Define(stage, f"/Warehouse/Robots/Ridgeback_{_i:02d}")
            _rb = UsdGeom.Xform.Define(stage, f"/Warehouse/Robots/Ridgeback_{_i:02d}/ridgeback")
            _rb.GetPrim().GetReferences().AddReference(RB_USD)
            if _i == 1:
                bot_xf = _xf
    else:
        ROBOT_USD = f"{ISAAC_ROOT}/Isaac/Robots/iRobot/Create3/create_3.usd"
        print("ROBOT USD:", ROBOT_USD)
        bot_xf = UsdGeom.Xform.Define(stage, "/Warehouse/Robots/Create3_01")
        _c3 = UsdGeom.Xform.Define(stage, "/Warehouse/Robots/Create3_01/create3")
        _c3.GetPrim().GetReferences().AddReference(ROBOT_USD)

    bot_api = UsdGeom.XformCommonAPI(bot_xf)
    bot_api.SetTranslate(Gf.Vec3d(60.0, 40.0, 0.0))
    # do day robot de ha xuong cham san
    _bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    _rng = _bb.ComputeWorldBound(bot_xf.GetPrim()).ComputeAlignedRange()
    if _rng.IsEmpty():
        print("[CANH BAO] Khong do duoc bbox robot, dat Z = 0")
        _z = 0.0
    else:
        _z = -_rng.GetMin()[2] + 0.002
        print(f"ROBOT {ROBOT} day z = {_rng.GetMin()[2]:.3f}, nang them {_z:.3f} m")
    bot_api.SetTranslate(Gf.Vec3d(60.0, 40.0, _z))
    if ROBOT == "ridgeback":
        for _i in range(1, NUM_ROBOTS + 1):
            UsdGeom.XformCommonAPI(stage.GetPrimAtPath(f"/Warehouse/Robots/Ridgeback_{_i:02d}")).SetTranslate(
                Gf.Vec3d(RB_POS[_i - 1][0], RB_POS[_i - 1][1], _z))
        print("ROBOT so luong:", NUM_ROBOTS)

# ------------------------------------------------------------
# LIGHTING
# ------------------------------------------------------------
dome = UsdLux.DomeLight.Define(stage, "/Warehouse/Lighting/EnvironmentLight")
dome.CreateIntensityAttr(600.0)
dome.CreateExposureAttr(0.0)

# Only the dome remains: no ceiling fixtures or rectangular light panels.

# ------------------------------------------------------------
# CAMERA
# ------------------------------------------------------------
camera = UsdGeom.Camera.Define(stage, "/Warehouse/Camera")
camera.CreateFocalLengthAttr(28.0)
camera.CreateClippingRangeAttr(Gf.Vec2f(0.1, 1000.0))
cam_api = UsdGeom.XformCommonAPI(camera)
cam_api.SetTranslate(Gf.Vec3d(165, -125, 145))
cam_api.SetRotate(Gf.Vec3f(49.0, 0.0, 35.0), UsdGeom.XformCommonAPI.RotationOrderXYZ)

# ------------------------------------------------------------
# SAVE
# ------------------------------------------------------------
# ===== COLLISION PATCH: va cham cho tuong, cot va moi model =====
UsdGeom.Xform.Define(stage, "/Warehouse/Colliders")
_bbc = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
_ncol = [0, 0]   # [tuong/cot, model]

for _p in stage.GetPrimAtPath("/Warehouse/Architecture").GetChildren():
    if _p.GetName().startswith(("Wall_", "DoorPost_", "Column_")):
        UsdPhysics.CollisionAPI.Apply(_p)
        _ncol[0] += 1

for _cat in ("Racks", "Conveyors", "Pallets", "Boxes", "Forklifts", "Props", "Safety"):
    if ASSET_MODE == 'models' and _cat == 'Racks':
        # Each rack already owns a collider; a block-sized box would seal its aisles.
        continue
    _root = stage.GetPrimAtPath(f"/Warehouse/Assets/{_cat}")
    if not _root:
        continue
    for _p in _root.GetChildren():
        if _p.GetName().startswith("Cone_"):
            continue
        _r = _bbc.ComputeWorldBound(_p).ComputeAlignedRange()
        if _r.IsEmpty():
            continue
        _mn, _mx = _r.GetMin(), _r.GetMax()
        _c = (_mn + _mx) * 0.5
        _s = _mx - _mn
        _cp = UsdGeom.Cube.Define(stage, f"/Warehouse/Colliders/{_cat}_{_p.GetName()}")
        _cp.CreateSizeAttr(1.0)
        _api = UsdGeom.XformCommonAPI(_cp)
        _api.SetTranslate(Gf.Vec3d(_c[0], _c[1], _c[2]))
        _api.SetScale(Gf.Vec3f(max(_s[0], 0.02), max(_s[1], 0.02), max(_s[2], 0.02)))
        _cp.CreatePurposeAttr(UsdGeom.Tokens.guide)
        UsdPhysics.CollisionAPI.Apply(_cp.GetPrim())
        _ncol[1] += 1
print("COLLISION tuong/cot:", _ncol[0], "| model:", _ncol[1])

from prepare_cycle_graph import mark_cycle_roads
if not LITE:
    mark_cycle_roads(stage)
stage.SetDefaultPrim(stage.GetPrimAtPath("/Warehouse"))
stage.GetRootLayer().customLayerData = {
    'asset_mode': ASSET_MODE, 'model_counts': json.dumps(_model_counts),
    'mobile_robot_count': NUM_ROBOTS if not ENV_ONLY and ROBOT == 'ridgeback' else 0,
    'rack_blocks': 'Left: x=24.25..58.75; Right: x=64.25..98.75; central aisle width 5.5 m',
    'asset_sources': json.dumps(MODEL_ASSETS),
    'pending_local_assets': json.dumps(_manifest.get('pending_local', {})),
    'remaining_procedural': 'roof trusses, control room, scanner gates' +
        (', workers' if 'worker' not in MODEL_ASSETS else '') +
        (', trucks' if 'truck' not in MODEL_ASSETS else '')}
stage.GetRootLayer().Export(OUTPUT)
print('ACTUAL MODEL INSTANCES:', _model_counts)
print('PROCEDURAL REMAINING:', stage.GetRootLayer().customLayerData['remaining_procedural'])

print("")
print("==============================================")
print(" Warehouse created successfully")
print("==============================================")
print(f"Output: {OUTPUT}")
print("SO KE:", len(rack_positions))
print("SO BANG CHUYEN:", len(conveyors))
print("SO PALLET:", _model_counts.get("pallet", len(pallet_positions)))
print("SO BOX (ngoai hang co san trong ke):", _model_counts.get("box", len(box_positions)))
print("SO XE NANG:", len(forklift_positions))
print("==============================================")

if simulation_app is not None:
    simulation_app.close()
