"""Chrome regression: a failed 3D view must not stop valid live SSE updates."""
import sys
import time
from web_browser_qa import CDP


c = CDP(sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8090')
c.call('Runtime.enable')
c.call('Page.enable')


def updating_map():
    c.wait("document.querySelector('button[data-view=map]').classList.contains('active')")
    c.wait("document.querySelectorAll('#map-robots .robot-marker').length===6")
    before = c.js('window.warehouseSnapshot.server_time')
    time.sleep(1.2)
    assert c.js('window.warehouseSnapshot.server_time') != before
    assert not c.errors, c.errors


# Reproduce a server started before web_scene support was added.
script = c.call('Page.addScriptToEvaluateOnNewDocument', {'source': """
const originalFetch = window.fetch;
window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    if (args[0] !== '/api/geometry') return response;
    const data = await response.json();
    delete data.scene;
    return new Response(JSON.stringify(data), {headers: {'Content-Type': 'application/json'}});
};
"""})['identifier']
try:
    c.errors = []
    c.call('Page.reload', {'ignoreCache': True})
    updating_map()
    assert c.js("document.getElementById('toast').textContent.includes('Khởi động lại run_web.sh')")
finally:
    c.call('Page.removeScriptToEvaluateOnNewDocument', {'identifier': script})

c.call('Page.reload', {'ignoreCache': True})
c.wait('window.KhoTwin3D?.ready===true')
c.errors = []
# A render exception is a view error, not a corrupt incoming JSON packet.
c.js("window.KhoTwin3D.update=()=>{throw new Error('QA view failure')}")
updating_map()
assert c.js("document.getElementById('toast').textContent.includes('QA view failure')")
# A malformed event is rejected; the following valid events still update 2D.
c.js("stream.dispatchEvent(new MessageEvent('state',{data:'{broken json'}))")
assert c.js("document.getElementById('toast').textContent.includes('không hợp lệ')")
updating_map()
c.call('Page.reload', {'ignoreCache': True})
c.wait('window.KhoTwin3D?.ready===true')
print('PASS: old geometry API and 3D exceptions fall back to six live 2D markers; malformed JSON is distinguished; valid SSE recovers; normal 3D starts after reload')
c.sock.close()
