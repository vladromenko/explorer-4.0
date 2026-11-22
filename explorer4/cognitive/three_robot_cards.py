"""Three registered simulation roles for the colour-order docking demonstration."""
from .store import digest

ROLES = ('so101.read_dock_order.rgb.v1','rosmaster.measure_station.rgb.v1','tank.dock_ordered.geometric.v1')


def add(cards, file_hash):
    source='explorer4/sim/three_robot_dock.py'
    code=file_hash(source)
    roles=[
        (ROLES[0],'so101.pick_place.scripted.v1','observation','order_from_rgb','room_order_token','station_id_from_wrist_rgb'),
        (ROLES[1],'rosmaster.observe_dock.geometric.v1','observation','ThreeRobotDock.measure','ordered_dock','station_pose_from_wrist_rgb'),
        (ROLES[2],'tank.dock_observed.scripted.v1','geometric','ThreeRobotDock.drive','ordered_dock','stable_at_requested_station'),
    ]
    contracts = {
        ROLES[0]:({'image':'SO-101 wrist RGB'}, {'station':'colour ID or null','frame_sha256':'RGB digest'}),
        ROLES[1]:({'image':'ROSMASTER wrist RGB','order':'SO-101 station ID and source frame'},
                  {'station':'colour ID','target_xy_m':'metric waypoint','stamp_s':'simulation time'}),
        ROLES[2]:({'packet':'matched fresh metric waypoint','odometry':'body velocity and yaw rate'},
                  {'channels':['linear velocity','yaw rate'],'units':['m/s','rad/s']}),
    }
    for ident,base,kind,symbol,goal,effect in roles:
        parent=cards[base]
        cards[ident]=parent.model_copy(update={'skill_id':ident,'kind':kind,'source_ref':source+':'+symbol,
                'version':digest({'parent':parent.version,'code':code,'role':ident,'contract':contracts[ident]}), 'policy_sha256':code,
                'state_schema':contracts[ident][0],'action_schema':contracts[ident][1],
                'goals':[goal],'preconditions':['fresh_evidence','fixed_scene'],'postconditions':[effect],
                'sim_admission':'available','real_admission':'blocked',
                'verified_scope':['Two coloured badges on a surveyed wall and a matching tabletop order token.'],
                'limitation':'Fixed camera geometry and token colours in the shared MuJoCo room.'})
