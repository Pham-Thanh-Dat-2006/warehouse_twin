"""Optional local Chrome DevTools QA. Connects only to the dedicated test browser."""
import base64,json,os,socket,struct,time
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlsplit

class CDP:
    def __init__(self, url_prefix="http://127.0.0.1:8090", port=9229):
        with urlopen(f'http://127.0.0.1:{port}/json/list') as r:
            target=next(t for t in json.load(r) if t['type']=='page' and t['url'].startswith(url_prefix))
        u=urlsplit(target['webSocketDebuggerUrl']);self.sock=socket.create_connection((u.hostname,u.port),timeout=10)
        key=base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(f'GET {u.path} HTTP/1.1\r\nHost: {u.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode())
        response=b''
        while not response.endswith(b'\r\n\r\n'):response+=self.sock.recv(1)
        assert response.split(b' ',2)[1]==b'101',response
        self.seq=0;self.errors=[]
    def read(self,n):
        data=b''
        while len(data)<n:
            chunk=self.sock.recv(n-len(data))
            if not chunk:raise ConnectionError('DevTools disconnected')
            data+=chunk
        return data
    def send(self,obj):
        payload=json.dumps(obj).encode();mask=os.urandom(4);n=len(payload)
        size=bytes([n|128]) if n<126 else b'\xfe'+struct.pack('!H',n) if n<65536 else b'\xff'+struct.pack('!Q',n)
        self.sock.sendall(b'\x81'+size+mask+bytes(c^mask[i%4] for i,c in enumerate(payload)))
    def message(self):
        head=self.read(2);n=head[1]&127
        if n==126:n=struct.unpack('!H',self.read(2))[0]
        elif n==127:n=struct.unpack('!Q',self.read(8))[0]
        data=self.read(n)
        return json.loads(data)
    def call(self,method,params=None):
        self.seq+=1;key=self.seq;self.send({'id':key,'method':method,'params':params or {}})
        while True:
            item=self.message()
            if item.get('method')=='Runtime.exceptionThrown':self.errors.append(item['params'])
            if item.get('id')==key:
                if 'error' in item:raise RuntimeError(item['error'])
                return item.get('result',{})
    def js(self,expr):
        result=self.call('Runtime.evaluate',{'expression':expr,'returnByValue':True,'awaitPromise':True})
        if 'exceptionDetails' in result:raise RuntimeError(result['exceptionDetails'])
        return result['result'].get('value')
    def wait(self,expr):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if self.js(expr):return
            time.sleep(.1)
        raise AssertionError('Browser condition failed: '+expr)
    def screenshot(self,path):
        data=self.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
        Path(path).write_bytes(base64.b64decode(data['data']))


def main():
    c=CDP();c.call('Emulation.setDeviceMetricsOverride',{'width':1512,'height':1080,'deviceScaleFactor':1,'mobile':False});c.call('Runtime.enable');c.call('Page.enable');c.call('Page.reload',{'ignoreCache':True})
    c.wait('document.querySelectorAll(".robot-marker").length===6');c.errors=[]
    assert c.js('document.getElementById("mode-banner").textContent.includes("DEMO")')
    c.screenshot('/tmp/khoflow_overview.png')
    c.js('document.querySelector("a[data-page=inventory]").click()')
    c.wait('!document.getElementById("page-inventory").hidden')
    c.js('document.getElementById("intake-button").click()')
    c.wait('document.getElementById("intake-dialog").open')
    code='QA-'+str(int(time.time()))
    c.js('''(()=>{const f=document.getElementById('intake-form');f.elements.sku.value=%s;f.elements.name.value='Hàng kiểm thử trình duyệt';f.elements.qty.value='9';f.elements.location.value='storage_left';f.requestSubmit();})()'''%json.dumps(code))
    c.wait('!document.getElementById("intake-dialog").open')
    c.wait('document.getElementById("inventory-rows").textContent.includes('+json.dumps(code)+')')
    c.js('document.getElementById("inventory-search").value='+json.dumps(code)+';document.getElementById("inventory-search").dispatchEvent(new Event("input"))')
    c.wait('document.querySelectorAll("#inventory-rows tr").length===1')
    c.js('document.getElementById("new-order").click()')
    c.js('''(()=>{const f=document.getElementById('order-form');f.elements.sku.value=%s;f.elements.qty.value='99';f.elements.destination.value='assembly';f.requestSubmit();})()'''%json.dumps(code))
    c.wait('document.querySelector("#order-form .form-error").textContent.includes("chỉ còn")')
    c.js("document.getElementById('order-form').elements.qty.value='3';document.getElementById('order-form').requestSubmit()")
    c.wait('!document.getElementById("order-dialog").open')
    c.js('document.querySelector("a[data-page=orders]").click()')
    c.wait('!document.getElementById("page-orders").hidden')
    c.js('document.getElementById("order-search").value='+json.dumps(code)+';document.getElementById("order-search").dispatchEvent(new Event("input"))')
    c.wait('document.getElementById("order-rows").textContent.includes("Hàng kiểm thử")')
    c.js('document.querySelector("#order-rows [data-job]").click()')
    c.wait('document.getElementById("detail-dialog").open')
    assert c.js('document.getElementById("detail-body").textContent.includes("3 thùng")')
    c.js('document.querySelector("#detail-dialog [data-close]").click()')
    c.js('document.querySelector("a[data-page=production]").click()')
    c.wait('document.querySelectorAll("#belt-cards .belt-card").length===4&&document.querySelectorAll("#arm-cards .arm-card").length===8')
    c.screenshot('/tmp/khoflow_production.png')
    for name in ('fleet','activity','overview'):
        c.js('document.querySelector('+json.dumps('a[data-page='+name+']')+').click()')
        c.wait('!document.getElementById('+json.dumps('page-'+name)+').hidden')
    c.js("""document.querySelector('.robot-marker[data-robot="4"]').dispatchEvent(new MouseEvent("click",{bubbles:true}))""")
    c.wait('document.getElementById("selected-robot").textContent.includes("AGV-04")')
    c.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
    c.screenshot('/tmp/khoflow_mobile.png')
    assert c.js('document.documentElement.scrollWidth<=window.innerWidth'),c.js('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
    assert not c.errors,c.errors
    print('PASS: real browser navigation across 6 pages, 6 live map markers, intake form, SKU search, transport order creation, shipment detail, 4 belt/8 arm cards, robot selection, mobile overflow; no JS exceptions')
    c.sock.close()

if __name__=='__main__':main()
