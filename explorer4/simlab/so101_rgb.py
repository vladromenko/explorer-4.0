"""Frozen SO-101 actor with a calibrated top-down RGB camera and a known 32 mm cube."""
import hashlib
import math
import xml.etree.ElementTree as ET

import cv2
import mujoco
import numpy as np

from explorer4.sim.environment import SO101PickPlace
from explorer4.sim.models import so101_model
from .perception import cube_on_table

SIDE = .032
BOX = np.array([.24,.10,0.])   # Fixed surveyed fixture in the task model.
SIZE = 256
CAMERA = 'evaluation_overhead_rgb'
POSITION = [.215,.025,.56]
FOV = 43.
CAMERA_TO_BASE = np.diag([1.,-1.,-1.,1.])
CAMERA_TO_BASE[:3,3] = POSITION
FOCAL = SIZE / (2*math.tan(math.radians(FOV)/2))
K = np.array([[FOCAL,0,(SIZE-1)/2],[0,FOCAL,(SIZE-1)/2],[0,0,1.]])


def camera_model():
    xml,manifest = so101_model()
    root = ET.fromstring(xml)
    ET.SubElement(root.find('worldbody'),'camera',name=CAMERA,pos=' '.join(map(str,POSITION)),
                  xyaxes='1 0 0 0 1 0',fovy=str(FOV))
    instrumented = ET.tostring(root,encoding='unicode')
    return instrumented,{**manifest,'camera_xml_sha256':hashlib.sha256(instrumented.encode()).hexdigest()}


class OverheadScene(SO101PickPlace):
    model_builder = staticmethod(camera_model)


class CubeTracker:
    """Use the known cube edge when a full top face is visible. Hold the last measured point on occlusion."""
    def __init__(self):
        self.last = np.zeros(3)
        self.last_at = None
        self.mask = None

    def reset(self):
        self.last[:] = 0.
        self.last_at = None

    def measure(self,rgb,now):
        bgr = cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv,(5,120,120),(22,255,255))
        self.mask=mask
        contours,_ = cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        visible=False
        if contours:
            best=max(contours,key=cv2.contourArea)
            area=cv2.contourArea(best)
            _,axes,_=cv2.minAreaRect(best)
            width,height=sorted(v+1 for v in axes)
            # Perspective from a near-vertical view. A clipped or non-square component is not a depth observation.
            if area>40 and width/height>=.72 and area/(height*width)>=.64:
                depth=FOCAL*SIDE/max(width,height)
                centre_height=POSITION[2]-depth-SIDE/2
                if -.006<=centre_height<=.27:
                    centre_height=max(SIDE/2,centre_height)
                    point=cube_on_table(bgr,K,CAMERA_TO_BASE,centre_height+SIDE/2,min_area=40)
                    if point is not None:
                        point[2]=centre_height
                        self.last=point
                        self.last_at=now
                        visible=True
        age=1. if self.last_at is None else min(1.,max(0.,now-self.last_at))
        return self.last.copy(),int(visible),age


def simultaneous_jaw_contact(env):
    cube = env.model.geom('cube').id
    fixed=env.model.geom_bodyid[env.model.geom('fixed_jaw_box1').id]
    moving=env.model.geom_bodyid[env.model.geom('moving_jaw_box1').id]
    jaw_bodies=set()
    for a,b in zip(env.data.contact.geom1,env.data.contact.geom2):
        if cube==a or cube==b:
            jaw_bodies.add(env.model.geom_bodyid[b if cube==a else a])
    return fixed in jaw_bodies and moving in jaw_bodies


class PickBelief:
    """Localize on the table before approach, then propagate a grasp hypothesis with measured joint positions."""
    def __init__(self,model):
        self.model=model
        self.forward=mujoco.MjData(model)
        self.reset()

    def reset(self):
        self.pick=None
        self.offset=None
        self.released=None

    def observe(self,joints,rgb=None,*,constant=False):
        self.forward.qpos[:6]=joints
        mujoco.mj_kinematics(self.model,self.forward)
        tip=self.forward.site('gripperframe').xpos.copy()
        raw_visible=False
        if self.pick is None:
            if constant:
                self.pick=np.array([.24,-.06,SIDE/2])
            elif rgb is not None:
                first=cube_on_table(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),K,CAMERA_TO_BASE,SIDE,min_area=40)
                if first is not None:
                    self.pick=first.copy()
                    self.pick[2]=SIDE/2
                    raw_visible=True
        if self.pick is None:
            return np.zeros(3),0,1.,raw_visible
        opening=joints[5]
        if self.offset is None and self.released is None and opening<.46 and np.linalg.norm(tip-self.pick)<.035:
            self.offset=self.pick-tip
        if self.offset is not None:
            point=tip+self.offset
            if opening>.60:
                self.released=point.copy()
                self.offset=None
        elif self.released is not None:
            point=self.released
        else:
            point=self.pick
        # This distinct adapter uses the VALIDITY OF A POSE ESTIMATE for the actor's flag.
        # Acquisition is RGB; closure and co-motion are a hypothesis, never a grasp score.
        return point.copy(),1,0.,raw_visible
