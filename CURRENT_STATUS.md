# Explorer 4.0 current status

## 24 November 2026

In one supervised physical pilot, ROSMASTER supplied a goal at an unmarked shelf and Tank drove toward it. A camera freshness check stopped the first leg. Tank resumed from the stopped position after two fresh lidar registrations agreed and ROSMASTER re-observed the same shelf. The resumed approach reached the goal in 8.9 seconds. Ten stationary scans after disarming put the endpoint 2.1–2.9 cm from the goal and 5.3–5.9 degrees from the requested heading. These checks use Tank's lidar, and the pilot includes one interruption and no paired physical control. [Physical pilot result](docs/results/markerless-shelf-20261124/physical-pilot-continuation.json) · [Verified Tank limits](docs/results/markerless-shelf-20261124/tank-verified.json)

Before the drive, one RGB-D exposure pair registered the two cameras to each other. Across seven further pairs from the same placement, the ROSMASTER-only goal agreed with the goal computed from Tank's own camera within 0.8 mm and 0.12 degrees. A 10 cm lateral offset passed four offline scan replays after the first replay informed the choice. This measured repeatability at one placement. [RGB-D registration and scan replay](docs/results/markerless-shelf-20261124/result.json)

A markerless optical endpoint check reconstructed Tank's stopped pose from the front plane and left divider, with a corner annotation chosen on the saved endpoint frame. It put Tank 2.9 cm from the planned target and 5.3 degrees from the planned heading using RGB-D and no lidar pose. In four archived paired replays with the original images, local and selective control both reached the target in the static-scan simulator and no assistance was requested. Masking the right edge in the local RGB image caused four local abstentions. Selective control requested the peer observation in all four cases and the simulated approach reached the target in each. Ten later exposures showed the shelf from ROSMASTER's native near preset, with at most 1.6 mm goal disagreement at the same placement. The paired physical series remains to be run. [Optical endpoint and paired replay](docs/results/markerless-shelf-20261124/paired-optical-replay.json) · [Reachable donor preset](docs/results/markerless-shelf-20261124/near-donor-check.json)

ROSMASTER recovered from its folded arm position in 4.2 seconds using the native preset. All six encoders finished within 1.0 degree of the target and the chassis measured zero velocity throughout the sampled motion. In a separate stopped check the camera measured the blue-topped cube in ten frames, approximately 29.7 cm forward in the nominal base frame. Its top was approximately 30 mm above the local depth-fitted floor. The trained and evaluated workspace ends at 25 cm, and nominal low-grasp IK rejected the measured point. The depth check pairs fresh camera data with native joint feedback and uses no actuator calls. [Arm log](http://192.168.0.168:8030/simlab-media/reports/rosmaster-live-20261124/arm-preparation.json) · [Cube observations](http://192.168.0.168:8030/simlab-media/reports/rosmaster-live-20261124/cube-visibility.json) · [Read-only capture](scripts/rosmaster_depth_readiness.py)

Before charging, ROSMASTER supplied ten more registered RGB-D frames with native encoder feedback and five dual-lidar packets with odometry. Across nine comparisons between two arm poses, the median difference between image-derived and nominal camera translation was 12.3 mm. The three same-pose comparisons had a median difference of 0.35 mm. This measures relative registration on one scene. A depth-only detector fitted the floor and isolated the cube in all ten archived frames of one placement, agreeing with the colour-assisted depth estimate to within 3.2 mm. The two estimates share the same camera calibration. [Sensor archive summary](http://192.168.0.168:8030/simlab-media/reports/rosmaster-live-20261124/field-closeout.json) · [Camera motion comparison](http://192.168.0.168:8030/simlab-media/reports/rosmaster-live-20261124/camera-relative-motion.json) · [Depth-only replay](http://192.168.0.168:8030/simlab-media/reports/rosmaster-live-20261124/clustered-depth-shadow.json)

The varied cube development bank tests four ranges, three lateral placements, three yaw angles, two hand starts and seeded appearance changes. The stationary-depth arm controller achieved 26/27 retentions. The revised sequential depth-guided base and arm simulator achieved 9/9 retentions on the distant development scenes. A separate bank yielded 35 demonstrations. The matched ACT and Diffusion jobs use a 27/4/4 split with the same 3,000-update budget. [Position and yaw results](docs/results/varied-floor-cube-v1/development.json) · [Distant scenes](http://192.168.0.168:8030/simlab-media/reports/varied-floor-cube-v1/mobile-development-v3/result.json) · [LeRobot jobs](http://192.168.0.168:8030/simlab-media/reports/varied-floor-cube-v1/training/queue.json)

## 23 November 2026


The six end-to-end ACT controls retained the cube on none of twelve common starts per model. The same reset-state hashes had no visible cube pixels in the starting camera frames. A bounded look followed by calibrated simulated depth and the existing inverse-kinematics controller retained the cube on all twelve of those starts and sixteen additional prespecified starts. The success endpoint required both jaws on the cube, more than 50 mm lift and the configured carry pose throughout the final second. Depth is generated by the simulator and assumes correct camera-to-base registration. The changed system-level comparison adds this sensing channel and changes the motor controller. It does not isolate a training effect. Reproduce on Homebrain with `MUJOCO_GL=egl OPENBLAS_NUM_THREADS=1 .venv-sim/bin/python -m scripts.grasp_study.depth_floor_recovery`. [Frozen protocol and results](docs/results/floor-depth-recovery-v1/) · [Simulator figure](http://192.168.0.168:8030/simlab-media/reports/floor-depth-recovery-v1/carry-comparison.svg)

On Homebrain the common-deadline docking pilot finished all 64 branches on 16 new scenes. Both local-first and the adaptive selector completed 13 with six requests. Local-only completed eight. Historical raw ACT completed three of twenty starts with skill initialization and one from scratch. The newer native motor and vision candidates each lost terminal successes on fresh tests. Returning to the camera look pose before closure raised first stable carries from 21 to 28 on 32 paired simulated starts. The current physical series has no observer-scored result. Source changes, confidence limits and the inputs needed from the operator are linked below. [Paired evidence and research audit](docs/RESEARCH_AUDIT.md) · [Generated table](README.md#measured-results) · [Field setup](http://192.168.0.168:8030/field-session)

## Historical status at 16 November 2026


The work is done on Homebrain. The current work code and the completed results are combined with Main; the interface:8030 is updated to 01b3ada. Further minor changes are published from the codex /complete-research-20261116. Previous timeline is available in Git. Specific actions are: [TODO_NEXT.md](docs/TODO_NEXT.md).

## Confirmed

| Result| Evidence and limit|
|---|---|
| K0-K4 complete, 50 runs| 3 /10, 2 /10, 9 /10, 10 /10, 8 /10; [summary](docs/results/knowledge_gap_sim/20261116-v2/summary.json). 2D perception and capture model, not robots and untrained motor policy|
| K4 with Qwen| One time out, one failure, no technical errors/swimming of the counselor. The advantages of K3 rules are not shown on these ten rooms.|
| MuJoCo K, geometry v2| 60 pair scenes x 3 conditions: complete information 44 /60, without size 34 /60, size of assistant 35 /60. [](docs/results/knowledge_transfer_mujoco_v2/summary.json) results. 80% not achieved for all six forms|
| Summarized learning data K v3| Size changes within class ± 20%; one physical rollout gives two records with the same personnel/acts and different text. First actual pair seed 50000: 217 frames, both readback PASS; [article](docs/results/knowledge_paired_v3_preflight_20261116.json)|
| Prototype of transport SO-101 ♪ ROSMASTER| The object-related phases, the IK/ROSMASTER, the independent MuJoCo-checker, are still simulational. Development phase 42000 has passed; the new 4.0 is rejected by surveillance. [All attempts](docs/results/skill_transfer_preflight_20261116/summary.json) are ongoing.]|
| Real SO-101 sources| Of the five old records, three successful complete tasks, zero suitable packages. [Audit]](docs/results/so101_donor_audit_20261116.json)No synchronous positions, metric sponges and confirmed geometry required |
| Real-trained transport| No actual SkillPacket, new T policy or physical adoption|

The complete K-outputs are published by the 7306ea5 and a36b991. The failures and time-out are maintained; the settings of these completed comparisons have not changed.

## What's been realized

- SkillPacket stores the source, hash, authorized use, metric positions/coppers, errors, and four phases with fixed supports. The package does not automatically become the recipient's skill.
- The current cognitive.registry only takes precise weights ROSMASTER, size/cams/calibration area and at least three independent success scenes without an online donor and geometric replacement. Actual registration further requires a real source and active deploy_gate.
- The existing FleetAgents, cognative_missions /requests, knowledge, Jobs and training_drafts are related: waiting for an example  \ \ choice of package \ \ \ data \ training \ \ check \ waiting for test \ acceptance. Second dispatcher/trainer not created.
- The re-engineering of the stage or the final zone does not create a re-training of the same skill. The target is stored at the mission. The end of the training and the restart do not start the movement.
- The new mission ends in a square of 40 x 40 cm on the floor; SO-101 remains a teacher. 2D checks the release and location of the entire object within the zone. The actual coordinates/outputs/observator are not yet allowed. A simple lift is not considered delivery.
- The geometry baseline is clearly chosen. The 2D room refuses to choose a trained policy; it does not replace it with its geometric capture.
- The manual SO-101 record can separate the top C920, measured joints, reference frames, time and the kinematic fixed tip. This is not yet calibrated contact TCP.
- The real package collector checks the original record, the frame, the reference geometry, the metric sponge curve, the camera delay, the phase and the continuous visible rise ≥ 5 cm/containment ≥1 s. Unknown errors are not replaced by zero.
- The minimum static beginnings of SO-101 joints are moved from so101ik 3456805b to Apache 2.0 with the /NOTICE. license the Old Backend is not called. The AmicGen-adapted adapter is self-realized; the NVlabs code is not copied.

## Verification and calculation

Target Python tests cover the origin, the limits of the phase, uncertainty, grouping of donor derivatives, readiness, turn/end, end zone and rejection of hidden baseline. Final Playwright scenarios check request/end, inappropriate package, actual artifacts, learning plan, waiting for clearance, reuse and manual writing. They operate in isolation and are not physical adoption.

The actual trainer and the subsidiaries are limited to the cgroup, STOP stops the group. The baseline of 6 GiB RAM + 2 GiB swap; the short SmolVLA batch 8 is complete: 50 updates, storage/reloading and validation have been completed. The measured cgroup peak has reached the limit of 6 GiB, swap peak 0.45 GiB, minimum available system memory 7.05 GiB; OOM /kill was not. This is a short run working limit, not a guarantee for all future sets. The optimization is maintained every 1,000 updates. The external SSD is used for weights and new large reference frames; LeRobot records remain in DATA /datasets. The absence of external mounting prohibits collection from --external-spin.

Small K Set: Six successful pairs, equal to 4 /1/1; [](docs/results/knowledge_paired_v3_memory_20261116.json) memory check. Full separate set: seeds 50006-50305, not more than 300 attempts to the first 200 successful pairs; technical six pairs and weights excluded. Status: DATA /runs/knowledge-policy-v3-20261116/full/state.json. Full K-learning: previously agreed 200 demonstrations per option, SmolVLA, 12000 updates, Batch 8, sed 1000. New T-learning requires a specific budget after the first real transfer.

## What else is needed

1. Three diagnostic hand-held SO-101 and independent measurements of the geometry of /TCP, sponges and camera delays; then the first real package \ \ own display of ROSMASTER in MuJoCo.
2. Complete separate steam collection K, both studies and independent evaluation. Memory check complete.
3. Prepare a precise small budget T1 /T2, account for all target/donor/verification data and time; then training/comparison by agreement.
4. Independent monitoring of the rise/retention of the real ROSMASTER, Shadow and limited testing with the owner. Failure of the servo unit does not prove success.
5. Measure the real end zone, check the tab and implement the clear continuation of the mission after the fresh stage, charge and resolution.

## Equipment and existing capacities

The motion commands were not sent in this run. ROSMASTER and Tank remain on charge; SO-101 need not be reset. The last test is the Leader /Follower, wrist chamber and C920 are connected and free.

The current common lidar plan, search, experiment, /STOP, shadow runtime, deploy_gate and magazines are still in place. The former piano bookmark v4 (180 runs, zero collisions) is a separate simulation, not adopting new policy.

An independent stopover of Tank at USB break remains a hardware restriction. The dangerous failure on a moving robot has not been repeated. Wristlab:8020, so101_autonomus_pick_place:8010, Console8090 and CubeBot have not changed or been called; the embroidery and motor calibrations have not changed.
