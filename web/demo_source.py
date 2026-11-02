"""Explicitly labelled synthetic telemetry, isolated from ROS and live inventory."""
import math
import threading
import time
from warehouse_routes import mission
from factory_cycle_core import create_factory
from factory_surfaces import support_height,CONTACT_GAP


class DemoSource:
    def __init__(self,store):
        self.store=store;self.stop=threading.Event();self.started=time.monotonic()
        self.lines=create_factory();self.last_sim=0.
        for sku,name,qty,loc in [('MTR-024','Động cơ servo 24V',240,'storage_left'),('PCB-100','Bo mạch điều khiển',180,'storage_left'),('KIT-A12','Bộ linh kiện A12',320,'storage_right'),('PKG-040','Hộp đóng gói tiêu chuẩn',480,'storage_right')]:
            store.intake({'sku':sku,'name':name,'qty':qty,'unit':'thùng','location':loc,'minimum':40})
        for sku,dest,qty in [('MTR-024','assembly',8),('KIT-A12','packing',12),('PCB-100','assembly',6),('PKG-040','packing',10)]:
            store.create_job({'sku':sku,'qty':qty,'destination':dest,'priority':1})
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    @staticmethod
    def position(points,age,speed=.9):
        for a,b in zip(points,points[1:]):
            length=math.dist(a,b);duration=length/speed
            if age<=duration:
                f=age/duration
                return a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f,math.atan2(b[1]-a[1],b[0]-a[0]),False
            age-=duration
        a,b=points[-2:];return b[0],b[1],math.atan2(b[1]-a[1],b[0]-a[0]),True

    def run(self):
        from warehouse_routes import STARTS
        # Demo has accelerated time; each active AGV still follows the authored route.
        while not self.stop.wait(.1):
            sim=(time.monotonic()-self.started)*6
            states={}
            for offset in (0,3):
                routes=mission(1+offset)
                durations=[sum(math.dist(a,b) for a,b in zip(pts,pts[1:]))/.9+3 for _,pts in routes]
                total=sum(durations);turn=int(sim//total);active=offset+1+turn%3;age=sim%total
                for i in range(offset+1,offset+4):
                    states[str(i)]={'phase':'parked','loaded':False,'active':False,'completed':max(0,(turn-(i-offset-1)+2)//3)}
                    if i!=active:
                        x,y=STARTS[i-1];self.store.pose(i,x,y,0,sim);self.store.scan(i)
                routes=mission(active)
                durations=[sum(math.dist(a,b) for a,b in zip(pts,pts[1:]))/.9+3 for _,pts in routes]
                # Recompute per-robot durations with a common normalized cycle progress.
                age=(sim%total)/total*sum(durations)
                for index,(name,points) in enumerate(routes):
                    if age<durations[index]:break
                    age-=durations[index]
                x,y,a,dwell=self.position(points,age)
                self.store.pose(active,x,y,a,sim);self.store.scan(active)
                states[str(active)].update(phase=name,loaded=name=='drop',active=True,at_station=dwell)
            self.store.update_clock(sim);self.store.factory_heartbeat(True)
            self.store.factory_state({'version':1,'run_id':'demo-session','sim_time':sim,'running':True,'held':False,'fault':None,'robots':states})
            for line in self.lines:line.step(max(0.,sim-self.last_sim))
            self.last_sim=sim
            belts=[];arms=[]
            keys=(self.store.scene or {}).get('demo_arm_keyframes',[])
            for i,line in enumerate(self.lines):
                parcels=[]
                points_by_arm={}
                for a in line.arms:
                    age=a.age if a.parcel is not None else 0.
                    points=[]
                    if keys:
                        left,right=keys[-2:]
                        for left,right in zip(keys,keys[1:]):
                            if age<=right['time']:break
                        f=max(0.,min(1.,(age-left['time'])/(right['time']-left['time'])))
                        local=[[u+(v-u)*f for u,v in zip(p,q)] for p,q in zip(left['points'],right['points'])]
                        bx,by=11+a.index*10,(10,23)[i]-2.4
                        points=[[bx-v[1],by+v[0],1.1+v[2]] for v in local]
                    points_by_arm[a.index]=points
                    phase='idle' if a.parcel is None else 'picking' if age<1.2 else 'carrying' if age<3.4 else 'placing' if age<4.15 else 'returning'
                    arms.append({'id':i*4+a.index+1,'line':i+1,'cell':a.index+1,'cycles':a.cycles,'state':phase,'points':points})
                y=(10,23,8,21)[i]
                belt=self.store.scene['belts'][i]
                for item in line.parcels:
                    z=support_height(belt,item.x,belt['parcel_size'][0]/2)+belt['parcel_size'][2]/2+CONTACT_GAP
                    pos=[item.x,y,z]
                    if item.mode=='carried' and item.arm is not None and points_by_arm.get(item.arm):
                        pos=list(points_by_arm[item.arm][-1]);pos[2]-=belt['parcel_size'][2]/2
                    parcels.append({'id':item.index,'position':pos,'mode':item.mode,'visible':item.mode!='outfeed'})
                belts.append({'id':i+1,'name':('Lắp ráp' if i<2 else 'Đóng gói')+f' {i%2+1}','speed':line.speed,'outputs':line.output,'running':True,'parcels':parcels})
            self.store.factory_telemetry({'version':1,'factory_time':sim,'physics_steps':int(sim*60),'running':True,'failed':False,'belts':belts,'arms':arms,'arm_cycles':sum(a['cycles'] for a in arms),'belt_outputs':sum(b['outputs'] for b in belts)})

    def close(self):self.stop.set();self.thread.join(timeout=2.)
