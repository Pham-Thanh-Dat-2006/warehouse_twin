"""Forward kinematics of the user's Comau model, using its USD joint frames."""
import math
import numpy as np


def axis_rotation(axis,angle):
    c,s=math.cos(angle),math.sin(angle)
    m=np.eye(4)
    if axis=='X':m[:3,:3]=[[1,0,0],[0,c,s],[0,-s,c]]
    elif axis=='Y':m[:3,:3]=[[c,0,-s],[0,1,0],[s,0,c]]
    else:m[:3,:3]=[[c,s,0],[-s,c,0],[0,0,1]]
    return m


def forward(rig,q):
    world={'base_link':np.array(rig['base'],dtype=float)}
    for joint,angle in zip(rig['joints'],q):
        world[joint['child']]=np.linalg.inv(joint['f1'])@axis_rotation(joint['axis'],angle)@joint['f0']@world[joint['parent']]
    return world


def blend(a,b,t):
    t=max(0.,min(1.,t));t=t*t*(3-2*t)
    return [x+(y-x)*t for x,y in zip(a,b)]


def angles_at(plan,t):
    keys=plan['keyframes']
    for a,b in zip(keys,keys[1:]):
        if t<=b['time']:return blend(a['q'],b['q'],(t-a['time'])/(b['time']-a['time']))
    return keys[-1]['q']
