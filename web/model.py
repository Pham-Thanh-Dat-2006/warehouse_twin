"""Warehouse read model and persistent inventory. No ROS commands are published."""
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from warehouse_routes import STARTS, mission
from project_paths import CONFIG_DIR

LOCATIONS = {
    'storage_left': 'Kho trữ trái', 'storage_right': 'Kho trữ phải',
    'assembly': 'Khu lắp ráp', 'packing': 'Khu đóng gói',
}
PHASES = {'pickup': 'Đến nhận hàng', 'drop': 'Đang giao hàng', 'park': 'Về bãi', 'parked': 'Đang đỗ'}


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def text(value, name, limit=120):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f'{name}: cần nhập từ 1 đến {limit} ký tự')
    return value.strip()


def quantity(value):
    if isinstance(value, bool): raise ValueError('Số lượng phải là số nguyên dương')
    try: result = int(value)
    except (ValueError, TypeError): raise ValueError('Số lượng phải là số nguyên dương')
    if str(result) != str(value).strip() or not 1 <= result <= 1_000_000:
        raise ValueError('Số lượng phải từ 1 đến 1.000.000')
    return result


class Warehouse:
    def __init__(self, database, demo=False):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(database), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS skus(sku TEXT PRIMARY KEY, name TEXT NOT NULL, unit TEXT NOT NULL, minimum INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS stock(sku TEXT REFERENCES skus(sku), location TEXT, qty INTEGER NOT NULL CHECK(qty>=0), PRIMARY KEY(sku,location));
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, sku TEXT REFERENCES skus(sku), qty INTEGER, source TEXT, destination TEXT,
              priority INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, robot INTEGER, trip_key TEXT UNIQUE,
              picked INTEGER NOT NULL DEFAULT 0, delivered INTEGER NOT NULL DEFAULT 0, observed INTEGER NOT NULL DEFAULT 0,
              note TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, severity TEXT NOT NULL,
              kind TEXT NOT NULL, message TEXT NOT NULL, job_id TEXT, robot INTEGER);
        ''')
        self.demo = demo
        self.started = time.monotonic()
        self.fleet = {i: {'id': i, 'name': f'AGV-{i:02}', 'group': 'assembly' if i <= 3 else 'packing',
                         'pose': None, 'pose_at': None, 'pose_stamp': None, 'speed': None,
                         'trail': deque(maxlen=160), 'distance': 0., 'scan_at': None,
                         'phase': None, 'loaded': None, 'active': False, 'completed': 0,
                         'trip_key': None, 'phase_at': None, 'at_station': False} for i in range(1, 7)}
        self.master = None; self.master_at = None
        self.production = None; self.production_at = None
        self.heartbeat = None; self.heartbeat_at = None
        self.clock = None; self.clock_at = None; self.rtf = None
        self.run_id = None; self.legacy_run = uuid.uuid4().hex[:10]
        self.alert_keys = set(); self.ros_error = None
        self.history = deque(maxlen=90)
        self._last_history = 0.
        self.heatmap={}
        scene_path=CONFIG_DIR/'web_scene.json'
        self.scene=json.loads(scene_path.read_text()) if scene_path.is_file() else None

    def event(self, message, severity='info', kind='system', job_id=None, robot=None):
        self.db.execute('INSERT INTO events(at,severity,kind,message,job_id,robot) VALUES(?,?,?,?,?,?)',
                        (utc(),severity,kind,message,job_id,robot))

    def intake(self, data):
        code = text(data.get('sku'), 'Mã SKU', 40).upper()
        if not re.fullmatch(r'[A-Z0-9_-]+', code): raise ValueError('SKU chỉ gồm chữ, số, gạch ngang/gạch dưới')
        name = text(data.get('name'), 'Tên hàng', 100)
        unit = text(data.get('unit', 'thùng'), 'Đơn vị', 20)
        count = quantity(data.get('qty'))
        location = data.get('location')
        if location not in LOCATIONS: raise ValueError('Vị trí không hợp lệ')
        try: minimum = int(data.get('minimum', 0))
        except (ValueError,TypeError): raise ValueError('Mức tồn tối thiểu không hợp lệ')
        if minimum < 0 or minimum > 1_000_000: raise ValueError('Mức tồn tối thiểu không hợp lệ')
        with self.lock, self.db:
            self.db.execute('INSERT INTO skus VALUES(?,?,?,?) ON CONFLICT(sku) DO UPDATE SET name=excluded.name,unit=excluded.unit,minimum=excluded.minimum', (code,name,unit,minimum))
            self.db.execute('INSERT INTO stock VALUES(?,?,?) ON CONFLICT(sku,location) DO UPDATE SET qty=qty+excluded.qty', (code,location,count))
            self.event(f'Nhập {count} {unit} {code} vào {LOCATIONS[location]}',kind='inventory')
        return code

    def available(self, sku, source):
        row = self.db.execute('SELECT qty FROM stock WHERE sku=? AND location=?',(sku,source)).fetchone()
        total = row['qty'] if row else 0
        reserved = self.db.execute("SELECT COALESCE(SUM(qty),0) FROM jobs WHERE sku=? AND source=? AND picked=0 AND status IN ('queued','pickup')", (sku,source)).fetchone()[0]
        return total - reserved

    def create_job(self, data):
        sku = text(data.get('sku'), 'Mã SKU',40).upper()
        count = quantity(data.get('qty'))
        dest = data.get('destination')
        if dest not in ('assembly','packing'): raise ValueError('Chọn khu lắp ráp hoặc đóng gói theo tuyến hiện có')
        source = 'storage_left' if dest=='assembly' else 'storage_right'
        try: priority = int(data.get('priority',0))
        except (TypeError,ValueError): raise ValueError('Độ ưu tiên không hợp lệ')
        if priority not in (0,1,2): raise ValueError('Độ ưu tiên không hợp lệ')
        note = str(data.get('note','')).strip()[:300]
        with self.lock, self.db:
            if not self.db.execute('SELECT 1 FROM skus WHERE sku=?',(sku,)).fetchone(): raise ValueError('SKU chưa được khai báo')
            available = self.available(sku,source)
            if count > available: raise ValueError(f'{LOCATIONS[source]} chỉ còn {available} đơn vị khả dụng')
            key = 'VC-'+uuid.uuid4().hex[:8].upper()
            self.db.execute('INSERT INTO jobs(id,sku,qty,source,destination,priority,status,note,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (key,sku,count,source,dest,priority,'queued',note,utc(),utc()))
            self.event(f'Tạo {key}: {sku} × {count} → {LOCATIONS[dest]}; chờ chu kỳ nhận tiếp theo',kind='order',job_id=key)
        return key

    def cancel_job(self, key):
        with self.lock, self.db:
            job = self.db.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone()
            if job is None: raise ValueError('Không tìm thấy đơn')
            if job['status'] != 'queued': raise ValueError('Chỉ hủy được đơn đang chờ ghép chuyến')
            self.db.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=?",(utc(),key))
            self.event(f'Hủy đơn {key}; giải phóng số lượng giữ chỗ',kind='order',job_id=key)

    def reconcile(self, key, destination):
        with self.lock,self.db:
            job = self.db.execute('SELECT * FROM jobs WHERE id=?',(key,)).fetchone()
            if job is None or job['status']!='interrupted': raise ValueError('Đơn không cần đối soát')
            if destination not in ('source','destination'): raise ValueError('Chọn nơi hàng thực sự đã về')
            if destination=='destination' and not job['picked']:
                raise ValueError('Chưa ghi nhận lấy hàng; cần xác nhận trả kho hoặc kiểm kê trước')
            if job['sku'] and job['picked'] and not job['delivered']:
                loc = job[destination]
                self.db.execute('INSERT INTO stock VALUES(?,?,?) ON CONFLICT(sku,location) DO UPDATE SET qty=qty+excluded.qty',(job['sku'],loc,job['qty']))
            status = 'delivered' if destination=='destination' else 'returned'
            self.db.execute('UPDATE jobs SET status=?,delivered=?,updated=? WHERE id=?',(status,int(destination=='destination'),utc(),key))
            self.event(f'Đối soát {key}: xác nhận {"đã giao" if destination=="destination" else "đã trả kho"}',kind='inventory',job_id=key)

    def pose(self, i, x, y, a, stamp):
        if not all(math.isfinite(v) for v in (x,y,a,stamp)): return
        with self.lock:
            f = self.fleet[i]; now = time.monotonic()
            if f['pose_stamp'] is not None and stamp > f['pose_stamp'] and f['pose'] is not None:
                if 0<=x<120 and 0<=y<80:
                    cell=(int(x/2.5),int(y/2.5))
                    self.heatmap[cell]=self.heatmap.get(cell,0.)+min(.5,stamp-f['pose_stamp'])
                delta = math.hypot(x-f['pose']['x'],y-f['pose']['y'])
                speed = delta/(stamp-f['pose_stamp'])
                f['speed'] = speed if speed < 5 else None
                if delta < 5: f['distance'] += delta
            f['pose'] = {'x':x,'y':y,'yaw':a}; f['pose_stamp'] = stamp; f['pose_at'] = now
            if not f['trail'] or math.hypot(x-f['trail'][-1][0],y-f['trail'][-1][1])>.15:
                f['trail'].append([x,y])

    def scan(self,i):
        with self.lock:self.fleet[i]['scan_at']=time.monotonic()

    def update_clock(self, value):
        with self.lock:
            now=time.monotonic()
            if self.clock is not None and value<self.clock-.05:
                for f in self.fleet.values():
                    f['speed']=None;f['pose_stamp']=None;f['trail'].clear();f['distance']=0.
                self.rtf=None
                self.heatmap.clear()
            if self.clock is not None and value>=self.clock and self.clock_at is not None:
                elapsed=now-self.clock_at
                if elapsed>.001:
                    rate=(value-self.clock)/elapsed
                    self.rtf=rate if self.rtf is None else self.rtf*.9+rate*.1
            self.clock=value;self.clock_at=now

    def factory_heartbeat(self, healthy):
        with self.lock:self.heartbeat=bool(healthy);self.heartbeat_at=time.monotonic()

    def factory_telemetry(self, data):
        if not isinstance(data,dict) or data.get('version')!=1:return
        with self.lock:
            self.production=data;self.production_at=time.monotonic()
            if self.history and data.get('factory_time',0)<self.history[-1]['time']:
                self.history.clear();self._last_history=0.
            now=time.monotonic()
            if now-self._last_history>=5.:
                self.history.append({'at':utc(),'time':data.get('factory_time',0),'outputs':data.get('belt_outputs',0)})
                self._last_history=now

    def factory_state(self, data):
        if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('robots'),dict):return
        now=time.monotonic()
        run=str(data.get('run_id') or self.legacy_run)
        with self.lock,self.db:
            previous=self.db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('pickup','in_transit') AND trip_key NOT LIKE ?",(run+':%',)).fetchone()[0]
            if previous:
                self.db.execute("UPDATE jobs SET status='interrupted',updated=? WHERE status IN ('pickup','in_transit') AND trip_key NOT LIKE ?",(utc(),run+':%'))
                for f in self.fleet.values():f['trip_key']=None
                self.event('Bộ điều phối bắt đầu phiên mới. Các chuyến chưa hoàn tất cần đối soát.',severity='warning',kind='mission')
            # Preserve interrupted stock across server restarts, rather than marking it delivered.
            self.run_id=run;self.master=data;self.master_at=now
            for i,f in self.fleet.items():
                state=data['robots'].get(str(i),{})
                if not isinstance(state,dict):continue
                phase=state.get('phase','parked');active=bool(state.get('active'));loaded=bool(state.get('loaded'))
                completed=int(state.get('completed',0))
                if phase!=f['phase']:
                    f['phase_at']=now
                f.update(phase=phase,loaded=loaded,active=active,completed=completed,at_station=bool(state.get('at_station')))
                if not active: continue
                cycle=int(state.get('cycle',completed+1))
                trip=f'{run}:robot{i}:{cycle}'
                old=self.db.execute("SELECT * FROM jobs WHERE robot=? AND status IN ('pickup','in_transit') AND trip_key!=?",(i,trip)).fetchall()
                for lost in old:
                    self.db.execute("UPDATE jobs SET status='interrupted',updated=? WHERE id=?",(utc(),lost['id']))
                    self.event(f'{lost["id"]}: thiếu sự kiện hoàn tất trước chu kỳ mới; cần đối soát',severity='warning',kind='mission',job_id=lost['id'],robot=i)
                source='storage_left' if i<=3 else 'storage_right';dest=f['group']
                # Only attach declared stock before pickup, never to a trip first seen already loaded.
                job=self.db.execute('SELECT * FROM jobs WHERE trip_key=?',(trip,)).fetchone()
                if job is None:
                    if phase=='park':continue
                    queued=self.db.execute("SELECT * FROM jobs WHERE status='queued' AND destination=? ORDER BY priority DESC,created,id LIMIT 1",(dest,)).fetchone() if phase=='pickup' and not loaded else None
                    if queued:
                        self.db.execute("UPDATE jobs SET status='pickup',robot=?,trip_key=?,updated=? WHERE id=?",(i,trip,utc(),queued['id']))
                        key=queued['id']
                    else:
                        key=f'K-{run[:12]}-{i}-{cycle}'
                        self.db.execute('INSERT OR IGNORE INTO jobs(id,source,destination,status,robot,trip_key,observed,created,updated) VALUES(?,?,?,?,?,?,1,?,?)', (key,source,dest,'pickup',i,trip,utc(),utc()))
                    self.event(f'{key}: ghép với {f["name"]}',kind='mission',job_id=key,robot=i)
                    job=self.db.execute('SELECT * FROM jobs WHERE trip_key=?',(trip,)).fetchone()
                f['trip_key']=job['id']
                if job['status'] in ('delivered','cancelled','returned','interrupted'):continue
                picked=job['picked'];delivered=job['delivered']
                if loaded and not picked:
                    if job['sku']:
                        cursor=self.db.execute('UPDATE stock SET qty=qty-? WHERE sku=? AND location=? AND qty>=?',(job['qty'],job['sku'],source,job['qty']))
                        if cursor.rowcount!=1:raise RuntimeError('Tồn kho đã giữ chỗ không đủ khi nhận hàng')
                    picked=1
                    self.db.execute("UPDATE jobs SET picked=1,status='in_transit',updated=? WHERE id=?",(utc(),job['id']))
                    self.event(f'{job["id"]}: {f["name"]} đã nhận hàng, đang tới {LOCATIONS[dest]}',kind='mission',job_id=job['id'],robot=i)
                if phase=='park' and not loaded and picked and not delivered:
                    if job['sku']:
                        self.db.execute('INSERT INTO stock VALUES(?,?,?) ON CONFLICT(sku,location) DO UPDATE SET qty=qty+excluded.qty',(job['sku'],dest,job['qty']))
                    self.db.execute("UPDATE jobs SET delivered=1,status='delivered',updated=? WHERE id=?",(utc(),job['id']))
                    self.event(f'{job["id"]}: đã giao tại {LOCATIONS[dest]}',kind='mission',job_id=job['id'],robot=i)

    def snapshot(self):
        now=time.monotonic()
        with self.lock,self.db:
            def fresh(at):return at is not None and now-at<3.
            robots=[]
            for f in self.fleet.values():
                item={k:v for k,v in f.items() if k not in ('trail','pose_at','pose_stamp','scan_at','phase_at')}
                item.update(online=fresh(f['pose_at']),scan_online=fresh(f['scan_at']),age=None if f['pose_at'] is None else round(now-f['pose_at'],1),trail=list(f['trail']))
                robots.append(item)
            inventory=[dict(row) for row in self.db.execute('''SELECT k.*,COALESCE(s.qty,0) qty,s.location FROM skus k LEFT JOIN stock s ON s.sku=k.sku ORDER BY k.sku,s.location''')]
            for row in inventory:
                row['available']=self.available(row['sku'],row['location']) if row['location'] else 0
                row['reserved']=row['qty']-row['available']
            jobs=[dict(row) for row in self.db.execute('SELECT j.*,s.name,s.unit FROM jobs j LEFT JOIN skus s ON s.sku=j.sku ORDER BY j.created DESC,j.id DESC LIMIT 500')]
            events=[dict(row) for row in self.db.execute('SELECT * FROM events ORDER BY seq DESC LIMIT 150')]
            alerts=[]
            if self.ros_error:alerts.append({'key':'ros','severity':'error','message':self.ros_error})
            if not fresh(self.master_at):alerts.append({'key':'dispatcher','severity':'warning','message':'Chưa nhận dữ liệu mới từ bộ điều phối AGV'})
            if self.master and not self.master.get('run_id'):alerts.append({'key':'old-dispatcher','severity':'warning','message':'Khởi động lại bộ điều phối để dùng mã chuyến ổn định của bản web mới'})
            if self.master and self.master.get('fault'):alerts.append({'key':'fault','severity':'error','message':str(self.master['fault'])})
            if self.master and self.master.get('held'):alerts.append({'key':'hold','severity':'warning','message':'Bộ điều phối đang giữ dừng các AGV'})
            for f in robots:
                if not f['online']:alerts.append({'key':f'pose{f["id"]}','severity':'warning','message':f'{f["name"]}: chưa có pose mới'})
                elif not f['scan_online']:alerts.append({'key':f'scan{f["id"]}','severity':'warning','message':f'{f["name"]}: lidar chưa có dữ liệu mới'})
            if not fresh(self.production_at):alerts.append({'key':'production','severity':'warning','message':'Chưa có telemetry mới của băng chuyền/tay máy'})
            totals={}
            for row in inventory:totals[row['sku']]=totals.get(row['sku'],0)+row['qty']
            for row in inventory:
                if row['minimum'] and totals[row['sku']]<row['minimum']:
                    key='stock'+row['sku']
                    if not any(a['key']==key for a in alerts):alerts.append({'key':key,'severity':'warning','message':f'{row["sku"]}: tổng tồn dưới mức tối thiểu {row["minimum"]}'})
            return {'mode':'demo' if self.demo else 'live','server_time':utc(),'uptime':round(now-self.started),
                    'connection':{'dispatcher':fresh(self.master_at),'production':fresh(self.production_at),'clock':fresh(self.clock_at),'factory':fresh(self.heartbeat_at) and self.heartbeat is True},
                    'sim_time':self.clock,'rtf':self.rtf,'master':self.master,'robots':robots,
                    'production':self.production,'history':list(self.history),'inventory':inventory,'jobs':jobs,'events':events,'alerts':alerts,
                    'heatmap':{'cell_size':2.5,'unit':'robot_seconds','cells':[[x,y,round(v,2)] for (x,y),v in self.heatmap.items()]},
                    'kpis':{'online':sum(f['online'] for f in robots),'moving':sum(f['online'] and f['speed'] is not None and f['speed']>.03 for f in robots),
                            'on_hand':sum(totals.values()),'skus':len(totals),'queued':sum(j['status']=='queued' for j in jobs),
                            'transit':sum(j['status']=='in_transit' for j in jobs),'delivered':self.db.execute("SELECT COUNT(*) FROM jobs WHERE status='delivered'").fetchone()[0]}}

    def detail(self,key):
        with self.lock:
            job=self.db.execute('SELECT j.*,s.name,s.unit FROM jobs j LEFT JOIN skus s ON s.sku=j.sku WHERE j.id=?',(key,)).fetchone()
            if job is None:raise ValueError('Không tìm thấy đơn')
            return {'job':dict(job),'events':[dict(e) for e in self.db.execute('SELECT * FROM events WHERE job_id=? ORDER BY seq',(key,))]}

    def geometry(self):
        return {'width':120,'height':80,'locations':LOCATIONS,'scene':self.scene,
                'robots':{str(i):{'start':STARTS[i-1],'routes':{phase:points for phase,points in mission(i)}} for i in range(1,7)}}

    def close(self):
        with self.lock:self.db.close()
