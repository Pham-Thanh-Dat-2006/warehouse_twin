#!/usr/bin/env python3
"""Open the validated ROS2 warehouse with a scripted live-factory layer."""
import argparse
import os
from pathlib import Path
from project_paths import PROJECT_ROOT, ROS2_USD

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--stage',default=str(ROS2_USD))
p.add_argument('--play',action='store_true')
p.add_argument('--no-ros',action='store_true',help='Standalone animation preview without AGV coupling')
p.add_argument('--quality',choices=('fast','quality'),default='fast',
               help='fast: 960x540 raytraced lighting; quality: Isaac default realtime path tracing')
args=p.parse_args()
if not os.path.isfile(args.stage):p.error('Stage does not exist: '+args.stage)
from isaacsim.simulation_app import SimulationApp
launch={'headless':False}
if args.quality=='fast':
    launch.update(renderer='RaytracedLighting',width=960,height=540,multi_gpu=False)
print(f'[FACTORY LOAD] Render profile: {args.quality}; '
      f'{launch.get("renderer", "RealTimePathTracing")} '
      f'{launch.get("width",1280)}x{launch.get("height",720)}',flush=True)
app=SimulationApp(launch)
from isaacsim.core.utils.extensions import enable_extension
for name in ('omni.graph.action','omni.graph.nodes','isaacsim.core.nodes',
             'isaacsim.ros2.bridge','isaacsim.sensors.experimental.rtx'):
    enable_extension(name)
app.update()
import omni.usd
import omni.timeline
ctx=omni.usd.get_context()
driver=None
try:
    print('[FACTORY LOAD] Opening '+args.stage,flush=True)
    if not ctx.open_stage(args.stage):raise RuntimeError('Cannot open '+args.stage)
    stage=ctx.get_stage()
    if stage is None or not stage.GetPrimAtPath('/Warehouse/ROS2_robot1'):
        raise RuntimeError('Opened stage is missing /Warehouse/ROS2_robot1')
    print('[FACTORY LOAD] USD opened; preparing warehouse overview',flush=True)
    from factory_startup import set_overview,wait_for_assets
    from omni.kit.viewport.utility import get_active_viewport
    for _ in range(5):app.update()
    viewport=get_active_viewport()
    if viewport is None:raise RuntimeError('No active viewport in Isaac')
    set_overview(stage,viewport)
    print('[FACTORY LOAD] Camera selected: /Warehouse/Camera',flush=True)
    wait_for_assets(app,ctx)
    print('[FACTORY LOAD] Preparing conveyor and arm animation',flush=True)
    from factory_live import start_factory
    driver=start_factory(ros_enabled=not args.no_ros)
    if args.play:omni.timeline.get_timeline_interface().play()
    print(f'[FACTORY] Press Play, then run: WAREHOUSE_FACTORY=1 bash {PROJECT_ROOT}/scripts/run_warehouse_cycles.sh')
    while app.is_running():app.update()
finally:
    if driver is not None:driver.stop()
    app.close()
