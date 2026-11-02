# add_ros2_ridgeback.py - graph ROS2 + lidar cho N robot Ridgeback+UR5 (robot1..robotN)
# Doc maps/warehouse_environment_models.usd -> maps/warehouse_ros2_ridgeback.usd
import os
from project_paths import ENVIRONMENT_USD, ROS2_USD, ASSET_MANIFEST
import json

from isaacsim.simulation_app import SimulationApp
app = SimulationApp({"headless": True})

from isaacsim.core.utils.extensions import enable_extension
for ext in ("omni.graph.action", "omni.graph.nodes", "isaacsim.core.nodes",
            "isaacsim.ros2.bridge", "isaacsim.sensors.experimental.rtx"):
    enable_extension(ext)
app.update()

import omni.graph.core as og
import omni.usd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics
from isaacsim.sensors.experimental.rtx import Lidar

N = int(os.environ.get("ROBOTS", "6"))
SRC = os.path.expanduser(os.environ.get("SRC", str(ENVIRONMENT_USD)))
DST = os.path.expanduser(os.environ.get("DST", str(ROS2_USD)))
LIN_DAMPING = 2000.0    # N.s/m
ANG_DAMPING = 50.0      # N.m.s/do
_manifest_path = os.path.expanduser(os.environ.get(
    "ASSET_MANIFEST", str(ASSET_MANIFEST)))
with open(_manifest_path) as _f:
    _asset_manifest = json.load(_f)
LIDAR_USD = os.path.expanduser(os.environ.get("LIDAR_USD",
    _asset_manifest.get("assets", {}).get("lidar", "")))
assert os.path.isfile(LIDAR_USD), "Tai lidar truoc: bash ~/warehouse_twin/scripts/build_warehouse_map.sh --download"
assert 1 <= N <= 6, "ROBOTS phai tu 1 den 6"
LIDAR_FRAME = "rplidar_link"

assert os.path.exists(SRC), "Khong thay %s. Tao bang: ROBOT=ridgeback ROBOTS=%d python.sh warehouse.py" % (SRC, N)
ctx = omni.usd.get_context()
print("OPEN", SRC, "->", ctx.open_stage(SRC))
for _ in range(10):
    app.update()
for _ in range(300):
    msg, loaded, total = ctx.get_stage_loading_status()
    if total == 0:
        break
    app.update()
stage = ctx.get_stage()
keys = og.Controller.Keys


def setup(i):
    NS = f"robot{i}"
    ART = f"/Warehouse/Robots/Ridgeback_{i:02d}/ridgeback"
    CHASSIS = f"{ART}/base_link"
    GRAPH = f"/Warehouse/ROS2_robot{i}"
    assert stage.GetPrimAtPath(ART), f"Khong thay robot tai {ART}"

    # drive: vi tri -> van toc
    for path, kind in ((f"{ART}/world/dummy_base_prismatic_x_joint", "linear"),
                       (f"{ART}/dummy_base_x/dummy_base_prismatic_y_joint", "linear"),
                       (f"{ART}/dummy_base_y/dummy_base_revolute_z_joint", "angular")):
        jp = stage.GetPrimAtPath(path)
        assert jp, f"Khong thay khop {path}"
        d = UsdPhysics.DriveAPI.Apply(jp, kind)
        d.CreateStiffnessAttr(0.0)
        d.CreateDampingAttr(LIN_DAMPING if kind == "linear" else ANG_DAMPING)
    print("DRIVE", NS, "ok")

    # vi tri lidar: mep truoc, tren mat than xe (tinh tu bbox base_link)
    bp = stage.GetPrimAtPath(CHASSIS)
    bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render]) \
        .ComputeWorldBound(bp).ComputeAlignedRange()
    inv = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(bp).GetInverse()
    mn, mx = bb.GetMin(), bb.GetMax()
    cs = [inv.Transform(Gf.Vec3d(x, y, z)) for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])]
    lo = [min(c[k] for c in cs) for k in range(3)]
    hi = [max(c[k] for c in cs) for k in range(3)]
    xyz = (hi[0] - 0.05, 0.5 * (lo[1] + hi[1]), hi[2] + 0.02)
    if os.environ.get("LIDAR_XYZ"):
        xyz = tuple(float(v) for v in os.environ["LIDAR_XYZ"].split(","))
    LP = f"{CHASSIS}/rplidar"
    if stage.GetPrimAtPath(LP):
        stage.RemovePrim(LP)
    Lidar.create(LP, usd_path=LIDAR_USD)
    for _ in range(5):
        app.update()
    UsdGeom.XformCommonAPI(stage.GetPrimAtPath(LP)).SetTranslate(Gf.Vec3d(*xyz))
    olid = next((p for p in Usd.PrimRange(stage.GetPrimAtPath(LP)) if p.GetTypeName() == "OmniLidar"), None)
    assert olid is not None, "Khong thay OmniLidar duoi " + LP
    print("LIDAR", NS, olid.GetPath(), "vi tri", tuple(round(v, 3) for v in xyz))

    if stage.GetPrimAtPath(GRAPH):
        stage.RemovePrim(GRAPH)
        for _ in range(5):
            app.update()

    nodes = [
        ("Tick", "omni.graph.action.OnPlaybackTick"),
        ("SimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
        ("SubJS", "isaacsim.ros2.bridge.ROS2SubscribeJointState"),
        ("Art", "isaacsim.core.nodes.IsaacArticulationController"),
        ("OdomCalc", "isaacsim.core.nodes.IsaacComputeOdometry"),
        ("OdomPub", "isaacsim.ros2.bridge.ROS2PublishOdometry"),
        ("WorldPose", "isaacsim.core.nodes.IsaacReadWorldPose"),
        ("WorldPosePub", "isaacsim.ros2.bridge.ROS2PublishOdometry"),
        ("TfPub", "isaacsim.ros2.bridge.ROS2PublishRawTransformTree"),
        ("RP", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
        ("LidarPub", "isaacsim.ros2.bridge.ROS2RtxLidarHelper"),
        ("TfLidar", "isaacsim.ros2.bridge.ROS2PublishRawTransformTree"),
    ]
    values = [
        ("SubJS.inputs:topicName", "joint_command"), ("SubJS.inputs:nodeNamespace", NS),
        ("Art.inputs:robotPath", ART),
        ("WorldPosePub.inputs:topicName", "warehouse_pose"),
        ("WorldPosePub.inputs:nodeNamespace", NS),
        ("WorldPosePub.inputs:odomFrameId", f"{NS}/map"),
        ("WorldPosePub.inputs:chassisFrameId", f"{NS}/base_link"),
        ("OdomPub.inputs:topicName", "odom"), ("OdomPub.inputs:nodeNamespace", NS),
        ("OdomPub.inputs:odomFrameId", f"{NS}/odom"), ("OdomPub.inputs:chassisFrameId", f"{NS}/base_link"),
        ("TfPub.inputs:topicName", "tf"),
        ("TfPub.inputs:parentFrameId", f"{NS}/odom"), ("TfPub.inputs:childFrameId", f"{NS}/base_link"),
        ("RP.inputs:width", 1), ("RP.inputs:height", 1),
        ("LidarPub.inputs:topicName", "scan"), ("LidarPub.inputs:nodeNamespace", NS),
        ("LidarPub.inputs:frameId", f"{NS}/{LIDAR_FRAME}"), ("LidarPub.inputs:type", "laser_scan"),
        ("TfLidar.inputs:topicName", "tf_static"), ("TfLidar.inputs:staticPublisher", True),
        ("TfLidar.inputs:parentFrameId", f"{NS}/base_link"),
        ("TfLidar.inputs:childFrameId", f"{NS}/{LIDAR_FRAME}"),
        ("TfLidar.inputs:translation", list(xyz)), ("TfLidar.inputs:rotation", [0.0, 0.0, 0.0, 1.0]),
    ]
    conns = [
        ("Tick.outputs:tick", "SubJS.inputs:execIn"),
        ("SubJS.outputs:execOut", "Art.inputs:execIn"),
        ("SubJS.outputs:jointNames", "Art.inputs:jointNames"),
        ("SubJS.outputs:velocityCommand", "Art.inputs:velocityCommand"),
        ("Tick.outputs:tick", "OdomCalc.inputs:execIn"),
        ("Tick.outputs:tick", "WorldPosePub.inputs:execIn"),
        ("WorldPose.outputs:translation", "WorldPosePub.inputs:position"),
        ("WorldPose.outputs:orientation", "WorldPosePub.inputs:orientation"),
        ("OdomCalc.outputs:linearVelocity", "WorldPosePub.inputs:linearVelocity"),
        ("OdomCalc.outputs:angularVelocity", "WorldPosePub.inputs:angularVelocity"),
        ("SimTime.outputs:simulationTime", "WorldPosePub.inputs:timeStamp"),
        ("Tick.outputs:tick", "OdomPub.inputs:execIn"),
        ("Tick.outputs:tick", "TfPub.inputs:execIn"),
        ("OdomCalc.outputs:position", "OdomPub.inputs:position"),
        ("OdomCalc.outputs:orientation", "OdomPub.inputs:orientation"),
        ("OdomCalc.outputs:linearVelocity", "OdomPub.inputs:linearVelocity"),
        ("OdomCalc.outputs:angularVelocity", "OdomPub.inputs:angularVelocity"),
        ("OdomCalc.outputs:position", "TfPub.inputs:translation"),
        ("OdomCalc.outputs:orientation", "TfPub.inputs:rotation"),
        ("SimTime.outputs:simulationTime", "OdomPub.inputs:timeStamp"),
        ("SimTime.outputs:simulationTime", "TfPub.inputs:timeStamp"),
        ("Tick.outputs:tick", "RP.inputs:execIn"),
        ("RP.outputs:execOut", "LidarPub.inputs:execIn"),
        ("RP.outputs:renderProductPath", "LidarPub.inputs:renderProductPath"),
        ("Tick.outputs:tick", "TfLidar.inputs:execIn"),
        ("SimTime.outputs:simulationTime", "TfLidar.inputs:timeStamp"),
    ]
    if i == 1:   # chi robot1 phat /clock
        nodes.append(("ClockPub", "isaacsim.ros2.bridge.ROS2PublishClock"))
        values.append(("ClockPub.inputs:topicName", "clock"))
        conns += [("Tick.outputs:tick", "ClockPub.inputs:execIn"),
                  ("SimTime.outputs:simulationTime", "ClockPub.inputs:timeStamp")]

    og.Controller.edit({"graph_path": GRAPH, "evaluator_name": "execution"},
                       {keys.CREATE_NODES: nodes, keys.SET_VALUES: values, keys.CONNECT: conns})
    stage.GetPrimAtPath(f"{GRAPH}/OdomCalc").CreateRelationship("inputs:chassisPrim").SetTargets([Sdf.Path(CHASSIS)])
    stage.GetPrimAtPath(f"{GRAPH}/RP").CreateRelationship("inputs:cameraPrim").SetTargets([olid.GetPath()])
    stage.GetPrimAtPath(f"{GRAPH}/WorldPose").CreateRelationship("inputs:prim").SetTargets([Sdf.Path(CHASSIS)])
    print("ROS2", NS, "ok")


for i in range(1, N + 1):
    setup(i)

from prepare_cycle_graph import mark_cycle_roads
mark_cycle_roads(stage)
ctx.save_as_stage(DST)
print("ROS2 OK: da luu", DST, "| so robot:", N)
app.close()
