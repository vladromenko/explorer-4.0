# TuJoCo training with robotic transfer (simlab)

Code: `explorer4/simlab/`. Prompto Step: `docs/handoffs/SIM_TRAINING_PROMPT.md`.
The status at 14.11.2026 is below, under the "Status".

## How it works

| Part| File| What does|
|---|---|---|
| Observation contract| `simlab/contract.py` | Same vector of signs in simulation, shadow mode and on robot. Bases: target by tag (distance, peleng, angle, visibility, age), 36 sectors of lidar, gyroscope z and acceleration x /y, previous action.|
| Scene and scripts| `configs/scene_measurements.yaml`, `configs/scenarios/dock_v1.yaml`, `simlab/scenario.py` | Dimensions of your measurements (`docs/SCENE_MEASUREMENT.md`), start distribution, obstacles, interference, frozen evaluation set|
| Training of bases| `simlab/dock_gpu.py` | Thousands of media on GPU. Drive: delay, dead zone, inertia, slipping. A robot agent layer: constraints, smooth acceleration, stop by lidar (like the real Tank and ROSMASTER).|
| Bases check| `simlab/dock_mujoco.py`, `scripts/simlab_eval.py` | Full MuJoCo: model manufacturer chassis, contact, lidar `mj_multiRay`. Decision on admission - only for it|
| Hand-to-hand training| `simlab/arm_warp.py` | SO-101 and ROSMASTER's hand on MuJoCo Warp (GPU), Cube and Box Contacts, CUDA graft control|
| Arm teacher| `simlab/arm_demos.py` | Screen teacher `sim/expert.py` in contract format, cloning and launch PPO|
| PPO | `simlab/ppo.py` | Asymmetrical: The instrument only sees signs of robotics, the critic is the exact state of simulation.|
| Identification| `simlab/sysid_base.py`, `scripts/simlab_sysid.py` | Delay, inertia, reinforcement, dead zone on the "+ depth and lidar" records. Accepted only if the error falls by more than 10% on the delayed part; then the learning environment takes the range found.|
| Perception| `simlab/perception.py` | ArUco-mark of purpose    \ contract characteristics (uncertain position removed; label not less than 15 cm). Cube by color and plane of table|
| Policy| `simlab/artifact.py` | `policy.npz` + `policy.json`: Weights, rationing, contract, hash scenes. Performance only numpy (works in any environment and Pi at Tank)|
| Shadow Mode| `scripts/simlab_shadow.py` | The policy takes a real shot of the frame; the commands are not sent; the report is a match to the operator, exit for distribution, delay|
| Launch on robots| `simlab/runtime.py` | A robot cycle, all in parallel; shadow mode and operator side by side; any error or delay.... stop of robot|

## Commands
```bash
# Smoke run (up to 15 minutes). Start full training separately.
PYTHONPATH=. .venv-sim/bin/python scripts/simlab_train.py tank --minutes 10
PYTHONPATH=. .venv-sim/bin/python scripts/simlab_train.py so101 --minutes 12 --demos 200
# Evaluate the frozen starts in MuJoCo.
MUJOCO_GL=egl PYTHONPATH=. .venv-sim/bin/python scripts/simlab_eval.py ~/.local/share/explorer3/simlab/policies/<policy-name>
# Identify the drive model from real lidar recordings.
PYTHONPATH=. .venv-sim/bin/python scripts/simlab_sysid.py tank <recording-directory> ...
# Run shadow inference on a physical recording.
PYTHONPATH=. .venv/bin/python scripts/simlab_shadow.py <policy> <recording-directory>
```

## The threshold for acceptance of policy to a robot
- Success in a full MuJoCo is at least 80% on a frozen set and 60% on a
  A dynamic that is more altered than learning.
- In shadow mode, there are no actions outside the box on the real records.
- Delay less than half the driving time.

## Status (14.11.2026)
- Calculation budget: `docs/COMPUTE_BUDGET.md`.
- **Bases.** All the conveyor is assembled and checked.
  - Tank is a 73% success rate in the 0.5 program; in the full MuJoCo 74%
    (95 % MDIs 60 - 84 %) under the same conditions;
  - ROSMASTER is a 74% program.
  Until the full program and the 80 percent threshold, we need full start-up.
- **Hands.**
  - SO-101: `so101_bc_v1` policy (Cloping IK teacher through the same
    Speed limiter, with DART noise) - **96% (48 /50)** in MuJoCo
    frozen start-ups with numpy performer, 91% (232 /256) in GPU medium
    It's the start of the training program.
    (cube ± 2 cm).
  - Found and corrected traps:
    - The teacher changes the phases over time, and time is added to the signs;
    - The rotations are making an error, the action has become an absolute goal;
    - The clone copied the past action (copycat) from the signs;
    - The trajectory of the show was not consistent with the clone limiter — the display
      It's being executed through the same limiter.
  - PPO is not learning from zero per test run.
    The clone is on a very high start.
- **Not done:**
  - Identification by real lobes - need "+ depth and lidar" entries;
  - Measurement of the scene (`status: assumed`);
  - Park Policy page in UI;
  - Shows and cloning for ROSMASTER (media and contract ready);
  - ACT visual line (M7).
