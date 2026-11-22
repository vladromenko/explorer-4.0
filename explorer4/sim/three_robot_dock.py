"""SO-101 reads an order token, ROSMASTER measures a station, Tank docks in FleetWorld."""
import hashlib
import math

import cv2
import mujoco
import numpy as np

from .cooperation import CooperationWorld, OBSERVE_POSE
from ..peer_dock_config import MAX_AGE_S

# Printed square station badges and matching tokens; RGB HSV limits are fixed.
COLOURS = {'magenta':([.92,.04,.80,1.], (137,90,35), (166,255,255)),
           'blue':([.05,.14,.95,1.], (112,110,38), (129,255,255))}
SIDE_M = .185
STANDOFF = .285


def regions(image, colour, minimum):
    hsv = cv2.cvtColor(image,cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv,COLOURS[colour][1],COLOURS[colour][2])
    contours,_ = cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    return [c for c in contours if cv2.contourArea(c)>=minimum]


def order_from_rgb(image):
    counts = {k:sum(cv2.contourArea(c) for c in regions(image,k,200)) for k in COLOURS}
    visible = [k for k in counts if counts[k]>=350]
    return {'source_robot':'so101','station':visible[0] if len(visible)==1 else None,
            'frame_sha256':hashlib.sha256(image.tobytes()).hexdigest(),'colour_pixels':counts}


def quadrilateral(image, colour):
    candidates = []
    for contour in regions(image,colour,200):
        polygon=cv2.approxPolyDP(contour,.025*cv2.arcLength(contour,True),True)
        if len(polygon)==4 and cv2.isContourConvex(polygon):
            candidates.append(polygon[:,0,:].astype(float))
    if len(candidates)!=1:
        return None
    points = candidates[0]
    # World-up squares face the aisle. Top/bottom edges stay in the upper/lower image half.
    vertical = points[np.argsort(points[:,1])]
    top = vertical[:2][np.argsort(vertical[:2,0])]
    bottom = vertical[2:][np.argsort(vertical[2:,0])]
    return np.array([top[0],top[1],bottom[1],bottom[0]])


class ThreeRobotDock(CooperationWorld):
    def __init__(self,output,seed,preset):
        super().__init__(output,seed,preset)
        self.configure(seed)

    def configure(self,seed):
        super().reset(seed)
        model=self.world.model
        rng=np.random.default_rng(seed)
        self.required=list(COLOURS)[seed%2]  # scorer and token only
        model.geom('so101/cube').rgba[:]=COLOURS[self.required][0]
        # Reuse FleetWorld's existing freestanding dock: extend its backboard
        # and move the two square front patches onto opposite ends. Each
        # visible badge is real model geometry, rendered from both viewpoints.
        target=model.body('tank/target')
        centre=np.array([rng.uniform(1.09,1.18),1.1+rng.uniform(-.05,.05)])
        target.pos[:2]=centre
        backing=model.geom('tank/target_board')
        backing.size[:]=[.015,.335,.145]
        backing.rgba[:]=[.56,.53,.48,1.]
        for i in range(model.ngeom):
            name=model.geom(i).name
            if name and name.startswith('tank/fiducial_') and name!='tank/fiducial_sheet':
                model.geom(i).rgba[3]=0
        positions={}
        ysign=1 if (seed//2)%2 else -1
        for key,geom,side in [('magenta','tank/fiducial_sheet',ysign),('blue','tank/target_center',-ysign)]:
            badge=model.geom(geom)
            badge.pos[:]=[-.022,.195*side,0.]
            badge.size[:]=[.001,SIDE_M/2,SIDE_M/2]
            badge.rgba[:]=COLOURS[key][0]
            positions[key]=centre+badge.pos[:2]+[-STANDOFF-.001,0.]-self.world.views['tank'].origin[:2]
        self.goals=positions
        self.world.views['tank'].env.goal=np.r_[positions[self.required],0.]
        model.geom('tank/dock_zone').rgba[3]=0.
        mujoco.mj_forward(model,self.world.data)
        for item in self.world.views.values(): item.read(forward=True)
        self.initial=self.world.snapshot()

    def frame(self,robot,name):
        rgb=self.world.render(robot)
        cv2.imwrite(str(self.output/(name+'.png')),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        return rgb

    def observe_stations(self):
        for _ in range(60):
            self.world.step({'rosmaster':OBSERVE_POSE})
        self.world.hold_agent('rosmaster')
        return self.frame('rosmaster','rosmaster-stations')

    def measure(self,image,order):
        colour=order.get('station') if order else None
        if colour not in COLOURS:return None
        corners=quadrilateral(image,colour)
        if corners is None:return None
        camera=self.sensors.detectors['rosmaster']
        # The sensor gives metric position from the known badge size, never from scene target coordinates.
        h=SIDE_M/2
        obj=np.array([[-h,h,0.],[h,h,0.],[h,-h,0.],[-h,-h,0.]])
        n,rots,translations,errs=cv2.solvePnPGeneric(obj,corners,camera.K,camera.dist,flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if not n:return None
        idx=int(np.argmin(np.ravel(errs)))
        if float(np.ravel(errs)[idx])>2.5:return None
        origin,axes=self.sensors.camera_pose('rosmaster')
        target=origin+axes@translations[idx].ravel()
        return {'source_robot':'rosmaster','station':colour,'frame':'tank_start_map','stamp_s':float(self.world.data.time),
                'source_frame_sha256':hashlib.sha256(image.tobytes()).hexdigest(),'order_frame_sha256':order['frame_sha256'],
                'corners_px':corners.tolist(),'target_xy_m':(target[:2]-[STANDOFF,0]-self.world.views['tank'].origin[:2]).tolist(),
                'target_yaw_rad':0.,'reprojection_error_px':float(np.ravel(errs)[idx])}

    def drive(self,order,packet,*,record=False):
        age=self.world.data.time-packet['stamp_s'] if packet else None
        valid=bool(order and packet and packet['station']==order['station']
                   and packet['order_frame_sha256']==order['frame_sha256']
                   and packet['source_robot']=='rosmaster' and packet['frame']=='tank_start_map'
                   and 0<=age<=MAX_AGE_S and np.isfinite([*packet['target_xy_m'],packet['target_yaw_rad']]).all())
        tank=self.world.views['tank']
        commands=[]
        while valid and not tank.done:
            command=self.sensors.action(packet)
            self.world.step({'tank':command})
            self.sensors.integrate(tank.env.dt)
            commands.append([float(x) for x in command])
        self.world.stop()
        if record:
            self.frame('tank','tank-final')
            self.overview('team-final')
        measured=tank.env.info()
        return {'success':bool(valid and tank.result and tank.result[4]['outcome']=='success'),
                'accepted':valid,'actions':len(commands),'commands_sha256':hashlib.sha256(np.asarray(commands,dtype='<f8').tobytes()).hexdigest(),
                'first_command':commands[0] if commands else None, 'distance_to_ordered_dock_m':measured['distance_m'],
                'yaw_error_rad':measured['yaw_error_rad'],'stable_s':measured['stable_s'],
                'verified_by':'MobileDock.complete_step','consumed':packet if valid else None}

