"""Isolated GPU soak of the complete instanced warehouse, six RTX lidars and arms.

Run with ROS_DOMAIN_ID=171 and the Isaac python.sh. No cmd_vel/joint commands
are published; an extra camera render product exercises the full scene.
"""
import argparse
import os
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seconds', type=float, default=450.)
parser.add_argument('--screenshot',help='Save a close-up of the carton/roller contact')
args = parser.parse_args()
if os.environ.get('ROS_DOMAIN_ID') != '171':
    raise RuntimeError('This test requires isolated ROS_DOMAIN_ID=171')
from isaacsim.simulation_app import SimulationApp
app = SimulationApp({'headless': True, 'width': 960, 'height': 540})
driver = None
node = executor = context = product = None
try:
    from isaacsim.core.utils.extensions import enable_extension
    for name in ('omni.graph.action','omni.graph.nodes','isaacsim.core.nodes',
                 'isaacsim.ros2.bridge','isaacsim.sensors.experimental.rtx'):
        enable_extension(name)
    app.update()
    import omni.usd
    import omni.timeline
    import omni.replicator.core as rep
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.signals import SignalHandlerOptions
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import LaserScan
    from pxr import UsdRender,UsdGeom,Usd,Gf
    from project_paths import MAPS_DIR
    from factory_live import start_factory
    from factory_startup import wait_for_assets
    from factory_surfaces import support_height,CONTACT_GAP
    ctx = omni.usd.get_context()
    assert ctx.open_stage(str(MAPS_DIR/'warehouse_factory_runtime.usda'))
    wait_for_assets(app,ctx)
    stage = ctx.get_stage()
    driver = start_factory(ros_enabled=False)
    if args.screenshot:
        with Usd.EditContext(stage,stage.GetSessionLayer()):
            camera=UsdGeom.Camera(stage.GetPrimAtPath('/Warehouse/Camera'))
            camera.GetFocalLengthAttr().Set(28.)
            pose=Gf.Matrix4d().SetLookAt(Gf.Vec3d(14,5,3),Gf.Vec3d(12,10,1.1),Gf.Vec3d(0,0,1)).GetInverse()
            UsdGeom.Xformable(camera).MakeMatrixXform().Set(pose)
    product = rep.create.render_product('/Warehouse/Camera',(960,540))
    rgb=None
    if args.screenshot:
        rgb=rep.AnnotatorRegistry.get_annotator('rgb');rgb.attach([product])
    context = Context()
    rclpy.init(context=context,signal_handler_options=SignalHandlerOptions.NO)
    node = Node('factory_render_soak',context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    counts = {(i,kind):0 for i in range(1,7) for kind in ('scan','odom')}
    def receive(key):
        def callback(msg):counts[key]+=1
        return callback
    subscriptions = []
    for i in range(1,7):
        for kind,typ in (('scan',LaserScan),('odom',Odometry)):
            subscriptions.append(node.create_subscription(typ,f'/robot{i}/{kind}',receive((i,kind)),qos_profile_sensor_data))
    timeline = omni.timeline.get_timeline_interface()
    timeline.play()
    started = last_report = time.monotonic()
    products_max = 0
    while time.monotonic()-started < args.seconds or driver.sim_time < 22.:
        if time.monotonic()-started > args.seconds+180.:
            raise TimeoutError('Physics did not reach 22s within the extra startup allowance')
        app.update()
        # Drain several ready subscriptions so all 12 streams are observed.
        for _ in range(16):executor.spin_once(timeout_sec=0.)
        if time.monotonic()-last_report >= 30:
            products = sum(p.IsA(UsdRender.Product) for p in stage.Traverse())
            products_max = max(products_max,products)
            assert products <= 14, f'Render products growing: {products}'
            assert not driver.failed
            cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),['default','render'])
            for i,line in enumerate(driver.lines):
                for parcel,mover in zip(line.parcels,driver.boxes[i]):
                    if parcel.mode not in ('flow','waiting'):continue
                    bottom=cache.ComputeWorldBound(mover.prim).ComputeAlignedRange().GetMin()[2]
                    top=support_height(driver.belts[i],parcel.x,mover.size[0]/2)
                    assert abs(bottom-top-CONTACT_GAP)<.005,(i,parcel.index,bottom,top)
            print(f'[RENDER SOAK] wall={time.monotonic()-started:.1f}s physics={driver.sim_time:.1f}s '
                  f'products={products} scans={[counts[i,"scan"] for i in range(1,7)]} '
                  f'arm_cycles={sum(a.cycles for line in driver.lines for a in line.arms)}',flush=True)
            last_report = time.monotonic()
    assert all(v>10 for v in counts.values()), counts
    assert all(a.cycles>0 for line in driver.lines for a in line.arms)
    assert sum(line.output for line in driver.lines)>0
    assert not driver.failed
    if rgb is not None:
        from PIL import Image
        image=rgb.get_data()
        assert image.size>0,'No rendered RGB image'
        Image.fromarray(image).save(args.screenshot)
        print('PASS: rendered carton contact close-up saved to '+args.screenshot,flush=True)
    print(f'PASS: complete warehouse, 6 odom + 6 RTX scan streams, 8 moving arms, conveyor outputs; '
          f'{time.monotonic()-started:.1f}s wall soak, {driver.sim_time:.1f}s physics; '
          f'max render products={products_max}; no control messages published',flush=True)
    timeline.stop()
except BaseException:
    import traceback
    traceback.print_exc()
    raise
finally:
    if driver is not None:driver.stop()
    if executor is not None:executor.shutdown(timeout_sec=0.)
    if node is not None:node.destroy_node()
    if context is not None and context.ok():context.shutdown()
    # No queued captures or authored USD saves in this test. Avoid a native
    # close_stage wait on six sensor render products after stopping timeline.
    app.close(wait_for_replicator=False,skip_cleanup=True,
              exit_code=1 if sys.exc_info()[0] is not None else 0)
