# Explorer 4.0 operator guide

The operator sets up the scene, demonstrates the task and records the outcome. Homebrain coordinates sensor timing, dataset formatting, the train/validation/test split, training and evaluation. The interface uses Russian labels. Their English meanings appear here.

| Page | Address |
| --- | --- |
| Explorer on the local network | http://192.168.0.168:8030 |
| Explorer over Tailscale | http://100.95.83.3:8030 |
| ROSMASTER control panel | http://192.168.0.168:8030/rosmaster/control |
| Research pilot | http://192.168.0.168:8030/research |
| CubeBot console | http://192.168.0.177:8090 |

Use the local connection for demonstrations. The remote connection has shown approximately half a second of delay. The CubeBot console and Explorer require exclusive ownership of the robot.

The red **STOP** button stops control. In the ROSMASTER panel, Space and Esc also stop motion. Switching to another browser tab or window triggers a stop. Opening a page or restarting Explorer leaves motion disabled.

## What Explorer records

Each episode associates camera frames, measured state and commands with the times they were captured and sent. The recorded data uses LeRobotDataset on Homebrain under `~/.local/share/explorer3/datasets`. A separate research log records the requested command, applied limits, the command sent to the controller, measured feedback, sensor age and voltage.

The pipeline reads episodes back and checks video and observation-to-command timing. It groups related sessions and layouts before making the train, validation and test split. Each task has its own ACT training recipe. The initial smoke test runs 50 steps and checks that a checkpoint can be reloaded for inference with motion disabled.

## ROSMASTER demonstrations

1. Turn on the robot and allow two to three minutes for startup. Check that the battery is at least 11 V, disconnect the charger and clear the space. Close control in the CubeBot console.
2. Open the ROSMASTER panel, click inside it to focus keyboard input, and acknowledge that you are beside the robot and the space is clear.
3. If the arm is folded after startup, use the arm card to raise it once. Then enable manual control. Use **STOP** or Space to stop.
4. Drive with `W A S D` and turn with `Q E`, or use the on-screen arrows. For joints, use `J/L` for the base, `I/K` for the shoulder, `R/F` for the elbow, comma and period for wrist pitch, brackets for wrist roll, and `N/M` for the gripper. Hold Shift for slow movement.
5. The Leader mirror is optional. Enable it to follow SO-101 Leader and disable it to return to the keyboard. Check the direction and gripper settings if a joint moves backwards or the gripper fails to close.
6. Select a task and layout, start recording, demonstrate, and mark success, failure or abort. For cube-to-box, keep the base still, pick up the cube, place it in the box and retract the arm. For approach, set the observation pose before recording, approach one visible target and stop in the marked zone.
7. Stop before resetting the scene. The reset occurs between recordings. Mark failed demonstrations accurately so the research log can retain them and the training split can exclude them.

## SO-101 demonstrations

1. Connect the Leader, Follower and wrist camera. Power the arms and set up the cube and box.
2. In Explorer, select SO-101 and hand over control from the existing service on port 8020. Test teleoperation and stop.
3. In Recording, select `so101_pick_place`, a session and a layout. Start a demonstration, use the Leader to pick up the cube, place it in the box and retract. Mark the outcome.

## Tank demonstrations

On November 13, a motor-controller USB disconnect prevented delivery of a stop command. The operator turned the robot off manually. One successful demonstration from that session was saved and read back. Use the current hardware checklist before recording. [Tank hardware acceptance](PHYSICAL_ACCEPTANCE.md) · [Incident record](TANK_INCIDENT.md)

1. Select Tank, enable control and wait for readiness. Use the on-screen arrows or the keyboard. Releasing the controls requests zero motion. Space or **STOP** ends control.
2. In Recording, set the session and layout. Start a demonstration, approach the visible target and stop in the marked zone. Mark the outcome, wait for the save, and stop before resetting the scene.
3. Tank records at 20 Hz and can repeat camera frames when the camera runs more slowly. The state includes the previous command. Prolonged video delay zeros the motion command, and control requires a fresh key press after recovery.
4. Return control to the Hiwonder app through the phone-app control panel if needed. Keep one controller in charge at a time.
5. The correction pilot requires a validated policy and a physically checked decision point and delay. During the correction window, use the arrows and select the completion action to hand control back before the 10-second limit. **STOP** aborts the trial. The Tank correction pilot still requires physical acceptance.

### Inspect Tank before updating onboard software

From the Explorer 4.0 checkout on Homebrain, run the following command after the Pi rejoins the network. It reads the agent’s health twice and reads software fingerprints, operator limits and permission-marker fingerprints inside the existing MentorPi container. It requires the configured Tank endpoint and the existing trusted SSH host key. The inspection sends zero motion commands. A successful check leaves the installed version untouched.

```sh
.venv/bin/python -B scripts/deploy_tank_recording.py --inspect-live
```

Read `compatible`, `reason`, `live_software` and `disk_software`. Exit status 2 means the comparison failed or the robot could not be reached. When `matches_archived_v1` is true, retain that installation. All seven runtime file hashes in the 14 November receipt matched the archived Tank bundle. That agent required fresh battery, IMU and lidar samples, checked tilt, applied profile-specific docking clearance, and required a new start after lease expiry. Its incident, bench and neutral-only permission rules also differ. Copying the old limits into the current agent would lose parts of this behaviour. The read-only result and the original bundle identify the exact base for a version-specific update. Compatible installations also require a disarmed agent with its motor connection closed and matching effective settings before an operator schedules an update. [Inspector and deployment checks](../scripts/deploy_tank_recording.py) · [Onboard agent](../agents/tank/agent.py)

## Training budget and controls

For each task, the initial target is three usable demonstrations and a smoke test. The standard starting budget is 50 usable demonstrations per task spread across independent layouts. A split needs at least three independent groups.

Open Datasets to check the data and video or change exclusion status. In Training, select the task and choose the 50-step ACT smoke test or the main ACT recipe. A past Homebrain estimate for the main recipe was roughly 22 hours per task. The trainer runs offline and the robots can be switched off. Finish any recording session before launching training.

### Queue timing and recovery

Add ACT, Diffusion or PPO jobs from the usual training pages. In the MuJoCo tab of `/learn`, the short check, full dock training, SO-101 teacher cloning and saved-policy video evaluation all enter the same queue. Open `/workspace#training-queue` to release the jobs currently listed, save a Moscow start time or hold them. A later addition needs its own release. Homebrain stores the release in SQLite. If it was powered off at the chosen time, eligible jobs start when the interface service and its worker are running again and the resources are free. The job page retains the log. SimLab saves evaluations and videos with the selected policy.

After a service restart, a job that was running is marked interrupted. Resume a LeRobot job from its saved optimizer state. A resumable SB3 PPO run requires its matching model and normalization checkpoint. Submit a fresh SimLab check, full run, clone or evaluation after interruption. The frozen article series supports `.venv/bin/python -m explorer4.study_queue stage` to queue its prepared tracks and `.venv/bin/python -m explorer4.study_queue start` to release just that series. Its ACT and Diffusion replications save progress every 1,000 updates. [Queue implementation](../explorer4/training_schedule.py) · [Frozen series](../explorer4/study_queue.py)

## Physical policy trials

1. Select a completed training job and prepare a checkpoint trial from the Trials tab. For replay, select the saved recording and prepare its command sequence.
2. Approve the trial plan while you are beside the robot. The approval is valid for three hours.
3. In the ROSMASTER panel, open Trials and Research, select the plan and start the trial. Watch the robot with **STOP** available, then record success, failure or abort.

## Randomized assistance pilot

1. In `/research`, select a frozen policy and save a pilot project.
2. Confirm a physically safe point where the robot can wait and the delays it can tolerate. Enter the decision time and allowed delays, then save them.
3. In the ROSMASTER panel, select both the trial plan and the pilot. If assistance is assigned, wait for the correction prompt. Correct the situation within the 10-second window and return control to the policy. Otherwise, observe the trial. Mark emergency intervention separately from scheduled assistance.
4. Collect at least 20 pilot trials per condition and task to estimate variation. The analysis compares random selection, risk and progress rules, the learned help-value model G, and transfer from SO-101 and Tank against ROSMASTER-only training. The pilot interface offers the 0/10/20 target-demonstration comparison.
