# Explorer 4.0: What is ready, what is left and how to get a trained system

**For a historical cut before R0-R9.** For current tolerances, limitations and recording procedures, see [CURRENT_STATUS.md](../CURRENT_STATUS.md) and [](RECORDING_DAY.md) recording day. The following permanent lockdown of Tank is replaced by failure processing and a clear reset of the session.

Screen on 14 November 2026 Repository: https://github.com/vladromenko/explorer-4.0.
Program delivery: `5047468` main block, `7305589` interface, fixation
Supply `e94eb00`The document describes the actual boundaries, not promises quality
Sources: CURRENT_STATUS.md, audit of AGENT_CONTRACTS.md
DATASET_GUIDE.md and saved program test results.

## 1. Is the basic design complete?

Core programme framework implemented and established.
I want you to take a particular platform and then collect it.
Re-positioning of the project or additional simulation or embroidery is not necessary.

But the "only tests" claim is inaccurate. There's a Tank hardware blocker,
Physical calibration and still not completed training on sufficient data.
New VLM/symmetrical routes written but prohibited from running in full
Such runs may reveal the need for corrections.
The system is not yet an autonomous robot team.

The intended workflow starts by **acquiring control and recording a single task**, then gathering
♪ show ♪ check and record the set ♪ separate permission for training ♪
test the retained policy ♪ conduct limited real tests ♪
Collect corrections.. repeat training if necessary.**
Coordination uses the skills already adopted, not creates them by a text team.

## 2. What's been realized

| Part| What's doing now?| Readiness boundary|
|---|---|---|
| Homebrain / Explorer :8030 | General interface, control, recording, viewing, testing, training and task line| Cold start and pages checked; launch control off|
| SO-101 | Existing TV operation Leader ≤ Follower, wrist camera, recording cube \box| Old shows saved; short re-entry of updated tract|
| ROSMASTER | Copy of /XYZ/ hand control joints/shassi, connection to Leader, recording of selected tasks| The previous control was taken by the operator; new records with the environment require acceptance|
| Tank | Own agent, copied full-time driver, control and recording, Wi-Fi, individual sensors| Normal traffic is blocked from the unsolved border of STOP /USB|
| Environment| RGB, dept, lidar, IMU, camera parameters, raw bags; ROSMASTER also has rear lidar, odom, mag| Data availability checked; total metric calibration not completed|
| ROS 2 | Separate common observation tyre, local reference systems, general view, MCAP| Not a general uncontrollable publisher of the motor command; performance through the previous /API controllers|
| Datasets| Official LeRobot format, video, state, action, times, outcome, origin, group breakdowns| Diagnostics and synthetics don't become real displays.|
| Training| Official ACT, SmolVLA, Diffusion; simulation PPO /Playground; preparation of new launches and further training| Support depends on profile; no new long launch was performed|
| Simulation| Four Wednesdays and the world, SO on the table, mobile robots on the floor; CAD and contacts| Dynamics and general installation not calibrated by gland; new geometry not accepted by fresh run|
| Local models| Qwen3-VL-2B, YOLOE, SAM3 downloaded; files checked; ByteTrack connected| New VLM Direct Approach is checked for input preparation, not new generation|
| Agents| Six programme roles, one model worker, registered skills, limited plans| LLM does not direct the servo drive and does not issue permission|
| Mission perpetrator| Past trials sequence, STOP/resign/lost browser, save result check| Physical clearance and proven skills required; next step requires clear confirmation|
| Help Memory| Sources, versions, compatibility, negative cases, relationship of the original case and the new episode| The memory transfer is a hypothesis; success of one platform does not prove the benefit of another.|
| Research| Fleet allocation, AutoIntervene-adapted, re-recovering, G preparation, frozen M0-M3| Scientific impact requires current comparative series|
| DART-inspired | Limited noise from ACT error; expert intent, command and Wednesday response separately| Only sim, not complete DART; no new collection started|

The old:8020,:8090, WristLab and the factory systems of this shipment have not changed.
The ROSMASTER /Tank's own agents files are checked against the repository.
The agent functions are running on Homebrain over these components.

Verification base: 92 software tests and 2 additional tests have been completed;
2 model forward tests are deliberately excluded. Then the affected ones are repeated.
contracts and checked pages at Chromium.
Five previous successful real episodes are reread: SO-3,
ROSMASTER BASES - 1, Tank - 1, Hand records with aborted results are not renamed
It's not enough for basic education.

## 3. What's left and where the operator needs it.

| Item| What Is Needed From Man| What remains an engineering job|
|---|---|---|
| ROSMASTER| Activate a charged vehicle without charger; be close; check the motion, STOP, mirror and record test displays| Check the records/sensors and correct the defect if it appears|
| Independent STOP Tank| Provide physical access and implement agreed actions on the stand after choice of solution| Set up a confirmed vehicle stop mechanism for loss of USB. Documented embroidery/hardware watchdog/selected power-off; solution not yet selected and implemented|
| Tank Reception| After STOP decision: stand-by check, then three separate access points without charger| Check the causality of the data, the sustainability of the communication and close the incident only on the basis of results|
| SO-101 | Connect arms/cam, perform short follow-up and test displays| Check stored commands, videos, calibrations and return of old controls|
| General scene| Measure actual dimensions/positions, show a general orientation, perform agreed calibration movements| Calculate and check transforms/synchronization, dynamics. This result is not yet available|
| /RGB Microphone| Listen to the short tape, check the actual light| There are interfaces; this is not a mandatory condition for the main motion dataset.|
| OLED ROSMASTER | Re-use of buttons alone will not solve the problem; access to other fees/stitching may be required| No documented command of the current MCU. Full-value screen support is not implemented and not required for the dateset|
| New model/symmetric tests| Specially authorize limited launch; no need to be present at the robot| Implement real VLM/sequence scenarios, check the result and correct the errors found|
| Dateset and training| Show tasks, drop the scene, honestly mark the outcome; then agree on the learning budget| Data checks, preparation, training, evaluation and reporting are done programmatically|

A stop by a normal vacation or a Wi-Fi timeout does not close the USB failure.
The fee should stop even when Raspberry Pi can't deliver
STOP – Now you can't promise that this is only a Python code change.

You don't need to turn the whole park on.
After the blocker has been decided, then SO-101; the total pair after the individual tolerances.
For a single dateset, you don't have to wait for the entire team to be ready.

[Straight physical checks at Explorer](http://192.168.0.168:8030/datasets/acceptance).

## 4. What datesets to collect

### Main demonstrations: separate task set and entry composition

| Recruitment| One episode| Proposed first volume|
|---|---|---|
| ROSMASTER arm| Take a cube ♪ put in a box ♪ open a capture ♪ take your hand away ♪| 3 test and then ≥50 suitable successful displays|
| ROSMASTER-Base| From the initial area, approach the apparent fixed target and stop in the marked area| Same, separate set|
| SO-101 | Cube ♪ box ♪ let go ♪ hand away, table setup| Same, separate set|
| Tank | Access to target and stop in zone| Only after the closure of STOP /USB; same, separate set|

50 - current technical minimum basic recipe, not a promise sufficient
At least 3 truly independent groups are needed.
The organization has 10 separate series of 5 successes, with different permissible positions.
Failures and interrupted attempts also persist, but are not among the 50 successes.

For ROSMASTER and Tank, it is desirable to choose the **-deep version immediately after the adoption
The regular RGB profile and the expanded profile are different sets and different profiles.
The old RGB shows are not turning into RGB-D ex post facto.

The recording contains video, status, command, time tags, output and
The extended profile adds numerical features of the environment,
Missing/old masks and raw cloud packages.
points or microphones do not mean that the current model automatically uses them.
Tank keeps the previous command rating, not the measured wheel speed.

### How to Write

1. Accept /STOP control and three short entries for the selected task.
2. In Explorer, select platform and profile. Open for ROSMASTER
   http://192.168.0.168:8030/rosmaster/control; for SO /Tank is the main screen and record.
3. Set the session and location, e.g. `ros-arm-s01` / `ros-arm-layout01`.
4. Start recording, wait for the staff to grow, do one job.
5. Mark the real result: success, failure or interruption. Wait for conservation.
6. Only after stopping can you return the scene.
7. Review the episode in the Dataset and perform the data/video verification.
   The wrong episode is excluded from the training with the source.

For the arm, vary the permissible position/orientation of the cube, moderate background and light;
Keep the cameras fixed, calibrating and purpose of the task.
Arbitrary new targets without corresponding
Policy entry is not considered a supported objective.

General session **or** General placements relate episodes to one group, including
Transit links. Do not rename one scene for artificial receipt
The next shots of one episode never separate between the train /test.
For 10 unconnected groups, the standard separation is approximately 8 /1/1 groups:
The standard is calculated by the teaching part only.

### Additional data for article

- **Creation: ** Selected segments of human intervention after difficulty
  The policy is still in place, the moment of the request,
  Delay, boundaries of the command source and result of continuation.
  Dangerous refusals to mix political teams with human standards.
- **Relief and memory:** observation before assistance, recipient's version of skills selected
  assistance, actual actions, time/cost, output of assistant, recipient
  and the whole task; the donor erisode connection ♪ memory case ♪ recipient erisode.
- **General sensors/calibration:** Diagnostic synchronous records and measurements
  Without action and outcome, they are not motor skills demonstrations.
- **Simulation shows:** separately marked human /scripted/learned sources,
  The version of physics and seeds. The branches of one state remain the same group.
  Synthetics don't go hidden in the real set.

## 5. How the system learns from these data

### Motor skills

1. On http://192.168.0.168:8030/training/prepare select the task and the suitable display.
   The LeRobot format, video, channels/units, times, sources of action,
   Initial sensors and group independence.
2. Prepare an unchangeable plan: list of episodes, reference amounts, breakage,
   Model, final number of updates, package size and initial weights.
   Training doesn't start.
3. After a separate permit, the official LeRobot trainer teaches politics
   To predict observations and human displays.
   It's not just a single video.
4. Save kheckpoint with configuration and normalisation, check individual downloads
   On validation check error/conduct to select version.
   Test to leave for final evaluation of the recorded choice.
5. Prepare limited real tests. Low error on files or loss
   They don't prove that the robot is taking a cube or stopping in the zone.
6. If not sufficiently qualified, add particular problematic conditions or
   Amend the text to read:
   The groups are retained, and they cannot be accidentally transferred to education.

Current matrix: ACT is the first supported physical track ROSMASTER /Tank,
including for extended entrances; SO-101 has prescriptions for ACT /SmolVLA/Diffusion.
The availability of a prescription does not mean a physically accepted trained policy.
does not receive the dept /lidar automatically; additional entrances are used
The PPO is a simulation rather than a self-contained profile.
A dangerous search for behavior on a real robot.

Each task teaches its own policies with its own channels and units.
SO-101 joint command does not become ROSMASTER reference command,
And the speed of Tank is a target arm action.
The park and any errands, this training has not been received.

### Vision and agent layer

Qwen3-VL, YOLOE and SAM3 are used as pre-trained components.
The gathering of demonstrations does not automatically trigger their training.
The focal point selects the available skills that are registered.
The controllers check separately the tolerance, freshness and STOP.

General memory updated by verified episodes and facts, without weight change
The unconfirmed transfer remains a hypothesis.
To prove the usefulness, M0-M3 is compared to the same available skills,
Budgets, scenes and initial memory, taking into account failures and unknown results.

The G-valueer is a separate model of the benefits of intervention.
Aid/no-aid outcomes and the cost of intervention, not just successful
As long as there is no suitable trained artifact, G is marked
The simulation effect is not available and a fixed basic choice is working.
You can't be a real person's expert.

## 6. What to consider as the end

- **Readability for task collection:** taken control of /STOP, three actual records
  Read and seen, entrances and outcomes are true.
- **Dateset Readiness:** Adequate shell, honest groups,
  Control amounts and recorded break-up.
- **Trained:** sheckpoint is independently tested and agreed upon
  Physical evaluation of the task: The criteria and number of attempts shall be recorded before testing.
- **Reliance of the result of the article:** reproducible comparison with basic methods,
  This is the next experimental activity.
  The stage, not the proven result of the programme delivery.

The next practical step is to separate ROSMASTER and select one set
No other robots are required
Work simultaneously to get the first suitable dateset.
