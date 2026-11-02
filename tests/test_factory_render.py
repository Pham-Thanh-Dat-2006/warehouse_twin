"""Real USD regression: sharing props preserves geometry, physics and editable arms."""
from collections import Counter
from pathlib import Path
import hashlib
import tempfile
from pxr import Usd, UsdGeom, UsdPhysics
from factory_render import write_render_stage, shareable
from project_paths import ROS2_USD

before_hash = hashlib.sha256(ROS2_USD.read_bytes()).hexdigest()
source = Usd.Stage.Open(str(ROS2_USD))
with tempfile.TemporaryDirectory(prefix='warehouse-render-') as directory:
    output = write_render_stage(ROS2_USD, Path(directory)/'runtime.usda')
    stage = Usd.Stage.Open(str(output))
    paths = [p.GetPath() for p in source.Traverse() if shareable(p)]
    assert len(paths) > 1000
    cache_a = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
    cache_b = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
    for path in paths:
        a, b = source.GetPrimAtPath(path), stage.GetPrimAtPath(path)
        assert b.IsInstance(), path
        box_a = cache_a.ComputeWorldBound(a).ComputeAlignedRange()
        box_b = cache_b.ComputeWorldBound(b).ComputeAlignedRange()
        for va, vb in ((box_a.GetMin(), box_b.GetMin()), (box_a.GetMax(), box_b.GetMax())):
            assert (va-vb).GetLength() < 1e-5, path
    # Traversing proxies still finds every original mesh/collider/body, at its
    # original scene path and with the same physics enable flags.
    def physics_state(s):
        result = {}
        for p in Usd.PrimRange(s.GetPseudoRoot(), Usd.TraverseInstanceProxies()):
            flags = []
            for name, api, attr in (
                ('collision', UsdPhysics.CollisionAPI, 'GetCollisionEnabledAttr'),
                ('rigid', UsdPhysics.RigidBodyAPI, 'GetRigidBodyEnabledAttr')):
                if p.HasAPI(api):
                    flags.append((name, getattr(api(p), attr)().Get()))
            if flags: result[str(p.GetPath())] = flags
        return result
    assert physics_state(stage) == physics_state(source)
    def counts(s, proxies=False):
        return Counter(p.GetTypeName() for p in Usd.PrimRange(
            s.GetPseudoRoot(), Usd.TraverseInstanceProxies()) if not p.IsPseudoRoot()) if proxies else Counter(p.GetTypeName() for p in s.Traverse())
    assert counts(stage, True) == counts(source, True)
    direct_a, direct_b = counts(source), counts(stage)
    assert direct_b['Material'] < direct_a['Material']/4
    for row in range(2):
        for cell in range(4):
            model = stage.GetPrimAtPath(f'/Warehouse/Zones/Assembly/Line{row}/Arm{cell}/N220_27/UnitsAndAxes/Model')
            assert not model.IsInstance()
            assert not stage.GetPrimAtPath(str(model.GetPath())+'/link_6').IsInstanceProxy()
    for i in range(1, 7):
        graph = f'/Warehouse/ROS2_robot{i}'
        assert stage.GetPrimAtPath(graph)
        for prim in Usd.PrimRange(source.GetPrimAtPath(graph)):
            actual = stage.GetPrimAtPath(prim.GetPath())
            for attr in prim.GetAttributes():
                assert attr.Get() == actual.GetAttribute(attr.GetName()).Get(), attr.GetPath()
    for key in ('upAxis','metersPerUnit','timeCodesPerSecond','startTimeCode','endTimeCode'):
        assert stage.GetMetadata(key) == source.GetMetadata(key), key
    assert hashlib.sha256(ROS2_USD.read_bytes()).hexdigest() == before_hash
    print(f'PASS: {len(paths)} shared props; all proxy geometry counts, 6 ROS graphs, physics flags and world bounds match; '
          f'8 arms remain editable; direct materials {direct_a["Material"]}->{direct_b["Material"]}; source USD unchanged')
