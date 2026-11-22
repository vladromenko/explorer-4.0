"""Post-hoc sequential scan-then-request control on the 24 opened screen-study development worlds."""
import argparse
import fcntl
import json
from pathlib import Path
from statistics import mean
from unittest.mock import patch

from explorer4.paths import DATA, ROOT
from scripts.peer_dock_study import digest, frozen
from explorer4.sim.state_codec import load

SOURCE = DATA / "runs/peer-screen-dock-v2"
DEFAULT = DATA / "simlab/reports/peer-screen-sequential-development"
ROOMS = {"train": ("workshop_screen", range(861000,861016)),
         "calibration": ("storage_screen", range(862000,862008))}


def read(path):
    return json.loads(path.read_text())


def register(out):
    original=read(SOURCE/"protocol.json")
    files={name:h for name,h in original["software_hashes"].items() if name.startswith("explorer4/")}
    files["scripts/peer_sequential_control.py"]=digest(Path(__file__))
    for name,h in files.items():
        if digest(ROOT/name)!=h:
            raise ValueError("Source differs from registered version: "+name)
    scenes=[]
    for split,(room,seeds) in ROOMS.items():
        for seed in seeds:
            directory=SOURCE/split/str(seed)
            start=read(directory/"start.json")
            if start["room"]!=room or start["seed"]!=seed or digest(directory/"initial-state.json")!=start["initial_state_sha256"]:
                raise ValueError("Wrong registered starting state")
            scenes.append({**start,"split":split,"initial_rgb_sha256":read(directory/"decision.json")["local_image_sha256"]})
    spec={"version":1,"label":"post_hoc_open_development_only","parent_protocol_sha256":digest(SOURCE/"protocol.json"),
          "source_sha256":files,"scenes":scenes,"training_updates":0,"test_scenes":0,
          "decision":"First consume the initial onboard RGB if valid, otherwise use the unchanged v2 active scan (up to 3 s). Only if no packet exists after that scan, hold Tank and call the unchanged 3 s donor observation in the CURRENT world. Dock with the first valid local or fresh donor packet. No retry after a valid but unsuccessful dock.",
          "time":"Single continuous MuJoCo clock and task horizon from archived reset. Delayed helper can cost 3 s extra relative to either exclusive sensing arm (up to 6 s combined). Twist odometry is integrated while the donor moves, including Tank settling. No branching, rewind or post-donor state replacement.",
          "primary":"Independent frozen stable-docking verifier. Report success, calls, all simulated seconds and utility = success - 0.10*calls - 0.005*seconds. Compare against opened per-seed v2 active-only and always-donor outcomes after sequential completion.",
          "operator":"No robot transport, training, learned selector, threshold search or inspection of unopened outcomes."}
    frozen(out/"protocol.json",spec)
    return spec


def run_room(spec, out, split):
    import cv2
    from explorer4.sim.cooperation import CooperationWorld
    cv2.setNumThreads(1)

    class Sequential(CooperationWorld):
        def dock(self, packet, *, save=True, on_tick=None):
            now=lambda:float(self.world.data.time)
            self.event={"local_search_end_s":now(),"calls":0,"donor_end_s":None,
                        "onboard_packet":packet is not None,"donor_packet":False}
            if packet is None:
                self.event["calls"]=1
                self.world.hold_agent("tank")
                self.event["request_odometry"]=self.sensors.odometry.tolist()
                step=self.world.step
                def step_with_encoders(*args,**kwargs):
                    before=now()
                    result=step(*args,**kwargs)
                    self.sensors.integrate(now()-before)
                    return result
                with patch.object(self.world,"step",step_with_encoders):
                    seen=self.observe(save=True)
                packet=seen["packet"]
                self.event.update(donor_end_s=now(),donor_packet=packet is not None,
                                  helper_received=seen["helper_outcome"],donor_image_sha256=digest(self.output/"donor-observation.png"),
                                  after_observation_odometry=self.sensors.odometry.tolist(),recipient_held=seen["recipient_held"])
            self.event["dock_start_s"]=now()
            return super().dock(packet,save=save,on_tick=on_tick)

    scenes=[s for s in spec["scenes"] if s["split"]==split]
    room=scenes[0]["room"]
    world=Sequential(out/"scratch"/room,scenes[0]["seed"],room)
    try:
        for scene in scenes:
            folder=out/str(scene["seed"])
            folder.mkdir(exist_ok=True)
            if (folder/"result.json").exists():
                continue
            world.output=folder
            world.reset(scene["seed"])
            world.world.restore(load(SOURCE/split/str(scene["seed"])/"initial-state.json"))
            if world.world.manifest["xml_sha256"]!=scene["world_model_sha256"] or abs(world.world.data.time)>1e-9:
                raise ValueError("Reset clock or shared scene differs")
            initial=world.camera("tank","initial")
            initial_image=digest(folder/"initial.png")
            # Pixel renderers can differ between EGL and software; record exact agreement and compare initial detected packet.
            archived=read(SOURCE/split/str(scene["seed"])/"decision.json")["local_packet"]
            if (initial["packet"] is None)!=(archived is None):
                raise ValueError("Initial onboard visibility differs from the open v2 trial")
            result=world.local_scan(initial["packet"],save=True)
            row={"seed":scene["seed"],"split":split,"room":room,"initial_state_sha256":scene["initial_state_sha256"],
                 "initial_rgb_sha256":initial_image,"initial_rgb_identical":initial_image==scene["initial_rgb_sha256"],
                 "clock_start_s":initial["simulation_time_s"],"initial_marker":initial["packet"] is not None,
                 "protocol_sha256":digest(out/"protocol.json"),**world.event,"verifier":result}
            frozen(folder/"result.json",row)
            print(room,scene["seed"],result["task"],world.event["calls"],round(result["simulation_time_s"],2),flush=True)
    finally:
        world.close()


def summarize(spec,out):
    development=read(SOURCE/"development.json")["rows"]
    baseline={r["seed"]:r for r in development}
    rows=[]
    for scene in spec["scenes"]:
        record=read(out/str(scene["seed"])/"result.json")
        v=record["verifier"]
        prior=baseline[scene["seed"]]
        if record["protocol_sha256"]!=digest(out/"protocol.json") or prior["room"]!=record["room"]:
            raise ValueError("Mismatched provenance")
        row={k:record[k] for k in ("seed","split","room","initial_rgb_identical","initial_marker","onboard_packet",
              "local_search_end_s","calls","donor_end_s","donor_packet","dock_start_s")}
        row.update(success=int(v["task"]=="success"),seconds=v["simulation_time_s"],distance_m=v["distance_m"],
                   stable_s=v["stable_s"],yaw_rad=v["yaw_error_rad"],packet_age_s=v["packet_age_s"],reason=v["reason"],
                   packet_source=(v["consumed_packet"] or {}).get("source_robot"),command_hash=v["commands_sha256"],
                   local_only=prior["local"],local_s=prior["local_time_s"],immediate_peer=prior["peer"],peer_s=prior["peer_time_s"])
        rows.append(row)
    stats={}
    for name,win,t,owner in (("sequential","success","seconds","calls"),("active_local","local_only","local_s",None),
                              ("immediate_peer","immediate_peer","peer_s","always")):
        calls=[r[owner] if owner=="calls" else int(owner=="always") for r in rows]
        stats[name]={"successes":sum(r[win] for r in rows),"n":len(rows),"calls":sum(calls),
                     "total_s":sum(r[t] for r in rows),"mean_s":mean(r[t] for r in rows),
                     "mean_utility":mean(r[win]-.10*c-.005*r[t] for r,c in zip(rows,calls))}
    report={"status":"completed","phase":"post_hoc_development_only","protocol_sha256":digest(out/"protocol.json"),
            "test_scenes":0,"training_updates":0,"physical_robot_commands":0,"summary":stats,"rows":rows}
    frozen(out/"summary.json",report)
    print(json.dumps(stats),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,default=DEFAULT)
    parser.add_argument("--prepare",action="store_true")
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    with (args.out/".lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        spec=register(args.out)
        if not args.prepare:
            for split in ROOMS:
                run_room(spec,args.out,split)
            summarize(spec,args.out)
