"""Pure route/coordinate helpers for repeatable warehouse cycles (no ROS)."""
import math

STARTS = [(10,33),(10,38.2),(10,43.4),(110,35.6),(110,40.8),(110,46)]
PICKUPS = {'assembly': (43,49), 'packing': (85,49)}
DROPS = {'assembly': (47,23), 'packing': (91,27)}


def mission(robot):
    x,y = STARTS[robot-1]
    if robot <= 3:
        return [('pickup', [(x,y),(20,y),(20,46),(43,46),PICKUPS['assembly']]),
                ('drop', [PICKUPS['assembly'],(43,46),(48.8,46),(48.8,23),DROPS['assembly']]),
                ('park', [DROPS['assembly'],(52,23),(52,34),(20,34),(20,y),(x,y)])]
    return [('pickup', [(x,y),(101,y),(101,46),(85,46),PICKUPS['packing']]),
            ('drop', [PICKUPS['packing'],(85,46),(91,46),DROPS['packing']]),
            ('park', [DROPS['packing'],(91,31),(99,31),(99,40),(101,40),(101,y),(x,y)])]


def distance(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])


def segment_distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    return distance(p,(a[0]+t*dx,a[1]+t*dy))


def sample_polyline(points, step=1.5):
    out=[tuple(points[0])]
    for a,b in zip(points,points[1:]):
        n=max(1,math.ceil(distance(a,b)/step))
        out.extend((a[0]+(b[0]-a[0])*k/n,a[1]+(b[1]-a[1])*k/n) for k in range(1,n+1))
    return out


def yaw(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))


def correction(world, odom):
    """Planar map->odom such that map->base equals the measured world pose."""
    angle=math.atan2(math.sin(world[2]-odom[2]),math.cos(world[2]-odom[2]))
    c,s=math.cos(angle),math.sin(angle)
    return world[0]-c*odom[0]+s*odom[1], world[1]-s*odom[0]-c*odom[1], angle


def freshness_issues(seen, sim, wall, sim_timeout=.7, wall_timeout=3.0):
    """Check simulation-stamp age plus a bounded wall-clock transport deadline."""
    issues=[]
    for robot in range(1,7):
        for stream in ('world','odom','pair','scan'):
            sample=seen.get((robot,stream))
            if sample is None:
                issues.append(f'robot{robot}/{stream}: missing')
                continue
            stamp,receipt=sample
            sim_age=max(0.,sim-stamp*1e-9)
            wall_age=max(0.,wall-receipt)
            if sim_age>sim_timeout or wall_age>wall_timeout:
                issues.append(f'robot{robot}/{stream}: sim_age={sim_age:.3f}s wall_age={wall_age:.3f}s')
    return issues


def match_pose_stamp(stamp, other, slop_ns=20_000_000):
    if stamp in other:return stamp
    if not other:return None
    near=min(other,key=lambda key:abs(key-stamp))
    return near if abs(near-stamp)<=slop_ns else None
