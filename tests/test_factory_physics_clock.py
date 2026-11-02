"""Headless Isaac integration: use real physics dt on a stage whose timeline range is 0..0.
No ROS bridge, warehouse robots or motor commands are loaded by this test.
"""
from isaacsim.simulation_app import SimulationApp
app=SimulationApp({'headless':True,'width':320,'height':240})
subscription=None
try:
    import omni.usd
    import omni.timeline
    import omni.physics.core
    from pxr import UsdPhysics,Gf
    from factory_cycle_core import create_factory
    ctx=omni.usd.get_context();ctx.new_stage()
    stage=ctx.get_stage();stage.SetStartTimeCode(0);stage.SetEndTimeCode(0)
    physics=UsdPhysics.Scene.Define(stage,'/PhysicsScene')
    physics.CreateGravityDirectionAttr(Gf.Vec3f(0,0,-1));physics.CreateGravityMagnitudeAttr(9.81)
    lines=create_factory();dt_total=[0.];steps=[0]
    def on_step(dt,*context):
        dt_total[0]+=dt;steps[0]+=1
        for line in lines:line.step(dt)
    subscription=omni.physics.core.get_physics_simulation_interface().subscribe_physics_on_step_events(
        on_update=on_step,pre_step=False,order=0)
    timeline=omni.timeline.get_timeline_interface();timeline.play()
    for _ in range(3000):
        app.update()
        if dt_total[0]>=22.:break
    assert dt_total[0]>=22.,(dt_total,steps)
    assert all(a.cycles>0 for line in lines for a in line.arms)
    assert sum(line.output for line in lines)>0
    timeline.pause();app.update();before=steps[0]
    for _ in range(10):app.update()
    assert steps[0]==before,'Physics clock advanced while paused'
    print(f'PASS: native Isaac post-step callback, zero-range stage; physics_time={dt_total[0]:.2f}s '
          f'steps={steps[0]} timeline={timeline.get_current_time():.3f}s '
          f'arm_cycles={sum(a.cycles for line in lines for a in line.arms)} '
          f'outputs={sum(line.output for line in lines)}; pause freezes motion',flush=True)
    timeline.stop()
finally:
    subscription=None
    app.close()
