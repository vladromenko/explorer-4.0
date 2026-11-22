> **Next step, after the dateset is recorded.** RECORDING_READINESS_PROMPT.md (R0-R9) is now operational. The starting point for future autonomy is retained below; the old descriptions of the permanent lockdown of Tank do not reflect the current tolerance. The training and autonomous physical runs have not been started here.

# Explorer 4.0 is a software upgrade to the Autonomous System (phase 1)

Date: 14 November 2026. perpetrator: Agent on Homebrain (Jetson Orin NX),
`~/Projects/explorer-4.0` repository, UI:8030, catalogue
`~/.local/share/explorer3`.

This document is the only task of the programme phase.**
programme part `NEXT_DEVELOPMENT_PROMPT.md` (v3). Retained from v3
Restrictions, statistical rules and formulas where reference is made.
Simulation (realistic simulation, script, sim-to-real)
A separate stage, not done here.** Only general ones are laid down here.
The interfaces she'll connect later.

Phase result: all software problems are closed, test green.
receives one physical inspection bag (section F) and passes through it.
Only then does the data start.

---

## A. Research framework: from "when to call" to full autonomy

### A.1. Question of article
Past framework: assess the benefits of human assistance and move this estimate between
The human being in it is a constant part of the contour.

> ** How to bring a mixed robot fleet (SO-101, goose Tank,
> ROSMASTER mobile manipulator) to work without a person and to what extent
> The transfer of knowledge between robots and from simulations reduces human labor,
> The one that's needed for it.

The only person left is three roles:
1. The author of the original shows;
2. Source of true tags for automatic detectors (on
   (b) The sample is not subject to any pressure (i.e., a delayed sample);
3. Emergency stop.

Total assessment - **zero human interventions** on a fixed set
Start-up conditions.

### A.2. Self-sustainment components (each — measurable module)
1. **Success detector** on the task: is the task finished, without a person?
2. **Malfunction Monitor**: predicts a breakdown before it (risks,
   AutoIntervene-adapted already exists.
3. **Rehabilitation without a person**: repetition from the original position, policy
   Recovery, software reserve (obsolete capture; Nav2 base).
4. **Autonomous stage drop**: robots return the task to launch
   Without this, there is no self-assessment or autonomous practice.
5. **Autonomy practice**: runs ♪ tested success ♪ further education ♪
   This is the training itself here.
   Training line.
6. **Safety envelope** for unattended work.

### A.3. Hypotheses (detailed and recorded in pre-registration, S12)
- **A1 (re-establishment).** Under the same starting conditions, "policy +
  Monitor + recovery" gives more per cent of autonomous success than one
  A comparison of the couple, by starting conditions.
- **A2 (practice).** Autonomous practice framework where success selects the detector,
  The increase in autonomous success without new human displays.
  success and a second for a round.
- **A3 (transfer).** Monitor, success detector and recovery from
  ♪ The robot source (SO-101 ♪ ROSMASTER; Tank ♪ ROSMASTER base) and sim,
  Reduces human seconds to the target level of autonomy at
  A comparison with learning only on a target robot.
  Negative control is the transfer from the outside robot.
- Causal v3 (randomization, DR evaluation, CATE)
  He now chooses ** automatic
  The option of "call man" is:
  It's just like a expensive standard.

### A.4. Metericks (all reports are the same)
- `autonomous_success_rate`: percentage of attempts successfully completed without a person
  (the success is confirmed by the person on the postponed part, not just the detector).
- `MTBI`: Average time between human interventions; `interventions_per_hour`.
- `human_seconds_per_success`: Shows + corrections + markings + hand-held discharges.
- `autonomous_reset_rate`: Percentage of successful automatic discharges.
- Success detector: accuracy, completeness, **supplicate success rate** (critical: false)
  The threshold for use is not more than 5%
  false success at the postponed markings.
- Safety: number of shell operation, number of emergency stops
  By man (should be) the whole of the world.

### Positioning (check each reference before article text)
- Close work:
  - Sirius (Liu et al., 2022) and Fleet-Dagher (Hoque et al., 2022) —
    Reduction of human participation;
  - ThriftyDAgger (Hoque et al., 2021);
  - SOAR (Zhou et al., 2024) is an autonomous improvement with a success detector
    Basic model;
  - RoboCat (Bousmalis et al., 2023) is a self-improvement;
  - reset-free RL (Gupta et al., 2021; Sharma et al., MEDAL);
  - VLM as a success detector (Du et al., 2023)
  - RESCUE, FARM, AutoIntervene is an audit.
- A new thing that can be really protected: **a homogeneous park**, carry-over
  The components of autonomy between different bodies and sim, fair price in
  "Absolute autonomy" is not claimed if it is not:
  The measured level shall be published.

### A.6. Honest expectations
ACT politicians at 50 Jetson shows aren't likely to give a high percentage immediately.
The article therefore holds on **increase** autonomy and**decrease**
Any component that has not been tested
(e.g. polygrid detector more than 5%) is supplied as negative
The result, not hiding.

---

## B. Rigid restrictions (no package removed)

- **Old systems.** SO-101 /WristLab:8020, Console:8090, their code, services,
  The data do not change or stop.
  Transfer SO-101 from:8020 to Explorer is done by the user, not the agent.
- **Learning.** Do not start political education (real and sim), PPO, fine-tune,
  Optimization of hyperparameters, Qwen generation without explicit authorization
  Allowed:
  - Test on fixings;
  - Inference saved by heckpoints without robot commands;
  - Fit of small valuers (logistics, crest regression) in tests.
- **Simulation.** General interfaces only (S8.4, S5.5). New models, scenes,
  Sysid is the next stage.
- **Iron.** Agent doesn't send traffic commands and doesn't open motors.
  Ports: SCH reading (files, tops, magazines) is permitted.
  Tank (`incident-block.json`, `stage-c-authorization-suspended-incident.json`)
  The agent does not remove: the user command removes them after F.2 verification.
  No change in the embroidery.
- **UI:8030.** Do not restart when actively driving, recording or
  Checks in isolated UI 8035-8039 with temporary
  `EXPLORER3_DATA`I mean, only my own processes, without a broad range of `pkill`.
- **Git.** Only your complete changes with the checked diff, without
  Force-push.
  `GH=~/.local/share/explorer3/tools/gh_2.103.3_linux_arm64/bin/gh; GIT_TERMINAL_PROMPT=0 git -c credential.helper= -c credential.helper="!$GH auth git-credential" push -q origin main`.
- **Data and secrets.** No to communicate currents, calibration, weights, videos, vendor.
  Accets with an unclear license (Hiwonder's manual is just a reference and a heshes,
  The data are not sent outside Homebrain.
- **Stats.** IMPLEMENTED ♪ SOFTWARE_VERIFIDE ♪ HARDWARE_VERIFIDE.
  The fairy is SOFTWARE_VERIFIDE. Do not write "ready", "self-contained", "proven"
  No status or data.

---

## C. Modalities and evaluations

| # | Package| Locks data entry| Evaluation|
|---|---|---|---|
| S0 | Single test run| Yes (counting point)| 1 h|
| S1 | The Common Performer of the episode and robot adapters| Yes| 2 days|
| S2 | Tank: Hiwonder program customization| Yes| 2-3 days|
| S3 | ROSMASTER: Programme tails| Yes| 0.5 days|
| S4 | SO-101: devices and Leader| Yes| 0.5 days|
| S5 | Success Detectors| Yes (marks required from first entry)| 2 days|
| S6 | Autonomous Scene Drop| No, but I need it before practice.| 2 days|
| S7 | Security cover without supervision| Yes for autonomous runs| 1.5 days|
| S8 | Autonomous racer and start-up kits| None| 2 days|
| S9 | Library of Recovery and Choice of the Mode| None| 2 days|
| S10 | Malfunction monitor| None| 1 day|
| S11 | Autonomous practice container (without start-up)| None| 1 day|
| S12 | Pre-registration, power, analysis| None| 2 days|
| S13 | UI and physical inspection package| Yes| 1.5 days|
| S14 | Documents, status, article skeleton| None| 1 day|

Order: S0   ♪ S1 ♪ (S2, S3, S4 in parallel) ♪ S5 ♪ S7 ♪ S13 ♪ (packing)
Physical verification can be given to the user here) ♪ S6 ♪ S8 ♪ S9 ♪
S10 ♪ S11 ♪ S12 ♪ S14 ♪ Small commies inside the package ♪ After each package
Report (section H).

---

## D. Packages

### S0. Single test run
**Why.** Tests are available in 56 files. Simulation tests require `.venv-sim` and
`MUJOCO_GL=egl`, the other `.venv`, was the first to cover 15 files.

**Do it.**
1. `scripts/run_all_tests.sh`: break `tests/` into groups
   - main (`.venv`, `PYTHONPATH=.`);
   - sim (`.venv-sim`, `MUJOCO_GL=egl`);
   - Browser (Playwright, isolated port).
   Group defined by `pytest.mark.sim` / `browser` in
   `conftest.py`, not the list of names.
2. Outcome: number of files in each group, passed /failed/errors, time.
   The file is in exactly the same group.

**Reception.** 0 failed, 0 errors; time not exceeding 10 minutes; result
saved in `validation/tests-<дата>.json`.
**Comm:** `Run every test file in its proper environment`.

### S1. The stage master and robot adapters
**Why.** Now the random assignment of aid (`tank_pilot.py`) is working.
For Tank only:
- `accepted_study` rejects everything except `tank_dock`;
- `tick` takes the magnitude of the Tank signs for any robot;
- `observe` sets `state_valid=False`;
- `session.py`, while retaining, provides `[0,0]`, is used from the chassis keyboard;
- The test does not read the Leader (`HardwareSource(teleoperate=not bool(provider))`).

Self-sustainment requires **one performer** with command sources:
`policy`, `recovery`, `reset`, `safety`, `human`.

**Do it.**
1. `explorer4/executor.py`: `EpisodeExecutor(profile, adapter, plan)`.
   - Phases: `reset`    ♪ `policy` ♪ (`monitor` worked ♪ `recovery` ♪
     ♪ `policy` ♪ ♪ `verify` ♪ `done` ♪ In any phase ♪ ♪ `safety` and `human` ♪
   - Each step writes `command_source`, `phase`, `phase_reason`.
   - The LeRobot segments are shared by source.
   - Change of phase   ♪ `provider.reset()` (clean chunk ACT); new chunk
     is built from current observation.
   - `tank_pilot.py` and `TankPilot` remain thin wrapping (import not to break).
2. `explorer4/adapters/` – contract `RobotAdapter`:
   - `hold_action(obs)`; `human_action(obs)`;
   - `measured_response(obs) -> (kind, values, valid)`;
   - `workspace_ok(obs)`; `reset_actions(...)` (S6); `success_signals(obs)` (S5).
   Implementation: `So101Adapter`, `RosmasterArmAdapter`, `RosmasterBaseAdapter`
   `TankAdapter`.
   - SO-101 / ROSMASTER arm, retention is the last measured position,
     Human - Leader by convergence with 2° /3
     (`hardware.py:489`) The beginning of the human correction is the Leader shift.
     is greater than 2°, not `abs(action) > 1e-6`.
   - Tank / ROSMASTER-Base. `[0, 0]`I. Measured response — from S2.3
     (Tank) and the existing odometer /IMU (ROSMASTER); `kind` is clearly recorded.
3. `accepted_study` accepts all six profiles (including `*_rgbd_lidar` ) and
   Checks for profile, hech and time-setting.
4. `trial_start` in `static/rosmaster-console.html` and generally UI transmits
   `collection` (now not transmitting and all day tests are merged into one group).

**Texts** (`tests/test_executor.py`, fairy sources):
- The sequence of phases and `command_source` on each frame;
- Hand retention equals the measured position;
- The Leader team comes with a convergence, no more than a limit;
- In Tank, with fresh IMU and `state_valid=True` lidar, the old ones False;
- Old `test_tank_pilot.py` passes except waiting `state_valid=False`
  (replace);
- `collection` reaches the catalog from both UI.

**Comm:** `Generic episode executor with policy/recovery/reset/safety/human sources`.

### S2. Tank: Hiwonder instruction software customization
Source: Local copy of official instruction MentorPi T1
`~/.local/share/explorer3/cache/references/mentorpi-t1-complete/` (chapters
1, 3, 4, 6, 7, 8) References and hashs - `docs/tank-reference-manifest.json`.

Facts as at 14.11:
- RRC Lite (`/dev/ttyACM0`, 1 Mbod) on SDK gives off voltage,
  Knobs, IMU, gamepad, SBUS and servo drive.
  The Explorer does not have a wheel feedback;
- `/odom_raw` in the regular `odom_publisher_node.py` (Chapter 3.4, parameter
  `linear_correction_factor_tank: 0.52` ) should be checked by reading: if it
  Integrating commands is not a measurement;
- `motion_permission.limited_command` allows a non-zero command **only** in
  Backup mode (`bench-authorized.json`, 15 min maximum, 0.2 m/s and
  (i) No regular driving on the floor of the program at all,** even after
  Freezing;
- Pi monitoring load: load overage about 5.3 - 5.6;
- instruction (chapter 3.4): Closing the Ctrl+C program may not stop
  chassis, zero command required. Recommended limits:
  ♪ ♪ 2 rad/s
- instruction (Chapter 1.3): charge below 6.4 V, disabled, regular
  The plate shall use a threshold of 6.9 V (`send_machine_type`) at 2 A. Plata.

**Do it.**
1. **Traffic modes.** Add `motion_permission.py` levels `bench` and
   `floor`. Resolution `floor-authorized.json`:
   - Tied to boot-id;
   - Created only by the user command `scripts/tank_unlock.py` after
     F.2: the script itself checks the test report and
     Requires the entry of confirmation at the terminal;
   - Duration up to 8 p.m.
   - Section limits: for display of 0.2 m/s and 0.5 rad/s, for self-contained
     separate limit not exceeding 0.3 m/s and 1.0 rad/s (less than
     The following table shows the number of cases reported by the manufacturer (i.e. recommended by the manufacturer).
   `incident-block.json` still covers everything.
   Same script, file archive and cause.
2. **The refusal of USB as a regular event.**
   - Core monitor on Pi (`udevadm monitor` or pyudev for `1a86:55d4`):
     When disabled immediately, STOP latch, event recording, UI notification
     with cause.
   - At EIO: One attempt to reopen the port and send zeros.
     The condition of `motor_link_lost` and the lock-down before the decision of the person is made is successful.
   - In each session log: number of U.S.B. shut-offs, minimum voltage
     Load, delay "last non-zero × zero".
3. **Measured response without encoders.**
   - By reading to check where `/odom_raw` comes from; write the result in
     `docs/TANK.md`.
   - Measurement source:
     - IMU (`/imu` through the regular `imu_filter.launch.py`, Chapter 3.3) is a burrow;
     - Lidar offset: scan comparison, `rf2o_laser_odometry` or
       `slam_toolbox` in localization mode (Chapter 6.4), if already available in
       Container; new software to be installed only after user approval;
     - EKF (`ekf.yaml` Chapter 3.3) — only when entering
       The dimension, not the command.
   - Admitting signs: `yaw_rate_imu`, `forward_displacement_lidar`
     `response_lag_s`; `kind='imu+lidar_scan_odometry'`; `valid` only
     if both flows are fresh 0.2 s.
   - Command assessment to leave a separate field with a clear name.
4. **Calibration under Chapter 3.2.** The agent does not start calibration: it requires
   Make:
   - Read-only `scripts/tank_calibration_report.py`: Read
     `imu_calib.yaml`, `calibrate_params.yaml`
     (`angular_correction_factor`, `linear_correction_factor_tank` ), hashs,
     Date of change;
   - step-by-step calibration chiplist for the user in bag F, with commands
     Chapter 3.2 (do_calib IMU; angular /linear calib launch).
5. **Purpose and regular services.** Check before session:
   - That the regular application is stopped (`~/.stop_ros.sh`, Chapter 3.4 Step 3);
   - That `/dev/ttyACM0` is only open by our driver (`serial_guard`).
   Gamepad and SBUS packages from the board should not be turned into a movement.
   Instruction (1.3.4) warns of interference between gamepads near the
   A few robots: While Explorer is working, gamepad teams
   Ignore and write it. The return of the regular application is the existing button.
6. **Load Pi.** `scripts/tank_load_report.py` Report: Processes, CPU,
   Temperature, `vcgencmd get_throttled`, camera and lidar frequency, delay
   Homebrain ♪ Pi ♪ toll (driver log)
   not the right Explorer, hold CPU, user list with
   I'm not sure if I'm a good person, but if I don't, I'll keep my services on.
7. **Local protection on Pi.** Works without Wi-Fi and Homebrain:
   - TTL 350 ms (there are);
   - Lidar stopping: minimum distance in front or rear
     The front of the road shall be adjusted in a profile, at least 0.15 m;
   - Stop at an IMU inclination greater than 20°;
   - Stop at voltage below 6.9 V (there is).
   The reason for each stop goes to UI.
8. **Hard-wall independent stop (preparation, no inclusion).**
   - Describe in `docs/TANK_ESTOP_RU.md` the diagram: relay or power key in a circuit
     Engine power, GPIO Pi security pulse and radio button.
   - Write an inactive `agents/tank/estop_gpio.py` module with a test on a fairy.
   - Without the user, you can't plug anything in.
   For operation **without supervision** (A.2.6) Tank is only allowed with this
   Stopping; F.2 is sufficient to show with the operator.
9. **Backgrounds for self-sustainment from the manufacturer's kit** (integration only)
   Read and launch on request, without change in the regular packages):
   - Nav2 / AMCL / DWA (Chapter 7) is a program reserve for access and access to the United States.
     A self-contained base dump. The map is built by the user in F;
   - QR recognition (Chapter 8.4) - target mark for a success detector
     The Committee notes that the number of accesses is only one of the reasons for the lack of access to the United Nations system.
10. **Renew pilot** under S1 (`TankAdapter`) and remove Tank Speciality from common seats.

**Techs** (fake serial and ROS as in existing Tank tests):
- without `floor-authorized.json` non-zero command     ~ 0;
- Expired resolution or other BOOT-ID. 0;
- `incident-block.json` is overrun by `floor`;
- Simulate the U.S.B. \STOP latch, zero, event in the journal;
- EIO for the recording of \ \ one attempt, then `motor_link_lost`;
- A lear is closer to the threshold on the way, stopping, you can move back;
- IMU-clown stop;
- :: Including the gamepad;
- The following are the indications of a response in the case of fresh and obsolete flows.

**Reception.** All Tank tests are green. `tank_calibration_report.py` and
`tank_load_report.py` is run on the Tank only reading, reports
`docs/TANK.md` is an honest section "what is measured that is not".
**Commies:** by item, e.g.
`Tank floor permission bound to bench acceptance`,
`Treat motor USB loss as a latched stop event`,
`Measured Tank response from IMU and lidar`.

### S3. ROSMASTER: Programme tails
1. Restart:8030 on the current HEAD only when UI is not available.
   He's working for 730589 now.
2. The file is for physical verification of ROSMASTER (sensors, profiles)
   `*_rgbd_lidar` ) is a model that includes a user.
3. Source of measured base response: odometery and IMU ROSMASTER.
   It's obvious that this is the measurement of the wheel encoders (if so), with `kind`.
4. The access and base drop detector is like Tank (S5, S6), the common code.
5. The decision about the arm lift is to leave it as a question to the user in F.

**Comm:** `ROSMASTER adapters for the generic executor`.

### S4. SO-101: devices
1. Explorer at start of SO-101 session checks whether the flyer or camera is busy
   (`so101-external-owner.json` and actual port owners) If occupied -
   Understandable message "SO-101 occupied by the old system:8020, release it" and
   No attempt at capture.
2. "So 101 Transfer" with instruction for user (to stop
   Agent:8020 doesn't touch.
3. Leader in trials and in performance (S1) is always read, Leader's teams
   are only introduced in phase `human`.

**Comm:** `SO-101 ownership check and leader reading in trials`.

### S5. Success detectors
**For what reason.** Without automatic verification of the outcome, there is no self-assessment and practice.

**Do.** `explorer4/success/` with common interface
`SuccessDetector.predict(episode_tail) -> (p_success, evidence)`.
1. Hands (SO-101, ROSMASTER) Signal:
   - Cube inside box area on frame: fixed area in coordinates
     The enclosures shall be set once; the colour of the cube or
     Existing YOLOE /SAM from `/sim/vision`;
   - The seizure is discovered;
   - The arm is in its retracted pose.
   A simple logistics model above these features or a rule with thresholds,
   The data is not available for the data.
2. Bases (Tank, ROSMASTER)
   - Target mark (QR or ArUco; Chapter 8.4 Hiwonder for Tank): distance and
     angle;
   - Lidar: distance to target in front sector;
   - Speed is about zero.
   Success is the center of the marked zone.
3. Human label validation:
   - `scripts/success_detector_eval.py` for episodes where the outcome was noted
     Human beings: accuracy, completeness, percentage of false success, CI by group;
   - The threshold for use is not more than 5% false success (A.4);
   - The detector shall only be operated in shadow mode before passing the threshold.
     (writing, but not deciding).
4. Every show (now, before autonomy) has to write an exit
   So the first 50 demonstrations are for the task.
   They give you a validation.
5. Interface one for real and sim (sim will be connected in the next phase).

**Texts:** synthetic episodes with known outcome; shadow mode not
changes the outcome; the discrepancy with the person is reported.
**Comm:** `Task success detectors with human-label validation`.

### S6. Autonomous stage drop
1. Hands: Dumping program.
   - Take a cube from the perception box (S5).
   - Place in random position from the set of permitted starting items
     Setup; the set is asked by the user once, in the coordinates of the table.
   - Take your hand away.
   - Checking the discharge by the same detector (cube outside the box, starting area).
2. Bases: departure from target to random starting position from recruitment (distance,
   First, a closed cycle on IMU and a lidar with a speed limit.
   (S2.1), later on, Nav2 (S2.9).
3. A bad discharge: two attempts, then a pause and a request from a man.
   The number of individual accounts is `human_seconds` of the type `reset`.
4. All discharges go through the performer with `command_source='reset'` and
   Recorded (deposit data will also be useful).

**Texts:** Fake robot; start position selection is reproduced on seed;
Restrictions on the working area are observed.
**Comm:** `Scripted autonomous scene reset for arms and bases`.

### S7. Safety cover without supervision
1. Total `SafetyEnvelope` in performer:
   - Hands working area (couples and XYZ with reserve);
   - Base geozon (Lidar and map);
   - Time limit for the episode and session;
   - Limitation of successive failures (3) ∙ pause;
   - The freshness of each flow;
   - voltage;
   - - No communication.
2. "Unsupervised" mode only when the robot has all of the HARDWARE_VERIFIDE
   The security posts are closed for Tank, with a hardware stop (S2.8).
   Otherwise, "operator side" mode: same cycle but before each episode
   The "go on" button.
3. Notifications: Stop, pause, low charge   \ event in UI and (on)
   The user agreement) push.

**Texts:** every violation \ \stop with cause; unattended mode not
is activated without conditions.
**Comm:** `Safety envelope for unattended episodes`.

### S8. Autonomous racer and start-up kits
1. `explorer4/autonomy_runner.py`: episode sequence
   `reset → policy(+monitor/recovery) → verify → log`, budget (number)
   The episode, the time, the pause and the stop, the continuation after the break.
2. Start-up kits: to target 30 fixed start-up conditions for evaluation
   (seed, object position or base starting position) separate from conditions
   The evaluation kit is frozen by the hash until the first run.
3. Metrique A.4 in the catalogue; page "Autonomity" with versions curved.
4. `EnvironmentAdapter` interface common for real and sim: next stage
   It'll set up a realistic simulation without changing the racer.

**Comm:** `Autonomy runner with frozen evaluation start sets`.

### S9. Rehabilitation Library and choice of method
1. Remediation modes (each with `cost_s` and time limitation):
   - `retry_from_pre_pose`: Return to position before collapse and restart
     Clean chunk policy;
   - `recovery_policy`: ACT slot, which is trained in the correction segments;
     He does not learn, the slot is empty until permission is granted;
   - `scripted_fallback`: Hand-held seizure, Nav2 or closed
     Base access;
   - `human`: Reference and emergency mode only.
2. At the monitor response, the method is selected **accidentally** by
   Pre-registered probabilities (blocks 4 as in v3 P2), s
   This provides data to assess the usefulness of each
   The situational approach (CATE v3) and the rule of choice without a person.
3. If the monitor failed and the detector failed, the record
   "missed malfunction" for the monitor.

**Comm:** `Recovery library with randomized recovery choice`.

### S10. Malfunction monitor
1. General interface `FailureMonitor.risk(window) -> p_fail`. Implementation:
   - The threshold for `tracking_error` / response (as in v3, baseline);
   - AutoIntervene-adapted (already available);
   - Logistically based on `research.FEATURES`.
2. Calibration of the threshold is only on wallidation groups; on test, once.
3. Transport: uploading of robot source monitor parameters as starting point
   (source-prior of v3 B.4) with contract
   `FEATURE_CONTRACT_VERSION`.

**Comm:** `Failure monitors with calibrated thresholds and transfer prior`.

### S11. Autonomous practice container (without start-up)
1. Building the kit: Human Shows + Self-Reliances
   detector (after S5 threshold only) + correction segments
   (Secretly, for recovery politics) The version of the set, the heshes, the share of the sources.
2. A plan to provide further training through the existing "Prepare training · Do not start".
   Start only with user permission.
3. Drift protection: in the k round set no more than the specified percentage
   Self-contained data (e.g. 50%), the evaluation set is never part of the training.

**Comm:** `Prepare autonomous-practice datasets without launching training`.

### S12 Pre-registration, power, analysis
- From v3 P3 /P4 without changing the formulas:
  - `explorer4/research_power.py`;
  - `docs/PREREGISTRATION.md` with hash block;
  - Group frolds;
  - T/S/DR-learner;
  - DR-value evaluation of the rule.
- Changes:
  - The subject matter of the decision - the method of restoration (S9);
  - Primary metrics - A.4
  - The hypothesis is A1–A3;
  - `analyze_v1` Save.
- A1 pair capacity by 30 starting conditions x k
  The second and A3 curves are "human seconds ~ self-sufficiency levels".

**Comm:** `Preregistration and analysis for autonomy hypotheses`.

### S13. UI and physical inspection package
1. Autonomity page:
   - Mode (operator close/unattended);
   - The current phase and the source of the team;
   - The reason for the last stop;
   - A.4 counters;
   - One big STOP button.
2. Physical verification scripts (section F) to UI: step
   user   ♪ automatic verification of entry ♪ PASS /FAIL in
   `validation/physical/<робот>-<дата>.json`.
3. The Playwright browser scripts on the fae robots for each new one.
   Pages; `page_errors` are empty.

**Comm:** `Autonomy page and guided physical acceptance`.

### S14. Documents
1. `CURRENT_STATUS.md`, `README.md`, `docs/TANK.md`,
   `docs/DATASET_GUIDE.md` is by status. Remove obsolete 92 PASS.
   New article (A) frame.
2. `docs/paper/` is a skeleton: introduction, method (A.2), protocol, metrics,
   The risk of valitivity; the drawings are generated by a script from the catalogue.
3. Warehouse: free of 32 GB out of 233 - report and archive proposal,
   without removal.

---

## E. What to do for the next phase (simulation) but not to

- General `RobotAdapter`, `EnvironmentAdapter`, `SuccessDetector`,
  `FailureMonitor` for real and sim.
- The response signs with the same names and units in real and sim.
  Sim writes `previous_command_estimate_no_wheel_feedback` for Tank and
  `servo_position_readback` for a hand in pick_place is corrected in the next step.
- The starting sets of the assessment are described in the coordinates transferred to the sim.

---

## F. Physical inspection package for user (post S13)

Agent forms a chesslist in UI (S13) and a separate document
`docs/PHYSICAL_CHECK_AFTER_SOFTWARE_RU.md` over time, every step.

- **F.1 ROSMASTER.**
  - Management and STOP;
  - Sensors (`/rosmaster/sensors`)
  - 3 hand test and 3 bases;
  - The "shadow" success detectors coincide with your marks;
  - One automatic drop of arm and base in "operator side" mode.
- **F.2 Tank, on the stand.**
  - :: Charged, free of charge, caterpillars in air;
  - 5-10 mines;
  - not less than 10 STOP;
  - USB and voltage magazine;
  - PASS: 0 U.S.B. shut-downs and each stop is less than 0.4 s.
  Then `scripts/tank_unlock.py`.
- **F.3 Tank, on the floor.**
  - Calibration of Chapter 3.2 if it moves away;
  - Mapping (Chapter 6.4), if Nav2 is needed;
  - Stopping at the lidar before the barrier;
  - 3 test access points;
  - QR is visible and recognized.
- **F.4 SO-101.**
  - Free from:8020;
  - Leader, STOP;
  - 3 test demonstrations;
  - A test automatic discharge;
  - I want you to return:8020.
- **F.5 Scene Marking**
  - The same cube and box for both hands;
  - The same mark and area for both bases;
  - 10 display locations + separate start-up set of evaluation terms.

---

## G. User decisions (to ask one message without blocking S0 - S5)

1. To approve the frame A (autonomous rather than "when man is called").
2. Tunk hardware stop (S2.8): set or not. Without it, only mode
   "operator is near."
3. Do you want to put a new software on Tank for lidar odometer if it's in a container?
   It is not (S2.3).
4. Training permit: needs to be completed after the screening is recorded (this is as follows):
   Where to teach: Jetson or external GPU.
5. Push notices of unattended stops.

---

## H. Reporting and readiness

**After each package** - in `STATE.md` and user:
- What has been changed (files);
- What tests and with what result (number);
- Status (B);
- What has not been done and why;
- One next request if you need it.

**The station is complete when:**
- S0-S14 is combed and armed; `scripts/run_all_tests.sh` is 0 Failed;
- All the new pages have been browser tested on the fae robots;
- For Tank, there are resolution levels, USB failure treatment, measured response,
  Calibration and load reports, hardware stop document;
- Success detectors write the result in each "shadow" recording;
- Physical F-check package issued to user with one document
  With a chess player in UI;
- No start-up, movement or modification of old systems
  No agent.
