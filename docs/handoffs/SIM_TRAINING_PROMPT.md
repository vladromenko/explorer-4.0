# Explorer 4.0 is a learning system in MuJoCo, which is available to real robots.

Date: 14 November 2026.
GPU Orin (Repository) `~/Projects/explorer-4.0`, simulation - `.venv-sim`.
* After** `RECORDING_READINESS_PROMPT.md`. Real records
The display is used for identification and co-education as soon as
They'll be there before they use the records they've saved.

## 0. Objective

Get for each task (SO-101 pick-place, ROSMASTER pick-place,
ROSMASTER dock, Tank dock) **a politician trained in MuJoCo** who:
1. on **realistic scenarios** repeating the real user scene,
   Achieves the desired success on the deferred options;
2. Receives the same observations as on the robot at the entrance.
3. is exported and launched on its robot through a common performer
   Explorer (`EpisodeExecutor` ready for recording);
4. Works on all three robots at the same time as Homebrain, with restrictions.
   speed and defense on the robot side.

Readiness is determined by a measured success in sim **and** in shadow mode on
A beautiful scene and a successful script teacher is not
The result.

---

## 1. What is now (checked 14.11.2026)

- MuJoCo 4.0.1, `mujoco_warp` 4.0.1 and `warp` 1.18.0 (GPU-symulation on Orin),
  2.11 CUDA, SB3 2.9.2, gymnasium 1.4. JAX is not. `.venv-sim`
  No (mainly `.venv`, 0.6.1)
- Models (`docs/SIM_MODELS.md`):
  - SO-101: Menagerie `robotstudio_so101`, commit 370c439;
  - ROSMASTER: Yahboom M3Pro URDF/STL;
  - Tank: MentalPi T1 URDF /STL from the regular package.
  Reference geometry. **The transmissions are not identified:**
  - At the base, the force-to-eye model;
  - At the hand, the PD is delayed and the filter is not checked against iron.
  The SO-101 joints are not cross-checked with local calibration.
- `explorer4/sim/` code (about 3,300 lines):
  - Environment (`environment.py`, `mobile.py`, `rosmaster_arm.py`);
  - Teachers (`expert.py` );
  - Collection (`collect.py`), estimate (`evaluate.py`), PPO (`ppo.py`);
  - Options (`variation.py`), sysid (`sysid.py`, `rosmaster_sysid.py`);
  - fleet-world`fleet*.py`), branches (`branching.py`).
- Results:
  - Short ACT (50 steps) is only smoke;
  - PPO Pick-place 16,384 steps – **0 /20 success**: the budget for the order is small,
    A rich reward.
  - budgets in `configs/sim-budgets.json`.
- Known defects:
  - Sim pick-place marks the response as real `servo_position_readback`;
  - Tank in sim writes `previous_command_estimate_no_wheel_feedback`, although on
    The robot now has IMU and lidar;
  - scenes are a "laboratory" rather than a measured user scene;
  - `.venv` and `.venv-sim` do not share the policy code with the real rebound.
- ACT at Jetson: about 0.8 s per step (about 22 h per 100k steps).
  Free about 32 GB discs.

---

## 2. Main technical decisions (adopted, not revised without data)

1. **Two lines of policy to challenge:**
   - **Line S (main transfer): policy on the basis of characteristics.** Entry —
     The compact features that are listed on the robot are reliable and equal:
     - Procluculation;
     - The purpose or object of perception (mark or detector + depth);
     - Lidar sector;
     - IMU;
     - Previous action.
     Teacher: PPO with a privileged condition in the mass parallel
     simulations (in millions of dollars)`mujoco_warp`) Student: same network on "real" topics with
     The network is small (MLP 2×256).
     Inference is less than 1 ms, and for Pi 5 it is also good for Tank.
   - **Line V (comparison and reserve): Visual ACT.** Entry - RGB same
     Co-education on sim shows (S-line teacher, rendezvous)
     The proportion of the real is fixed.
2. **One observation and action contract for sim and real:**
   `explorer4/contracts/obs_v1.py`. Names, units, frequencies, normalization,
   Sim and real adapters are required to issue identical dictionaries.
   It's tested by a test.
3. **Scenes by user measurements.** Table size, cube size, boxes,
   Target tags, stop areas, camera positions -- file
   `configs/scene_measurements.yaml`, which is filled in by photo and roulette
   (the hat with fields and units makes agent) before filling - values by
   default with `assumed` label.
4. **Dynamics from real logs.** The parameters of the drive are selected by
   Recorded: command  ♪ measured response (hand-rails, IMU and
   The odometer and IMU ROSMASTER are only used if the error is
   The delayed trajectory is dropping by more than 10%.
5. **Randomization — within the measured limits:** ranges around
   values identified (P5-P95, extended by 20-50%) rather than
   Arbitrary.
6. **Unplug in one rebound:** `explorer4/policy_runtime/`
   (ONX Runtime CPU /CUDA, TensorRT as Homebrain option)
   reads the model in sim evaluation, in shadow mode and on a robot.

---

## 3. Limitations

- Training: short test launches (up to 15 minutes per launch) for debugging
  * Full start of training** (budget table, M9)
  Start after one obvious user.
  Step question: Ask it when M0-M8 is ready.
- The real robots are not going to be in action.
  (Policy predicts that teams are not going to go) The real launch of the politician is
  UI user.
- Old systems:8020 and:8090 do not touch. UI:8030 do not restart when
  Checks are in isolated UI 8035-8039.
- External models and essays are only with a clear license.
  manifestos and heshes, no weights and no video.
- Git: Your complete changes, little commies, cannon with the same team as
  In the rest of the promptes.
- GPU general: learning is in the current order of tasks (`jobs.py`,
  `compute.lock`) and does not interfere with the recording of the show.

---

## 4. Work packages

Order: M0  ♪ M1 ♪ M2 ♪ M3 ♪ M4 ♪ M5 ♪ M6 ♪ M7 ♪ M8 ♪ (start question)
→ M9 → M10 → M11 → M12.

### M0. Base and benchmarking
1. The run-through of all sim tests (`MUJOCO_GL=egl`, `.venv-sim`) is a point of countdown.
2. `scripts/sim_benchmark.py`: Simulation steps per second for each of the four
   Wednesday:
   - CPU MuJoCo, 1 and 4 processes;
   - `mujoco_warp` with 64, 256, 1,024 worlds (without a render and 128×128 rendezvous)
     If supported.
   Plus GPU and RAM memory.
3. The result is a choice of a target and real budgets in the clock.
   Write it down in `docs/COMPUTE_BUDGET.md`.
   **Acceptance:** measurement table; selection is justified by numbers.

### M1. Observation and Action Contract
1. `explorer4/contracts/obs_v1.py` for each task:
   - SO-101 / ROSMASTER:
     - 5 joints + capture (rad, 0-1), joint speed;
     - Cube position in base (m) system, appearance of cube;
     - The box position (stage constant or perception);
     - Previous action;
     - Time phase.
     Action - joints delta, limited, 30 Hz
     (SO-101) / ROSMASTER arm frequency.
   - Tank / ROSMASTER database:
     - Target vector (distance, angle) of the mark, visibility;
     - 36 sectors of lidar (m, cut 0.05 - 4 m);
     - IMU (angular speed Z, acceleration X /Y );
     - Previous action.
     Act (v, ) in shares of the profile limit, 20 Hz.
2. The contract version and the hash are in every artifact of the model.
   Unloading.
3. Real adapters (based on robots adapters ready to record) and
   Sim-adapters give the same keys, shapes and units.
   The structure is on the recorded real episode and on the sim episode.
4. Correct the response marks in sim (defects from section 1).

### M2. Perception common to sim and real
1. **Bases:** Target mark AprilTag or ArUco (OpenCV `aruco`).
   - Real: Tank / ROSMASTER camera, known internics.
   - In sim: same word tag on target models, same detector on
     Figure 1 - Figure 1 - Figure 1 - Figure 1 - Figure 1 - Figure 1 - Figure 1 - Figure 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table of Table 2 - Table 2 - Table 2 - Table of Table of Table of Table of Table 2 - Table of Table 2 - Table 2 - Table 2 - Table of Table of Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Table 2 - Summary Table of Table of Table of Table of Table of Table of Table 2 - Summary of Table of Table of Table of Table of Table of Table of Table of Table of Table of
     The number of students in the country is the same as the number of students in the country.
   - Noise and sim passes are being picked up by real detectives.
2. - Hands:** for a cube.
   - The main option is the upper camera + color segmentator and famous
     Table plane (rapid, reliable on Jetson).
   - The reserve is YOLOE /SAM from `/sim/vision` for verification.
   - The position error is measured on the actual frames with 20 frames per frame
     In sim, the noise is the same size.
3. Sim lidar: `mj_ray` / `mj_multiRay` with real number of beams,
   range and noise; pass on dark and shining surfaces, by
   I'm not sure what you're doing.
4. **Reception:** on real records, the detector gives no more than a misstep position
   2 cm / 5° for tags and not more than 1.5 cm for cube, 90% for frames.
   - change the approach, not move on.

### M3. Realistic scenarios
1. `configs/scene_measurements.yaml` (sablelet + filling instruction in
   `docs/SCENE_MEASUREMENT.md`, 15 minutes with roll:
   - Table, cube, box, material;
   - The mark and target area;
   - The position and inclination of the cameras;
   - Sex (friction coating type);
   - lighting (window or lamps).
2. `explorer4/sim/scenarios/` is a YAML script, with the following:
   - The distribution of start-ups corresponding to 10 fee locations, and
     separate **frozen assessment set** (same coordinates as for
     (b) The following information is available:
   - Fuse: shift of cube during approach, partial closure,
     Slipping during capture, uneven floor / threshold 5 mm for bases,
     barrier, blunder, delay in communication, short-term loss
     Marks;
   - Recovery scenarios: Cube fell near the box; base
     The base was blocked;
   - Dump scenarios: return the cube to the starting zone; leave for
     Start position.
3. Performance criteria in sim ** same as actual success detectors
   (cube in box and seizure opened; base centre in zone, speed around
   One function is two applications of the entrance.
4. YAML scene generation on top of existing robot models; rooms for
   "fleet-world" is one of the same dimensions.

### M4. Identification of the dynamics by real lobes
The source is the already preserved display:
- SO-101 — 3;
- ROSMASTER combines an arm and a mobile base;
- Tank is one successful + interrupted.
Plus new records after they're ready to go.
- on the time marks.

1. **Hands (SO-101, ROSMASTER): ** for each kp joint, damping,
   friction, command delay, speed limit, play.
   The servo is checked by the entry "command, measured position".
   The zeros and joint directions are checked against the SO-101 calibration files
   (read only).
2. **Tank:** "command (v, ~) actual traffic" model:
   - Net delay;
   - First order for each caterpillar;
   - Dead zone;
   - Saturation;
   - Slip ratio at turning;
   - The pressure of the battery.
   Measurement - IMU (
   User, `scene_measurements.yaml` field. Use limit
   The break-up and limits of agent Tank.
3. **ROSMASTER-base:** same for mecanum (vx, vy, ) odometer and IMU.
4. Method: `scipy.optimize.least_squares` multiple short
   Restarted reset every 1–2 s (multiple scoting).
   20 percent of the trajectory for verification is delayed.
5. `docs/SIM_REAL_GAP_RU.md` report:
   - error before and after;
   - The remaining gap;
   - What it affects;
   - Randomization ranges.
   Apply parameters only if there is an error in the delayed trajectory
   The number of people who have been killed has decreased by more than 10%.

### M5. Education
1. One gymnasium-compatible class with `cpu` and `warp` backups,
   The following are the parameters selected in M0.
   M1 surveillance.
2. Awards (sealed, limited, documented in code and in
   `docs/SIM_REWARDS_RU.md`):
   - Pick-place: approaching capture with the cube ♪ contact with both sponges ♪
     3 cm lift to box  ♪ opening over box ♪ transfer; plus
     Fees for collision with a box and a table, pushes, exit from work
     Zones, time;
   - Dock: distance loss and angle error
     Plus a fine for being close to the lidar obstacles, a sharp change.
     Action, reverse without cause;
   - Final bonus only for M3.3.
3. Curriculum: from simple start to full distribution by
   moving success over 70%; M3.2 interferences are connected when success
   On clean terms, more than 80%.
4. Randomization: dynamics within M4, noise and delay in M2 perception
   chamber position ± 1 cm / ± 2°, illumination and texture (line V only).
5. Tests:
   - Determinism on seed;
   - Release;
   - Limits of action;
   - CPU and Warp Beckand match on short rebound (position tolerance);
   - The reward doesn't give you a bonus without a success criterion.

### M6. Teachers and pupils (S line)
1. Teacher: PPO with privileged condition. Implementation with Torch
   over Warp World (buffers on GPU, without copies via CPU) or
   `stable_baselines3` with vector environment, if it's faster on M0.
   The observational standards are maintained with the weights.
2. Student: Dagger.
   - The student walks by his actions on "real" signs with noise and
     Delay; teacher notes.
   - 5 - 10 rounds, mixture β 1 to 0.
3. Script teachers (`expert.py`) for start-up: BC-initiation
   PPO teachers and display generation for line V.
4. Artifact: ONNX student, norm, contract M1, hash scenes, parameters
   The number of times, metrics, is recorded in `policy_catalog.py`.

### M7. Visual Line V (ACT, Co-education)
1. Sim display by S line teacher (with render rendezvous) in format
   LeRobot, marked `sim` and the same contract of action as the real ones
   Show.
2. Co-education recipe: percentage of actual performances in the Batch is fixed
   ( default 50%); real wallidation is only real episodes.
3. Move ACT training to common code with basic `.venv` (LeRobot 0.6.1),
   I want the rendezvous and the training.

### M8. Assessment, transport and shadow mode
1. `scripts/sim_eval.py`: frozen M3.2 assessment set, 100 episodes per
   The problem.
   - Metrics: success, Wilson CI, time, impact, violations
     limits, flaccidity.
   - Separately on "displaced" dynamics (outside the redomination) —
     Sustainability.
2. **Shadow mode on real records:** lose every real show.
   - The politician gets real shots of the frame and acts,
     The team isn't leaving.
   - Metrries: Discrepancies with human action in key phases, percentage
     Staff members outside the distribution of topics, delay in participation on target
     - A car.
3. The tolerance threshold for a real start (to write before learning):
   - success in sim is at least 80% on the score set and at least 60% on
     The dynamic shift;
   - In shadow mode, no action outside the limits;
   - Delay less than half the driving period.
   There's no policy on a robot to the threshold.

### M9. Full start-up (after start-up)
Budgets are from M0 (hours, no steps), task sequence, one task at a time
Or parallel if you get a GPU.

| Objective| PPO Teacher| DeAgger Student| ACT Line V|
|---|---|---|---|
| Tank dock | before convergence or 4 h| 1 h| 8 h|
| ROSMASTER dock | before convergence or 4 h| 1 h| 8 h|
| SO-101 pick-place | before convergence or 12 h| 2 h| 8 p.m.|
| ROSMASTER pick-place | before convergence or 12 h| 2 h| 8 p.m.|

Ratings to M0. Three seeds for S line. Report for each task: curves,
The negative result is recorded as it is.

### M10. Flipping on robots
1. `explorer4/policy_runtime/`: loading of artifact, contract verification and hash,
   a cycle at the task frequency, a sequence of actions, a phase change drop.
   - Inference on Homebrain for all three robots.
     on Pi 5 (MLP via ONNX Runtime CPU): then the Wi-Fi loss protection
     Harder.
   - Communications are the existing agents.
2. `EpisodeExecutor` as source `policy`. Restrictions
   The speed and protection work on the robot, regardless of politics.
3. User modes:
   - "Shad" (suggestion without command) ♪ "operator close" (policy is coming,
     STOP under hand);
   - unattended mode — only after the appropriate tolerance
     security.

### M11. Parallel launch of the park
1. One page, Park Policy: For each robot, choose an artifact,
   Mode, set of startups; buttons "start everything", "stop everything."
2. Inference planner on GPU Homebrain: three cycles (Tank 20 Hz,
   ROSMASTER, SO-101 30 Hz), time priority, delay monitoring.
   Shortcomings are a reduction in frequency with warning, not a STOP pass.
3. Fake robot loading test: three politicians at the same time 30 minutes,
   p99 delay less than half of the period, no loss of command.
4. A common magazine of episodes with metrics, like the show footage.

### M12. Documents
- `docs/SIM_TRAINING.md`: How to start a training, evaluation,
  Shadow, unwrap.
- Update `docs/SIM_MODELS.md` (identified parameters),
  `docs/SIM_REAL_GAP_RU.md`, `README.md`, `CURRENT_STATUS.md`.
- Tasks matrix: sim-prom, shadow, real launch (when
  (c) The Committee will be informed of the progress made in the implementation of the Convention.

---

## 5. Ready when

- M0-M8, M10-M12 is combed and profuse; all tests are green (main, sim,
  browser).
- The M1 contract is the same in sim and real.
- The scenes are built on `scene_measurements.yaml`. The dynamics are identified.
  On real logs with a break-up report.
- For each of the four tasks, there is a trainer teacher ♪ apprentice ♪ ONNX ♪
  ♪ Shadow assessment tested by short launch.
- After "start" (M9): trained artifacts and honest results table.
  The tasks that have passed the M8.3 threshold are available on the Park Policy page for the
  The launch is on robots, including all three parallels.
- The agent never sent the movement team to a real robot.
