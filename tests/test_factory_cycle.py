"""Offline checks of queueing, scripted workcells and deterministic reset."""
from factory_cycle_core import create_factory

lines=create_factory()
for _ in range(12000):
    for line in lines:
        line.step(.04)
        floor=sorted(p.x for p in line.parcels if p.mode in ('flow','waiting'))
        assert all(b-a>=1.349 for a,b in zip(floor,floor[1:])),floor
        for arm in line.arms:
            if arm.parcel is not None:
                item=line.parcels[arm.parcel]
                assert arm.released or item.arm==arm.index
for row,line in enumerate(lines):
    assert line.output>0,(row,line.output)
    assert all(a.cycles>0 for a in line.arms),(row,[a.cycles for a in line.arms])
    print('PASS line',row,'outfeed',line.output,'arm cycles',[a.cycles for a in line.arms])
a,b=create_factory(),create_factory()
for _ in range(100):
    for line in a:line.step(.04)
    for line in b:line.step(.04)
assert [[(p.x,p.mode) for p in l.parcels] for l in a]==[[(p.x,p.mode) for p in l.parcels] for l in b]
print('PASS: parcel spacing, all 8 arms process products, 4 lines output, deterministic replay')
