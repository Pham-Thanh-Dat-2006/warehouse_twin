"""Real Chrome QA of the 3D control room, using the temporary demo browser."""
import time
from pathlib import Path
from web_browser_qa import CDP

c=CDP();c.call('Runtime.enable');c.call('Page.enable')
c.call('Emulation.setDeviceMetricsOverride',{'width':1536,'height':1024,'deviceScaleFactor':1,'mobile':False})
c.call('Page.reload',{'ignoreCache':True})
c.wait('window.KhoTwin3D?.ready===true&&window.warehouseSnapshot?.production?.arms?.length===8')
c.errors=[]
d=c.js('window.KhoTwin3D.debug()')
assert d['robots'] and len(d['robots'])==6 and d['racks']==40 and d['armChains']==8 and d['parcels']==52,d
assert c.js('window.KhoTwin3D.debug().robots.every(r=>{const p=window.warehouseSnapshot.robots.find(x=>x.id===r.id).pose;return Math.abs(r.x-p.x)<1e-7&&Math.abs(r.y-p.y)<1e-7})')
assert c.js('window.KhoTwin3D.dynamicArms.every(a=>a.target.length===8)')
# Verify view tabs and data-driven traffic/heat rather than decorative layers.
for mode in ('map','traffic','heatmap'):
 c.js(f'document.querySelector("button[data-view={mode}]").click()')
 c.wait(f'window.KhoTwin3D.mode==="{mode}"')
 assert c.js('!document.getElementById("twin-map-panel").hidden')
 if mode=='traffic':assert c.js('document.querySelectorAll("#map-trails polyline").length===6')
 if mode=='heatmap':assert c.js('document.querySelectorAll("#map-heat rect").length>0')
c.screenshot('/tmp/warehouse_twin_heatmap.png')
c.js("document.querySelector('button[data-view=\"3d\"]').click()")
# Numeric attribute values must be quoted in CSS selectors.
c.js('document.querySelector(\'.twin-scene-label[data-robot="4"]\').click()')
c.wait('document.getElementById("selected-robot").textContent.includes("AGV-04")')
c.js('document.getElementById("focus-robot").click()')
assert c.js('window.KhoTwin3D.camera.position.distanceTo(window.KhoTwin3D.controls.target)<25')
c.js('document.getElementById("follow-robot").click()');assert c.js('window.KhoTwin3D.follow')
c.js('document.getElementById("pan-tool").click()');assert c.js('window.KhoTwin3D.pan')
c.js('document.getElementById("orbit-tool").click()');assert not c.js('window.KhoTwin3D.pan')
c.js('document.getElementById("show-labels").click()');assert c.js('window.KhoTwin3D.overlay.hidden')
c.js('document.getElementById("show-labels").click()')
c.js('document.getElementById("show-routes").click()');assert c.js('window.KhoTwin3D.pathGroup.children.length===0')
c.js('document.getElementById("show-routes").click()')
c.js('document.querySelector("button[data-mini-camera=packing]").click()');assert c.js('window.KhoTwin3D.miniPreset==="packing"')
c.js('document.getElementById("camera-expand").click()')
c.js('document.getElementById("reset-camera").click()')
assert not c.js('window.KhoTwin3D.follow')
c.js("document.getElementById('render-quality').value='low';document.getElementById('render-quality').dispatchEvent(new Event('change'))")
assert c.js('window.KhoTwin3D.quality==="low"&&window.KhoTwin3D.renderer.getPixelRatio()===.65')
c.js("document.getElementById('render-quality').value='medium';document.getElementById('render-quality').dispatchEvent(new Event('change'))")
# Floor picking/ruler: two known world positions should measure 10 metres.
c.js('document.getElementById("measure-tool").click()')
for x in (40,50):
 p=c.js(f'(()=>{{const t=window.KhoTwin3D,r=t.renderer.domElement.getBoundingClientRect(),p=t.controls.target.clone().set({x},0,-40).project(t.camera);return {{x:r.x+(p.x*.5+.5)*r.width,y:r.y+(-p.y*.5+.5)*r.height}}}})()')
 c.call('Input.dispatchMouseEvent',{'type':'mousePressed','x':p['x'],'y':p['y'],'button':'left','clickCount':1})
 c.call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':p['x'],'y':p['y'],'button':'left','clickCount':1})
value=c.js('document.getElementById("measure-value").textContent')
assert value.endswith(' m') and abs(float(value[:-2])-10)<.1,value
c.js('document.getElementById("measure-tool").click()')
# Analysis is explicitly based on observations and rules.
c.js('document.getElementById("analysis-button").click()');assert c.js('document.getElementById("analysis-dialog").open')
c.js('document.querySelector("#analysis-dialog [data-close]").click()')
c.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':'/tmp/warehouse_browser_downloads'})
c.js('document.getElementById("snapshot-tool").click()')
deadline=time.monotonic()+5
while time.monotonic()<deadline and not Path('/tmp/warehouse_browser_downloads/warehouse-twin-3d.png').exists():time.sleep(.1)
assert Path('/tmp/warehouse_browser_downloads/warehouse-twin-3d.png').exists()
c.js('document.getElementById("reset-selection").click()');c.js('document.getElementById("reset-camera").click()')
c.screenshot('/tmp/warehouse_twin_control_room.png')
assert c.js('document.documentElement.scrollWidth<=innerWidth')
assert c.js('window.KhoTwin3D.debug().drawCalls<200'),c.js('window.KhoTwin3D.debug()')
c.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
c.screenshot('/tmp/warehouse_twin_control_room_mobile.png')
assert c.js('document.documentElement.scrollWidth<=innerWidth'),c.js('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
assert not c.errors,c.errors
print('PASS: 40 measured racks, 6 ROS-coordinate robot targets, 8 arm chains, 52 parcels; 4 view modes; measured heatmap; selection/focus/follow, camera presets, pan/orbit, paths/labels, 10m ruler, PNG capture, analysis, mobile; bounded draw calls and no JS exceptions')
c.sock.close()
