"""Passive ROS graph/TF inventory on the configured robots and observation hub. No goal client."""
import argparse
import concurrent.futures
import json
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time


def probe():
    import rclpy
    from ament_index_python.packages import get_packages_with_prefixes
    from rclpy.action import get_action_server_names_and_types_by_node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from rclpy.time import Time
    from sensor_msgs.msg import LaserScan
    from nav_msgs.msg import Odometry
    from tf2_msgs.msg import TFMessage
    from tf2_ros import Buffer

    rclpy.init()
    node = rclpy.create_node("explorer_nav2_readiness", enable_rosout=False, start_parameter_services=False)
    buffer = Buffer()
    topics, edges, readings = {}, {}, {}
    subscriptions = []
    qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
    latched = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)

    def on_tf(topic, message):
        static = topic.endswith("/tf_static")
        for tf in message.transforms:
            parent, child = tf.header.frame_id, tf.child_frame_id
            if not parent or not child:
                continue
            edges[(parent, child)] = {"parent":parent, "child":child, "static":static}
            if static:
                buffer.set_transform_static(tf, "observed")
            else:
                buffer.set_transform(tf, "observed")

    def subscribe(topic, types):
        if "tf2_msgs/msg/TFMessage" in types and topic.split("/")[-1] in ("tf", "tf_static"):
            return node.create_subscription(TFMessage, topic, lambda m:on_tf(topic, m),
                                            latched if topic.endswith("/tf_static") else qos)
        kind = LaserScan if "sensor_msgs/msg/LaserScan" in types else Odometry if "nav_msgs/msg/Odometry" in types else None
        if kind is None:
            return None
        def receive(msg):
            item = readings.setdefault(topic, {"messages":0})
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            item.update(messages=item["messages"]+1, frame=msg.header.frame_id, ros_stamp_s=stamp)
            if kind is Odometry:
                item["child_frame"] = msg.child_frame_id
        return node.create_subscription(kind, topic, receive, qos)

    try:
        deadline = time.monotonic() + 5.
        while time.monotonic() < deadline:
            for topic, types in node.get_topic_names_and_types():
                if topic not in topics and set(types) & {"tf2_msgs/msg/TFMessage", "sensor_msgs/msg/LaserScan", "nav_msgs/msg/Odometry"}:
                    topics[topic] = types
                    subscription = subscribe(topic, types)
                    if subscription is not None:
                        subscriptions.append(subscription)
            rclpy.spin_once(node, timeout_sec=.08)
        now = node.get_clock().now().nanoseconds * 1e-9
        for item in readings.values():
            item["age_s"] = round(now-item["ros_stamp_s"], 3)
        servers = []
        nodes = node.get_node_names_and_namespaces()
        for name, namespace in set(nodes):
            try:
                for action, types in get_action_server_names_and_types_by_node(node,name,namespace):
                    if "nav2_msgs/action/NavigateToPose" in types:
                        servers.append({"action":action, "node":namespace.rstrip("/")+"/"+name, "types":types})
            except RuntimeError:
                continue
        names = {e["parent"] for e in edges.values()} | {e["child"] for e in edges.values()}
        exposed = names | {r["frame"] for r in readings.values()} | {r["child_frame"] for r in readings.values() if "child_frame" in r}
        prefixes = {""} | {f.split("/")[0]+"/" for f in exposed if "/" in f}
        lookups = []
        def lookup(target, source):
            if target not in names or source not in names or not buffer.can_transform(target, source, Time()):
                return False
            tf = buffer.lookup_transform(target, source, Time()).header.stamp
            return tf.sec + tf.nanosec == 0 or -.05 <= now - (tf.sec + tf.nanosec*1e-9) <= 1.
        for prefix in sorted(prefixes):
            for base in ("base_link","base_footprint"):
                for odom in ("odom","odom_raw"):
                    body, origin, world = prefix+base, prefix+odom, prefix+"map"
                    lasers = {r["frame"] for t,r in readings.items() if topics.get(t)==["sensor_msgs/msg/LaserScan"]
                              and r["frame"].rpartition("/")[0]==prefix.rstrip("/") and -.05 <= r["age_s"] <= 1.}
                    if body in exposed or origin in exposed or world in exposed:
                        lookups.append({"world":world,"odom":origin,"base":body,
                                        "map_to_odom":lookup(world,origin),"odom_to_base":lookup(origin,body),
                                        "base_to_laser":{laser:lookup(body,laser) for laser in sorted(lasers)}})
        packages = get_packages_with_prefixes()
        selected = {n:p for n,p in sorted(packages.items()) if n.startswith(("nav2_", "yahboomcar", "mentorpi"))
                    or n in {"navigation", "slam", "slam_toolbox", "robot_localization", "ros_robot_controller",
                             "controller_manager", "move_group", "moveit_ros_move_group", "controller", "peripherals",
                             "app","bringup","arm_msgs","orbbec_camera","tf2_ros"}}
        paths = []
        prior = None
        if os.getenv("ROS_DOMAIN_ID")=="0":
            home = Path("/home/ubuntu/ros2_ws/src")
            paths = [home/p for p in ("navigation/config/nav2_params.yaml","navigation/config/nav2_controller_dwb.yaml",
                     "navigation/launch/navigation.launch.py","driver/controller/controller/odom_publisher_node.py",
                     "driver/ros_robot_controller/ros_robot_controller/ros_robot_controller_sdk.py")]
        elif os.getenv("ROS_DOMAIN_ID")=="30":
            home = Path("/home/vlad/Projects/rosmaster_autonomous_collector")
            paths = [home/p for p in ("scripts/run_nav2_dry_run.sh","scripts/nav2_dry_run_client.py","config/nav2-dry-run.yaml",
                                     "logs/nav2-dry-run-20261102.json","config/explorer-map-20261030.yaml","config/explorer-map-20261030.pgm")]
            paths.extend(Path("/home/vlad/explorer3/native/cubebot")/p for p in ("robot_io.py","base_control.py","arm_model.py"))
            outcome=home/"logs/nav2-dry-run-20261102.json"
            if outcome.is_file():
                prior=json.loads(outcome.read_text())
        files={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}
        return {"distro":os.getenv("ROS_DISTRO"),"installed_file_sha256":files,"previous_isolated_planning_report":prior,"domain":os.getenv("ROS_DOMAIN_ID"),
                "localhost_only":os.getenv("ROS_LOCALHOST_ONLY"),"at_unix_s":time.time(),
                "graph_nodes":sorted(set(ns.rstrip("/")+"/"+n for n,ns in nodes if n!=node.get_name())),
                "navigate_to_pose_servers":servers,"topics":{k:{"types":v,"publishers":node.count_publishers(k),
                    "publisher_nodes":sorted({x.node_namespace.rstrip("/")+"/"+x.node_name for x in node.get_publishers_info_by_topic(k)})} for k,v in topics.items()},
                "frames_received":readings,"tf_edges":sorted(edges.values(),key=lambda e:(e["parent"],e["child"])),
                "latest_tf_lookups":lookups,"visible_packages":selected}
    finally:
        node.destroy_node()
        rclpy.shutdown()


def compare_saved_map(yaml_path, view):
    """Replay Explorer planning on the exact map used by the existing isolated Nav2 planner trial."""
    import cv2
    import math
    import numpy as np
    import yaml
    from explorer4 import navigation
    from explorer4.fleet_map import Grid, RES, SIZE

    prior=view.get("previous_isolated_planning_report")
    if not prior or prior.get("status")!="PASS" or not prior.get("isolated_from_robot") or prior.get("actuator_commands")!=0:
        raise ValueError("The original isolated planning result is unavailable")
    setup=yaml.safe_load(yaml_path.read_text())
    if setup["mode"]!="trinary" or setup["resolution"]!=RES or setup["origin"][2]!=0 or setup["negate"]!=0:
        raise ValueError("This archived map requires a different grid conversion")
    image=yaml_path.parent/setup["image"]
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (yaml_path,image)}
    remote=view["installed_file_sha256"]
    if not all(digest==remote.get("/home/vlad/Projects/rosmaster_autonomous_collector/config/"+name) for name,digest in hashes.items()):
        raise ValueError("Local map differs from the recorded ROSMASTER setup")
    occupied_probability=1-np.flipud(cv2.imread(str(image),cv2.IMREAD_GRAYSCALE)).astype(float)/255
    grid=Grid()
    iy,ix=np.indices((SIZE,SIZE))
    # Nearest original map cell for each Explorer cell centre. The map-server and Explorer origins differ.
    x=np.floor(((ix-SIZE//2+.5)*RES-setup["origin"][0])/RES).astype(int)
    y=np.floor(((iy-SIZE//2+.5)*RES-setup["origin"][1])/RES).astype(int)
    inside=(x>=0)&(y>=0)&(x<occupied_probability.shape[1])&(y<occupied_probability.shape[0])
    occupancy=occupied_probability[y[inside],x[inside]]
    grid.hits[inside]=occupancy>setup["occupied_thresh"]
    grid.free[inside]=occupancy<setup["free_thresh"]
    start,goal=prior["start"],prior["goal"]
    route=navigation.plan(grid,"rosmaster",start,goal,allow_unknown=False)
    blocked,_,_=navigation.layers(grid,"rosmaster")
    gx,gy=navigation._cell(goal)
    endpoint=navigation.path_endpoint(goal,route)
    endpoint_error=endpoint["endpoint_offset_m"]
    return {"map_sha256":hashes,"start_m":start,"goal_m":goal,"original_nav2":prior,"original_nav2_endpoint_coordinates_saved":False,
            "explorer":{"grid_resolution_m":navigation.PRES,"unknown_traversal":False,
                "inflation_radius_m":navigation.RADIUS["rosmaster"],"waypoints_m":route,
                "path_length_between_returned_waypoints_m":None if route is None else sum(math.dist(a,b) for a,b in zip(route,route[1:])),
                "first_waypoint_error_m":None if route is None else math.dist(route[0],start),
                "requested_cell_in_inflation":bool(blocked[gy,gx]),"goal_cell_relocated":endpoint["goal_cell_relocated"],"terminal_waypoint_error_m":endpoint_error,
                "terminal_within_8cm_dock_tolerance":endpoint_error is not None and endpoint_error<.08},
            "scope":"Planner-only historical NavFn and current Explorer A* on the same provisional map and requested pose. Cell-centre sampling and planner tolerances differ. No drive, localization or route-time comparison."}


def collect(map_file=None):
    from explorer4 import fleet_config
    from explorer4.paths import DATA

    robot_cfg = json.loads((DATA/"configs/rosmaster-agent.json").read_text())
    ssh = ["ssh","-o","BatchMode=yes","-o","ConnectTimeout=4","-o","StrictHostKeyChecking=yes"]
    payload=Path(__file__).read_text()
    def invoke(label):
        site, local = label.split("/")
        if site in ("tank","rosmaster") and not fleet_config.robot_allowed(site)[0]:
            return {"available":False,"reason":"Panel robot switch is off"}
        if site=="hub":
            cmd=["docker","exec","-i","-u","ubuntu","-e","FASTRTPS_DEFAULT_PROFILES_FILE=/workspace/agents/ros2_hub/fastdds.xml",
                 "explorer3-ros2-hub","bash","-c","source /opt/ros/jazzy/setup.bash && exec python3 - --probe"]
        elif site=="tank":
            shell=f"source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY={local} && exec /usr/bin/python3 - --probe"
            cmd=[*ssh,"tank", shlex.join(["docker","exec","-i","-u","ubuntu","MentorPi","bash","-c",shell])]
        else:
            shell=f"source /home/vlad/explorer3/environment.sh && export ROS_LOCALHOST_ONLY={local} && exec /usr/bin/python3 - --probe"
            cmd=[*ssh,"-i",str(Path.home()/".ssh/rosmaster-collector"),robot_cfg.get("ssh_user","vlad")+"@"+robot_cfg["host"],
                 shlex.join(["bash","-c",shell])]
        try:
            proc=subprocess.run(cmd,input=payload,capture_output=True,text=True,timeout=38)
            if proc.returncode:
                return {"available":False,"reason":proc.stderr.strip().splitlines()[-1][:200]}
            return {"available":True,**json.loads(proc.stdout.strip().splitlines()[-1])}
        except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
            return {"available":False,"reason":type(exc).__name__}
    labels=["tank/1","tank/0","rosmaster/1","rosmaster/0","hub/1"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(labels)) as pool:
        results=dict(zip(labels,pool.map(invoke,labels)))
    readiness={}
    for robot in ("tank","rosmaster"):
        views=[v for label,v in results.items() if label.startswith(robot+"/") and v["available"]]
        servers=[a for v in views for a in v["navigate_to_pose_servers"]]
        # All prerequisites must occur within the same DDS view and same odometry frame chain.
        matched=[]
        for v in views:
            for row in v["latest_tf_lookups"]:
                odometry=any(r.get("frame")==row["odom"] and r.get("child_frame") in (row["base"],row["base"].replace("base_link","base_footprint"))
                             and -.05<=r["age_s"]<=1 for r in v["frames_received"].values())
                if row["map_to_odom"] and row["odom_to_base"] and any(row["base_to_laser"].values()) and odometry:
                    matched.append({"domain":v["domain"],"localhost_only":v["localhost_only"],"chain":row,
                                    "server_in_same_view":bool(v["navigate_to_pose_servers"])})
        readiness[robot]={"sampled_views":len(views),"navigate_to_pose_server_seen":bool(servers) if views else None,
                          "full_observed_chain":matched,"observation_prerequisites_present":any(x["server_in_same_view"] for x in matched) if views else None,
                          "authorization":"Observation only. Motor ownership and physical clearance are separate."}
    comparison=None
    if map_file is not None:
        comparison=compare_saved_map(map_file,results["rosmaster/1"])
    return {"checked_at":time.time(),"nav2_readiness":readiness,"same_map_comparison":comparison,"mode":"Ephemeral ROS graph discovery, five seconds per view; only scan, odometry and TF subscriptions.",
            "motion_commands_sent":0,"services_called":0,"goals_sent":0,"views":results}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe",action="store_true")
    parser.add_argument("--out",type=Path)
    parser.add_argument("--collector-map",type=Path,help="Optional provisional ROS map YAML from the old collector")
    args=parser.parse_args()
    if args.probe:
        print(json.dumps(probe()))
    elif args.out:
        from explorer4.fleet_config import atomic_write
        atomic_write(args.out, collect(args.collector_map))
    else:
        parser.error("--out is required")
