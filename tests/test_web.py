"""Warehouse accounting and local HTTP/SSE integration; no ROS/motor commands."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
from model import Warehouse
from server import make_server


def packet(phase='pickup',loaded=False,run='run-one',cycle=1,robot=1):
    return {'version':1,'run_id':run,'running':True,'held':False,'fault':None,
            'robots':{str(robot):{'active':True,'phase':phase,'loaded':loaded,'completed':cycle-1,'cycle':cycle}}}


class Accounting(unittest.TestCase):
    def setUp(self):self.store=Warehouse(':memory:')
    def tearDown(self):self.store.close()
    def stock(self):
        self.store.intake({'sku':'MTR-1','name':'Động cơ','qty':10,'location':'storage_left','unit':'thùng','minimum':2})
    def create(self,qty=4):return self.store.create_job({'sku':'MTR-1','qty':qty,'destination':'assembly'})
    def test_reservation_pickup_delivery_and_idempotence(self):
        self.stock();key=self.create();self.assertEqual(self.store.available('MTR-1','storage_left'),6)
        self.store.factory_state(packet());self.assertEqual(self.store.detail(key)['job']['robot'],1)
        self.assertEqual(self.store.detail(key)['job']['status'],'pickup')
        for _ in range(4):self.store.factory_state(packet('drop',True))
        self.assertEqual(self.store.detail(key)['job']['status'],'in_transit')
        self.assertEqual(self.store.available('MTR-1','storage_left'),6)
        for _ in range(4):self.store.factory_state(packet('park',False))
        self.assertEqual(self.store.detail(key)['job']['status'],'delivered')
        stock={r['location']:r['qty'] for r in self.store.snapshot()['inventory']}
        self.assertEqual(stock,{'storage_left':6,'assembly':4})
        self.assertEqual(len(self.store.detail(key)['events']),4)
    def test_over_reservation_and_cancel(self):
        self.stock();key=self.create(8)
        with self.assertRaises(ValueError):self.create(3)
        self.store.cancel_job(key);self.assertEqual(self.store.available('MTR-1','storage_left'),10)
        with self.assertRaises(ValueError):self.store.cancel_job(key)
    def test_loaded_trip_is_not_assigned_declared_stock(self):
        self.stock();key=self.create();self.store.factory_state(packet('drop',True))
        self.assertEqual(self.store.detail(key)['job']['status'],'queued')
        self.assertEqual(self.store.snapshot()['kpis']['on_hand'],10)
        observed=[j for j in self.store.snapshot()['jobs'] if j['observed']]
        self.assertEqual(len(observed),1);self.assertIsNone(observed[0]['sku'])
    def test_interrupted_trip_reconciliation_does_not_double_credit(self):
        self.stock();key=self.create();self.store.factory_state(packet());self.store.factory_state(packet('drop',True))
        self.store.factory_state(packet(run='run-two'))
        self.assertEqual(self.store.detail(key)['job']['status'],'interrupted')
        self.store.reconcile(key,'destination')
        self.assertEqual(self.store.snapshot()['kpis']['on_hand'],10)
        with self.assertRaises(ValueError):self.store.reconcile(key,'destination')
    def test_same_run_new_cycle_marks_missing_delivery(self):
        self.stock();key=self.create();self.store.factory_state(packet());self.store.factory_state(packet('drop',True))
        self.store.factory_state(packet(cycle=2))
        self.assertEqual(self.store.detail(key)['job']['status'],'interrupted')
    def test_db_survives_restart_and_session_change(self):
        with tempfile.TemporaryDirectory() as d:
            s=Warehouse(Path(d)/'test.sqlite');s.intake({'sku':'T1','name':'Hàng thử','qty':10,'location':'storage_left'})
            key=s.create_job({'sku':'T1','qty':3,'destination':'assembly'});s.factory_state(packet());s.factory_state(packet('drop',True));s.close()
            s=Warehouse(Path(d)/'test.sqlite')
            s.factory_state(packet(run='another-run'))
            self.assertEqual(s.detail(key)['job']['status'],'interrupted');s.reconcile(key,'source')
            self.assertEqual(s.available('T1','storage_left'),10);s.close()
    def test_stale_pose_is_visible_as_stale_and_reset_clears_speed(self):
        self.store.pose(1,10,33,0,1);self.store.pose(1,11,33,0,2);self.store.scan(1)
        f=self.store.snapshot()['robots'][0];self.assertTrue(f['online']);self.assertEqual(f['speed'],1)
        self.store.fleet[1]['pose_at']=time.monotonic()-4
        f=self.store.snapshot()['robots'][0];self.assertFalse(f['online']);self.assertEqual(f['pose']['x'],11)
        self.store.update_clock(10);self.store.update_clock(0)
        self.assertIsNone(self.store.fleet[1]['speed'])
    def test_heatmap_uses_observed_simulation_time_and_ignores_duplicate_stamps(self):
        self.store.pose(1,10,33,0,1)
        self.store.pose(1,10,33,0,1)
        self.assertEqual(self.store.snapshot()['heatmap']['cells'],[])
        self.store.pose(1,10,33,0,1.1)
        self.store.pose(1,10,33,0,1.2)
        cells=self.store.snapshot()['heatmap']['cells']
        self.assertEqual(cells,[[4,13,.2]])
        self.store.update_clock(10);self.store.update_clock(0)
        self.assertEqual(self.store.snapshot()['heatmap']['cells'],[])
    def test_unknown_data_and_invalid_quantities(self):
        s=self.store.snapshot();self.assertIsNone(s['production']);self.assertIsNone(s['robots'][0]['pose']);self.assertFalse(s['connection']['dispatcher'])
        for qty in (-1,0,True,2.5,'1e4'):
            with self.assertRaises(ValueError):self.store.intake({'sku':'T','name':'test','qty':qty,'location':'storage_left'})


class Http(unittest.TestCase):
    def setUp(self):
        self.store=Warehouse(':memory:');self.server=make_server(self.store,port=0)
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.monitor_stop.set();self.server.shutdown();self.server.server_close();self.thread.join();self.store.close()
    def request(self,path,data=None,origin=None):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        req=Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        return urlopen(req,timeout=3.)
    def test_http_forms_detail_csv_and_origin(self):
        with self.request('/api/inventory/intake',{'sku':'T1','name':'Hàng thử','qty':'10','location':'storage_left'}) as r:self.assertEqual(r.status,200)
        with self.request('/api/jobs',{'sku':'T1','qty':3,'destination':'assembly'}) as r:key=json.load(r)['id']
        with self.request('/api/jobs/'+key) as r:self.assertEqual(json.load(r)['job']['status'],'queued')
        with self.request('/api/export/inventory.csv') as r:self.assertIn('Hàng thử',r.read().decode('utf-8-sig'))
        with self.assertRaises(HTTPError) as cm:self.request('/api/jobs',{'sku':'T1','qty':20,'destination':'assembly'})
        self.assertEqual(cm.exception.code,400);cm.exception.close()
        with self.assertRaises(HTTPError) as cm:self.request('/api/jobs',{},origin='http://other-site.invalid')
        self.assertEqual(cm.exception.code,403);cm.exception.close()
        with self.request('/api/jobs/'+key+'/cancel',{}) as r:self.assertTrue(json.load(r)['ok'])
    def test_sse_static_and_path_boundaries(self):
        with self.request('/') as r:self.assertIn('KhoTwin',r.read().decode())
        with self.request('/api/events') as r:
            self.assertEqual(r.readline().decode().strip(),'event: state')
            data=json.loads(r.readline().decode().removeprefix('data: '));self.assertEqual(data['mode'],'live')
        with self.assertRaises(HTTPError) as cm:self.request('/%2e%2e/server.py')
        self.assertEqual(cm.exception.code,404);cm.exception.close()


if __name__=='__main__':unittest.main(verbosity=2)
