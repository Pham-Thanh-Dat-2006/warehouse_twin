"""Stage startup helpers; keep loading progress visible and select the warehouse camera."""
import time


def wait_for_assets(app, context, timeout=30., now=time.monotonic, report=print):
    """USD is already open; allow background resources time without waiting forever."""
    started=now();last_report=started
    while context.get_stage_loading_status()[2]:
        if not app.is_running():raise RuntimeError('Isaac window closed while loading warehouse')
        elapsed=now()-started
        if elapsed>=timeout:
            pending=context.get_stage_loading_status()[2]
            report(f'[FACTORY LOAD] {pending} background resources still pending after {elapsed:.0f}s; '
                   'continuing with the opened USD, textures may finish later',flush=True)
            return False
        if now()-last_report>=5.:
            report(f'[FACTORY LOAD] waiting for resources: {context.get_stage_loading_status()}',flush=True)
            last_report=now()
        app.update()
    return True


def set_overview(stage, viewport):
    from pxr import Usd,UsdGeom,Gf
    # Session opinions only: reopening the saved warehouse restores its camera.
    with Usd.EditContext(stage,stage.GetSessionLayer()):
        camera=UsdGeom.Camera.Define(stage,'/Warehouse/Camera')
        camera.CreateFocalLengthAttr(28.)
        camera.CreateHorizontalApertureAttr(36.)
        camera.CreateVerticalApertureAttr(20.25)
        camera.CreateClippingRangeAttr(Gf.Vec2f(.1,1000.))
        world=Gf.Matrix4d().SetLookAt(Gf.Vec3d(170,-115,145),Gf.Vec3d(60,40,2),Gf.Vec3d(0,0,1)).GetInverse()
        UsdGeom.Xformable(camera).MakeMatrixXform().Set(world)
    viewport.camera_path='/Warehouse/Camera'
