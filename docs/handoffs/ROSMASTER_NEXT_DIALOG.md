# The task of the adjacent dialogue is: ROSMASTER in the existing Explorer 4.0

Continue to develop ROSMASTER in the existing Explorer 4.0. This is a separate message from the user. Do not re-create the project, do not roll the current changes and do not rewrite the ready management. The main dialogue has suspended work on Homebrain at my request; after your work, it will come up with results.

## 1. Where the project and what to read first

- Homebrain: `/home/jetsonnx/Projects/explorer-4.0`.
- Data, own environment/kash/calibration: `/home/jetsonnx/.local/share/explorer3`.
- GitHub: https://github.com/vladromenko/explorer-4.0. Archival audit at the time of the previous transfer: `2561828`.
- Main interface: http://192.168.0.168:8030; ROSMASTER: http://192.168.0.168:8030/rosmaster/control.
- The last known address of ROSMASTER: `192.168.0.177`; user of `vlad`; own `/home/vlad/explorer3`; parent address 8090 - `/home/vlad/CubeBot`. The address, accessibility, versions and state of the service should be checked, not considered as a current measurement.
- Read `STATE.md`, `CURRENT_STATUS.md`, `docs/PROVENANCE.md`, `docs/OPERATOR_GUIDE.md`, `docs/SIM_MODELS.md`, relevant git diff and applicable AGENTS.md.
- The underlying task is to move from the](/home/jetsonnx/.codex/attachments/422e186e-2fb3-43fa-9d9b-fb12ff3592cb/EXPLORER_3_0_SIM_REAL_REUSE_CODEX_RU.md) simulation. For you, especially sections 8, 9, 13 and the requirements for the interface.

Historical documents contain outdated records, including the old step numbering. Priority is given to the last STATE, current code, current corrective task and direct user instructions. Do not reset the already corrected patch.

## 2. Limits of work and preservation

1. Your area is ROSMASTER's own agent, integration, camera, manual control, recording, test preparation and data for model refinement. The general simulation, R2 /R3/R5 studies, the perception of YOLOE /SAM3 and the general training prescriptions remain the main dialogue.
2. The old SO-101 /Wristlab on Homebrain `:8020`, its code, services, environment, data and processes do not change or stop. Tank does not plug in, correct, or remove its locks.
3. The old Consol 8090 is a saved work source and return route. Copying the necessary in your own area is possible; new amendments to the Explorer can not be transferred to the original Consol. Do not create other panels instead of the user selected.
4. Do not remove other changes. In general, shekout at the time of transmission has uncomplexed perception work: `configs/sim-requirements.lock.txt`, `explorer3/{app,fleet_pages,jobs,sim_pages,training}.py`, new `explorer4/perception.py`, `explorer4/vision_pages.py`, `scripts/check_vision_browser.py`. These files do not commise with their entire work and do not drop. If necessary, change the common file to separate only their lines. Before completing, check the diff.
5. Global workflow now `stage=A`, `hardware_connections=false` in runtime `configs/workflow.json`. Phase A is not yet complete. This gear selects ROSMASTER as a separate work, but does not mean A /B and does not allow all robots to be opened in silence. First, preparation and auditing without movement are required. If a single hardware session requires a transition, agree a specific action with the user and limit it to ROSMASTER; write down the exception and actual state.
6. Do not start learning in simulations, long learning, fine-tune or optimization: the user wants to start basic learning itself after the program is ready. Final software tests, readback, downloading existing checkpoint and inference without an optimizer are allowed. Even the old task of training smoke is not now automatically running.
7. Do not restart the common UI with active management/recording/task. Check current resource ownership. At the time of transmission, there was also an isolated test UI on `127.0.0.1:8035` with DATA `.../validation/browser-sim`; it is part of the main dialogue. Do not use its ports/data and do not follow wide pkill.

## 3. What has already been done and what it does not prove

- The user selected Console 8090 as the last normal panel. Its interface and control are copied to the Explorer. The basic keys/directions and chassis were previously confirmed by the user. Later, sessions were disrupted, so the historical confirmation does not replace the current intake.
- The original ringtime uses copies of BaseIO, VelocityShaper, ObstacleGuard, CartesianJog, MirrorMapper, ArmModel and the original BridgeCore /Link., Old Web Backend should not be a function of research/recording.
- There were corrections to the heartbeat sequence, blocking by long actions, canceling the controller, the old pose after STOP, the ranges and conflicts of the low position model, and some restrictions then changed back: not accidentally re-establishing the early version.
- The last significant STATE records of November 13 are: measured vertical position Leader - Pan -4.4°, liff 2.0°, elbow -83.5°, wrist -1.5°, roll 2.2°, gripper 0.9. It compares vertical ROSMASTER 90° on the first five drive units (DEFAULT_PAIR).
- The last mirror match confirmed in the log: `[1,-1,-1,-1,1]`; in Console 8090 absolute mode, scale 1:1 and speed 35°/s. The ringtime mentioned a 40°/s level. Check the existing seizures and implementation, not substitute them for the guess.
- Record 07:05: Leader's long start blocked the processing of the chartbeat panel. Actions are made in a separate sequence task, STOP is processed immediately. After correction, the live verification of the vertical position was passed. Record 07:20: also operated in a mirror through 8090 and a separate `leader8090.py`.
- The seizure previously gave 3,2767/unable feedback over an old bridge; the original seral agent later saw all six transmissions. It cannot be said that the reason was only in the battery or that the Feedback is now guaranteed. Check every channel, age and reliability. Not to replace measurement by a team or a supposed pose.
- ROSMASTER's non-movable software records exist, but are not three real demonstrations of the task.
- Homebrain already has a model of original Yahboom M3Pro URDF /STL/SRDF. Hand Contact Checks: 3 /3 crypted transport, maximum penetration of about 0.221 mm. This is a mechanical simulation test, not a policy skill, nor a calibration of the physical robot. The base is a force flat model, its dynamics are not yet identified.

## 4. Implementation

### Step 1 - check actual uninved installation

First, look locally at the code, saved logs, seizures and provenation. If ROSMASTER is available, read the versions/shesheshes of your own installation, services, the owners of the serial /camera, actual boot, /feedback power and last errors. Do not turn on the control for diagnostics. If it is off, complete all available locally and then ask only ROSMASTER to turn on the specific target.

Compare the developed version to the repository, save your own installation reserve and a precise list of changes before unplugging. Do not rescan the controller or correct the factory zeros/calibrations without separate subject matter.

### Step 2 - End steady control /data path

- Single ownership of the seral and camera, explicit transfer of the Explorer \ old system. Delete simultaneous motor access to two backends. Simultaneous independent operation with another platform should not be artificially blocked by a common robot selection button.
- Individual base and arm profiles; one ROSMASTER cannot be simultaneously owned by two incompatible tasks.
- Save the understandable interface of the selected 8090 in the general Excel style: Camera, fresh state, activation, STOP, XYZ/systs, keys/joist, record. Remove misleading status, show specific cause of failure.
- Address the de facto log controls. STOP and Watchdog are retained. Do not treat the bursts by the deactivation of the security, silent endless re-entry or fictional feedback. After STOP, operator/communication loss and restart, the movement does not resume itself.
- The start-up of the agent/cam must be reproducible and inert. The historical request for arm lift on loading does not mean that the right to send unexpected moves during this operation is not allowed. Check the previous behaviour and make the preparation of the hand a clear controlled operation with STOP; any changes in the vehicle movement will be agreed subject matterally.
- The mirror save and check the existing adapter/signs/limits, do not rewrite it. Do not convert it into a condition of readiness for stage B if the keyboard/joystics allow the display to be recorded. The connection of Leader and the release of Wristlab resources is only for a specific agreed check, not automatically.

### Step 3 - Data and Model

- Check real camera timeamps/frequencys, six-channel feedback, sent commands and times of availability. Do not subtract the monotonic hours of different machines without the specified conversion. Unmeasured lateny /response is null + mask, not zero.
- Check the relevance of section 9 of the main task: the Task Force's comments: the Task Force's Task Force's Task Force Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force 9 comments: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force: Task Force 9 comments: Task Force 9 comments: Task Force: Task time: Task Force: Task Force: Task Force: Task Force: Task Force: Task; hardware/operator abort separately; Unknown: Unknown_response_kind_kind: Unknow; research route: This is not `leader8090.py`.
- Copy only the required real geometric descriptions/coefficients in your own design with reference routes and hashs. Check the specified hand, direction, scope, limits, camera position with MuJoCo. The manufacturer does not prove the caste hand.
- For chassis, determine which odometer is actually measured and which commands integrate; record units, frames, axes, frequency, time scale and masks of inaccessible sensors. Not count command-integral measured trajectory.
- Prepare a compact report for the main dialogue and a set of tested parameters. Changes to the general sim model are performed separately and only with evidence; hold measured, published and assumed separately; and identify on independent trajectory, deteriorated parameters not apply.

### Step 4 - End-user scenarios

First, the program checks with a fake transporter and a browser, then a short physical reading with a separate user confirmation: a free space, a power/charger, and a presence at the switch. The old permissions from history are not a confirmation of the current scene.

For base and arm individually: direction, retention/dismissal, STOP, tab opening, loss of communication, lack of self-renewal. Request the user short, specific, one check; do not request the entire park to be turned on. The logs of the sent STOP do not prove physical stoppage in themselves.

After successful management, three real displays of each task:
1. Base: approach to the apparent target and stop in the designated area;
2. arm at fixed base: cube, box, move hand.

Check the first file before the following shows. Save the official LeRobotDataset and slidecar design: real /human, profile, task, scene /session, hashes, outcome, termination_reason, timemps and masks.

Do not start a training and self-testing exercise without a separate user indication. No policy is an honest status, not a fake success rollout. Do not require dozens of new shows to complete the program.

At the end, check the release of the resources and return the previous control without changing its originals. Request that the ROSMASTER be turned off if the work is local: the battery does not waste time waiting.

## 5. Useful entry points

- `agents/rosmaster/{agent,runtime,leased_core,control_adapter,observer,feedback_diagnostics,handoff}.py`
- `agents/rosmaster/{start-agent,start-camera,environment}.sh`, service units, provenance JSON
- `explorer4/rosmaster_{control,console,mirror,session,monitor}.py`
- `explorer4/static/rosmaster-console.html`
- `explorer4/leader8090.py` — Separate compatibility, not research route
- `tests/test_rosmaster_*.py`, `agents/rosmaster/test_runtime.py`, `agents/rosmaster/console-fixes/`
- `scripts/rosmaster_pipeline_check.py`, `scripts/analyze_rosmaster_capture.py`
- `explorer4/sim/rosmaster_arm.py`, `docs/SIM_MODELS.md` is a model that does not confirm physical tolerance.

The tests are to be selected for changes; the whole set is not to be turned blind if it can turn to equipment or learning. The simulator and the actual application must be clearly separated.

## 6. What to Leave for Return to Basic Dialogue

Enter the `docs/handoffs/ROSMASTER_RESULT.md`, add the dated entries in STATE.md without rewriting the story of others. Do not declare the entire A /B complete by the result of the separate part.

The outcome should include:
- What is corrected and what is actually verified; what remains unconfirmed;
- Include commit IDs, changed files and any uncommitted changes.
- The heshes/tracks of a truly developed code, services and resource ownership;
- The state of supply of the robot, stoppage, tolerance and workflow after operation;
- Check/browser reports, real erisode IDs, quality and data supply;
- Measured parameters/time scales for sim, missing measurements;
- Ready next scenario commands/buttons and the exact remaining physical step;
- Whether there's nothing left to automatically control the robot or learn in the background.

To communicate and send to the GitHub repository only their complete changes with the checked diff; not to publish secrets, user calibrations or vendor accessories with an undetermined licence. Do not include the unfinished work of the main dialogue in its command.

Do not return another plan instead of implementation; work before the test result in this area; only ask me for a specific physical action, a motion evaluation or a real missing access; when a physical confirmation is required, do not bypass it by a sham test.
