#!/usr/bin/env python3
"""Local warehouse dashboard: stdlib HTTP + SSE + SQLite + optional read-only ROS."""
import argparse
import csv
import io
import json
import mimetypes
from pathlib import Path
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,unquote
from model import Warehouse

ROOT=Path(__file__).resolve().parent


def make_server(store,host='127.0.0.1',port=8080):
    stop=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def reply(self,code,data,mime='application/json; charset=utf-8'):
            if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(code);self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
        def do_GET(self):
            path=unquote(urlsplit(self.path).path)
            try:
                if path=='/api/state':return self.reply(200,store.snapshot())
                if path=='/api/geometry':return self.reply(200,store.geometry())
                if path.startswith('/api/jobs/'):
                    return self.reply(200,store.detail(path.removeprefix('/api/jobs/')))
                if path=='/api/events':return self.stream()
                if path in ('/api/export/inventory.csv','/api/export/jobs.csv'):
                    state=store.snapshot();kind='inventory' if 'inventory' in path else 'jobs'
                    fields=('sku','name','unit','location','qty','reserved','available') if kind=='inventory' else ('id','sku','name','qty','source','destination','robot','status','created','updated')
                    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(state[kind])
                    return self.reply(200,('\ufeff'+out.getvalue()).encode('utf-8'),'text/csv; charset=utf-8')
                if path.startswith('/api/'):return self.reply(404,{'error':'API không tồn tại'})
                file=(ROOT/'public'/('index.html' if path=='/' else path.lstrip('/'))).resolve()
                if not file.is_relative_to((ROOT/'public').resolve()) or not file.is_file():return self.reply(404,{'error':'Không tìm thấy trang'})
                return self.reply(200,file.read_bytes(),(mimetypes.guess_type(file.name)[0] or 'application/octet-stream')+'; charset=utf-8')
            except ValueError as exc:self.reply(404,{'error':str(exc)})
            except (BrokenPipeError,ConnectionResetError):pass
        def do_POST(self):
            path=unquote(urlsplit(self.path).path)
            origin=self.headers.get('Origin')
            if origin and origin not in ('http://'+self.headers.get('Host',''),'https://'+self.headers.get('Host','')):
                return self.reply(403,{'error':'Nguồn yêu cầu không hợp lệ'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                return self.reply(415,{'error':'Cần gửi JSON'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=32768:raise ValueError('Kích thước yêu cầu không hợp lệ')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('Dữ liệu cần là một object')
                if path=='/api/inventory/intake':result={'sku':store.intake(data)}
                elif path=='/api/jobs':result={'id':store.create_job(data)}
                elif path.startswith('/api/jobs/') and path.endswith('/cancel'):
                    store.cancel_job(path[len('/api/jobs/'):-len('/cancel')]);result={'ok':True}
                elif path.startswith('/api/jobs/') and path.endswith('/reconcile'):
                    store.reconcile(path[len('/api/jobs/'):-len('/reconcile')],data.get('destination'));result={'ok':True}
                else:return self.reply(404,{'error':'API không tồn tại'})
                return self.reply(200,result)
            except (ValueError,TypeError,json.JSONDecodeError) as exc:self.reply(400,{'error':str(exc)})
        def stream(self):
            self.send_response(200);self.send_header('Content-Type','text/event-stream; charset=utf-8')
            self.send_header('Cache-Control','no-cache');self.send_header('X-Accel-Buffering','no');self.end_headers()
            try:
                while not stop.is_set():
                    data=json.dumps(store.snapshot(),ensure_ascii=False,allow_nan=False)
                    self.wfile.write(('event: state\ndata: '+data+'\n\n').encode());self.wfile.flush()
                    stop.wait(.25)
            except (BrokenPipeError,ConnectionResetError):pass
    server=ThreadingHTTPServer((host,port),Handler);server.daemon_threads=True;server.monitor_stop=stop
    return server


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8080)
    p.add_argument('--demo',action='store_true',help='Synthetic data, separate temporary database, no ROS')
    p.add_argument('--database',type=Path,default=ROOT/'data/warehouse.sqlite')
    args=p.parse_args()
    if not 0<args.port<65536:p.error('Invalid port')
    if args.demo:
        database=':memory:'
    else:
        args.database.parent.mkdir(parents=True,exist_ok=True);database=args.database
    store=Warehouse(database,demo=args.demo);source=None;server=None
    def terminate(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,terminate)
    try:
        server=make_server(store,args.host,args.port)
        if args.demo:
            from demo_source import DemoSource
            source=DemoSource(store)
        else:
            try:
                from ros_source import RosSource
                source=RosSource(store)
            except Exception as exc:
                store.ros_error='Không kết nối được ROS: '+str(exc)
                print('[WEB] '+store.ros_error,flush=True)
        print(f'[WEB] {"DEMO (synthetic)" if args.demo else "LIVE (ROS read-only)"}: http://{args.host}:{server.server_port}',flush=True)
        print('[WEB] Inventory database: '+str(database),flush=True)
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:pass
    finally:
        if server:server.monitor_stop.set();server.server_close()
        if source:source.close()
        store.close()


if __name__=='__main__':main()
