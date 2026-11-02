"""Deterministic scripted factory flow; no ROS, USD, or physical grasp solver."""
import math
from dataclasses import dataclass,field


@dataclass
class Parcel:
    index:int
    x:float
    mode:str='flow'
    processed:set=field(default_factory=set)
    arm:int|None=None


@dataclass
class Workcell:
    index:int
    pick:float
    place:float
    parcel:int|None=None
    age:float=0.
    released:bool=False
    cycles:int=0


class BeltLine:
    def __init__(self,x0,x1,positions,stations=(),speed=.30,transfer=0.):
        self.x0=x0;self.x1=x1;self.transfer=transfer;self.speed=speed;self.output=0
        self.parcels=[Parcel(i,x,processed={j for j,p in enumerate(stations) if x>p+.01}) for i,x in enumerate(positions)]
        self.arms=[Workcell(j,p,p+.9) for j,p in enumerate(stations)]
        self.time=0.

    def step(self,dt):
        if dt<0:raise ValueError('dt must be nonnegative')
        n=max(1,math.ceil(dt/.04))
        for _ in range(n):self._step(dt/n)

    def _step(self,dt):
        self.time+=dt
        for arm in self.arms:
            if arm.parcel is None:continue
            arm.age+=dt
            item=self.parcels[arm.parcel]
            if arm.age>=1.2 and not arm.released:item.mode='carried'
            if arm.age>=4.15 and not arm.released:
                item.mode='flow';item.x=arm.place;item.processed.add(arm.index);item.arm=None
                arm.released=True
            if arm.age>=6.4:
                arm.parcel=None;arm.age=0.;arm.released=False;arm.cycles+=1
        # Advance downstream first; a stop gate at each active station prevents pass-through.
        ordered=sorted((p for p in self.parcels if p.mode in ('flow','waiting')),key=lambda p:p.x,reverse=True)
        front=None
        for item in ordered:
            if item.mode=='waiting':
                front=item.x;continue
            target=item.x+self.speed*dt
            if front is not None:target=min(target,front-1.35)
            target=max(item.x,target)
            for arm in self.arms:
                if arm.index in item.processed:continue
                if item.x<=arm.pick+.03 and target>=arm.pick:
                    target=arm.pick
                    if arm.parcel is None:
                        free=all(other.index==item.index or other.mode not in ('flow','waiting') or abs(other.x-arm.place)>1.35 for other in self.parcels)
                        if free:
                            arm.parcel=item.index;arm.age=0.;arm.released=False
                            item.mode='waiting';item.arm=arm.index
                    break
            item.x=target;front=item.x
            if item.x>self.x1+self.transfer:
                item.mode='outfeed';self.output+=1
        # Respawn at the inlet only when the preceding parcel has cleared it.
        for item in self.parcels:
            if item.mode=='outfeed' and all(other.index==item.index or other.mode not in ('flow','waiting') or abs(other.x-self.x0)>1.35 for other in self.parcels):
                item.x=self.x0;item.mode='flow';item.processed.clear();item.arm=None


def create_factory():
    assembly=[BeltLine(7,45,[8.3+i*2.8 for i in range(13)],stations=[10.55,20.55,30.55,40.55]) for _ in range(2)]
    packing=[BeltLine(55.5,94.5,[56.8+i*2.8 for i in range(13)],transfer=4.) for _ in range(2)]
    return assembly+packing
