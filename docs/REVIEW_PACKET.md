# Explorer 4.0 is an independent review package

Version 20.11.2026: Contains: Current Results, Methods (Library and Core Parameters), Plan for Remaining
and experiments and **-prescribed expectations and criteria** on which the result will be considered
A code is not included in the package; all numbers are taken from saved runs.

Request for review - Section 8: Specific issues on which opinions are needed.

---

## 1. Question and hypothesis

**Question.** Can the robot determine what knowledge it lacks for the task, close the gap with the help of
And how much is this reducing the number of people showing?

The knowledge gaps that the robot checks before action:

| Gap| The condition of the gap| Assistant Officer|
|---|---|---|
| Where| No object position on common map below 15 minutes or error > 0.35 m| Tank explorationer / own search|
| WHAT| On board detector doesn't recognize object| a stronger model on the computational node|
| HOW| No tested size of object| SO-101 bench (cam above + segmentation)|
| SHAPE| There is no proven policy of capture for the subject.| simulation, SO-101 experience, human displays|

Hypotheses (to actual E5-E6 experiments):
- **H1.** Aid chosen by type of gap increases the success of the task compared to a single robot and with the
  ♪ Checked out in 2D, E1. ♪
- **H2.** Knowledge of the size of the object increases the success of geometric capture. * Checked at MuJoCo, E2: not confirmed.*
- **H3.** The on-board detector doesn't recognize some objects, and the strong model recognizes them; it's detectable and closed.
  The "C" gap.
- **H4 (main).** The simulation (T1) and transfer of SO-101 (T2) experiences are also given
  K shows a higher success than just one show (T0), which means lowering the required k. *E5 *
- **H5** Robot correctly defines "know/don't know" for acquaintances, strangers and new subjects. *E6.*

## 2. Installation

**Robots.**
- ROSMASTER M3 Pro (recipient): wheelbase, 5-axial arm and claw, camera on arm 640×480, lidars, deep camera.
- SO-101 (strand, donor): 6-axle hand Follower + Leader hand for teledirection, upper chamber Logitech C920 1280x720.
- Tank: Intelligence, common map.
- Homebrain: NVIDIA Jetson Orin NX, learning and major models. All implementation and data are stored locally.

**Library and models.**

| Appointment| Library/model| Version|
|---|---|---|
| Political training, dateset format| LeRobot | 0.6.1 |
| Framework| PyTorch | 2.11 (CUDA 13) |
| ACT policy| ACT (LeRobot), ResNet-18 ImageNet | — |
| VLA policy| SmolVLA (`lerobot/smolvla_base`, VLM SmolVLM2-500M-Video-Instruct)| — |
| Simulation| MuJoCo | 4.0.1 |
| A robot model in simulation| URDF /STL manufacturer (Yahboom M3 Pro), imports to MuJoCo without changing kinetics| — |
| Rapid detector (board)| YOLOE-26s-seg, Open Vocabulary (Ultralistics), MobileCLIP2-B| 8.4.14 |
| Strong model (Assistant)| SAM 3 (`facebook/sam3`, Transformers) | 5.5.4 |
| Language Gaps Adviser (K4)| Qwen3-VL-2B local| — |
| Video| PyAV | 15.1 |

**ROSMASTER real-time television record management.**
- The man leads the Leader SO-101 arm; the Leader kinetics give the tip position.
- The tip position is converted to the decart target for ROSMASTER: radius -0.077 m, height -0.007 m, inclination in the tip axis.
- The target is determined by its own reverse-cinematique ROSMASTER (0.03) in a separate process.
- If the arm is 12 to 35 degrees behind, the command is held; if the arm is behind, the mirror stops.
- SO-101 joints on ROSMASTER are not copied.

**Real episode format.**
- LeRobot, 20 frames/s: state of 6 (5 joints + claw), action 6, image of arm camera 640×480.
- An extra log with time marks for each observation and sensors (deep, lidar, IMU) packages.
- The Episode shall be accepted only if all checks have been completed:
  - 3 to 120 s;
  - All intervals between observations and personnel ≤ 200 ms;
  - The camera frame shall not be repeated more than 200 ms;
  - The actions and states in the dataset are consistent with the log;
  - The result is marked by a man.
- Failures and interrupted attempts are maintained and accounted for.

## 3. Completed results

Trust intervals are 95% of Wilson's.

### E1. Roy in 2D simulations, "bring" (50 runs)
- Conditions: K0 is one ROSMASTER; K1 is a + Tank; K2 is a + SO-101; K3 is a type of gap (the rules);
  K4 is a gap called Qwen3-VL-2B, the answer is checked by the rules.
- Ten virtual rooms per condition, same rooms under all conditions.

| Condition| Success| MI 95%| Time Median, with|
|---|---|---|---|
| K0 | 3/10 | 0,11–0,60 | 99 |
| K1 | 2/10 | 0,06–0,51 | 110 |
| K2 | 9/10 | 0,60–0,98 | 108 |
| K3 | 10/10 | 0,72–1,00 | 122 |
| K4 | 8/10 | 0,49–0,94 | 164 (1 time-out)|

- A couple of K0: K3 – 7 rooms won only with the help, 0 without it.
- Conclusion: H1 is supported in 2D. LLM counselor is no better than the rules and slower.
- Limitation: 2D perception and capture model, not real robots.

### E2. Knowledge of the dimensions in MuJoCo (180 runs)
- Script geometric seizure from the floor, six forms (tub, bottle, brace, ball, cookie, sock), 10 scenes per uniform.
- Three conditions:
  - Full information (teacher knows orientation);
  - without knowledge;
  - Dimensions of SO-101 with noise.. = 1.5 mm.

| Condition| Success| MI 95%|
|---|---|---|
| Full information| 44/60 | 0,61–0,83 |
| Dimensions from SO-101| 35/60 | 0,46–0,70 |
| Without knowledge| 34/60 | 0,44–0,68 |

- Conclusion: H2 is not confirmed. Knowledge of size is hardly a change in success; the difference with complete information is in orientation.
- The cookie (0 /10) and socks are not taken in all conditions. The robot's correct decision in this case is "to call a man."

### E3. Training in the capture policy at MuJoCo (v4)
Data:
- 200 successful script teacher shows: 215 attempts, 93 percent successful;
- 4 classes of subjects (cube, bottle, brace, ball), size × 0.8 - 1.2 inside the class;
- The starting position is chosen so that the object is in the camera frame of the hand in 30 /30 test scenes.

Training:
- **SmolVLA**:
  - Start with `smolvla_base`;
  - Frozen visual encoder, only trained by action expert;
  - 12,000 updates, package 8 (~2.8 eras), lr 1e-4, horizon 50.
  - Two options: the size of the subject in the task text and without.
- **ACT**:
  - ResNet-18, 4 encoder layers / 1 decoder, d = 512, VAE (Lattle 32, KL 10);
  - Horizontal 100, lr 1e-5;
  - 30,000 updates, package 16 (~14 Epo, final loss 0.069;
  - No size.
- The checkpoint is the last one, not selected by result.

Estimate: 20 new scenes (seads 10,000–10019), 25 with attempt, success = subject held in the transfer position.

| Policy| Success| MI 95%|
|---|---|---|
| Teacher (script, position)| 18/20 | 0,70–0,97 |
| SmolVLA with size in text| 2/20 | 0,03–0,30 |
| SmolVLA without dimensions| 0/20 | 0,00–0,16 |
| ACT without dimensions| 1/20 | 0,01–0,24 |

Diagnostics (3 scenes per model, puncture):
- The trained politicians close the claw at the same moment as the teacher (~step 100), but 3–6 cm from the subject (ACT: 3.3–4.7 cm);
- No re-entry.

Conclusion:
- Five times the increase in learning (ACT) does not correct the failure, so it is not a failure.
- The politicians reproduce the average time trajectory and do not follow the object.
- The teachers' data do not contain any correction of the missus.

### Real data to date

| Source| Attempted| Success| Accepted by Audit|
|---|---|---|---|
| SO-101, donor seizure of a cube (mark AprilTag 36h11 No. 1; rise 7–17 cm C920)| 3 | 3 | 1 |
| ROSMASTER, floor grab: Cube/Cup/Cop/Toothpaste| 27 | 14 | 3 |

Why 11 successful ROSMASTER shows are rejected by the audit:
- 8 has a break in the record 0.5–2.7 s. The reason is found: lock the database on the computer node. 19.11 is corrected, the new record has not yet been checked.
- The camera was repeated at 3 in continuous action.

## 4. Preliminary E4 result: Recognition

First camera of the hand is from real show, request for an object name:

| Subject| YOLOE-26s (board)| SAM 3 (Assistant)|
|---|---|---|
| Cube| Found, 0.89| found in 3 of 5 episodes (0.91–0.95), 2 (not debriefed)|
| Candy (bunny wrapper)| No name found for any of the 4 names| found, 0.82 (candy only)|
| Toothpaste| No name found for any of the 4 names| Found, 0.57 (toothposte only)|

- Pre-H3 is supported, but the sample is one frame for the subject.
- The sensitivity to the wording of the request is visible.
- Full marking of all episodes (subject, frame, confidence) will be done after the recording.

## 5. Plan of remaining experiments

### E3+ (simulation, non-human)
- The same ACT, but the center and size of the object from the detector on the first frame are added to the state.
- Everything else is like E3, the grade on the same 20 scenes.
- **Expectation:** success is markedly higher than 1 /20.
- **Criteria:** ≥ 6 /20 and Fisher's exact test against 1 /20 with p < 0.05. This result confirms that there is a lack of information on the status of the object.
- **If ≤ 2/20:** Conclusion "the box is not enough, there needs to be a closed guidance loop." It is published.

### E5 (main, real ROSMASTER)
Learning options (ACT policy, same reference weights, number of updates and sensors):
- **T0** is only the ROSMASTER's own show;
- **T1** is a pre-selection for 200 MuJoCo shows, followed by a pre-supplementary presentation for their own;
- **T2** - T1 + shows obtained by moving SO-101 to ROSMASTER mechanics:
  - The trajectory is recorded relative to the subject and divided into phases (approach, capture, climbing);
  - The movement is reproduced by its own reverse film ROSMASTER, and the donor joints are not copied;
  - Failure if donor measurement error > 5 mm by position, > 0.2 rad by orientation or > 3 mm by disclosure.

k = 0 / 5 / 10 / 20 self-images equal to the subjects. All derivatives of one donor display are held in the same breakout group.

Evaluation:
- **Without robot, for all 12 models:** error of action on 5 postponed real shows (1-2 for subject) gives the curve "quality from k".
- **On the robot, at k = 20 for T0, T1, T2:**
  - 10 attempts (if time allows - 15);
  - The items are pre-set and the same for all options;
  - The order of the options is mixed;
  - success = subject raised ≥ 5 cm and retention 2 s; decision is made by the video observer.

**Expectations (fair):**
- For E3, the absolute success on the robot at k = 20 can be low in all options (0-30%).
- The main difference is offline and small k.
- H4 is considered to be supported if both conditions are met:
  - Offline error T1 /T2 below T0 at k = 5 and 10 on all three subjects;
  - on a T1 or T2 ≥ T0 + 4 success of 10.
- Otherwise, "not confirmed" with the size of the effect.

### E6 (real, self-assessment of gaps)
- The robot gets the command "take X" and before moving, it says, "I'll take my own help (what's the gap).
- Set of cases:
  - familiar subjects with a model trained in them;
  - A subject excluded from the training of a particular model;
  - a new object, never recorded (chosen in advance, no robot shown).
- Metrories: share of correct decisions, false "know" (a dangerous one), false "I don't know" (an unnecessary help).
- **Expect:** false "know" on a new subject - 0.

### E7 (full chain demonstration, time)
- "Bring" mission: 3 runs with piano and 3 without.
- The result is descriptive, not statistical.

## 6. Record plan

| Recording| Robot| How many| Appointment|
|---|---|---|---|
| Grabbing from the floor: cube, candy, pasta| ROSMASTER (through Leader)| ~20 successful, total 25 accepted (E8 for the purpose)| E5 (20 studies + 5), E4, E6|
| Donor candy and pasta capture| SO-101 | 3| E5-T2 for all items|
| New subject| — | not recorded| E6 |
| Post-training tests| ROSMASTER | 30-45 attempts E5, ~10 E6, 6 E7| Totals|

ROSMASTER:
- One series - one subject;
- The whole object in the camera frame of the hand before the recording begins;
- Each display is a new place and a turn, 16–26 cm in front of the robot, without moving the wheels;
- Capture: lower, squeeze, lift ≥ 5 cm, hold 1 - 2 s;
- Failures remain at a mark.

Outside the article:
- Transfer of the subject to the person;
- Tank dataset;
- Video training on the phone person (last job).

## 7. Known limitations and threats of valitude
1. There are few real data: 3 objects, ~25 demonstrations, 10-15 test-by-conditions checks. Only major effects are detected (E40 para.
2. The show is run via television with another movie (SO-101 ♪ ROSMASTER) and the operator's style of motion may differ from that of ROSMASTER.
3. Simulation objects are rigid boxes of approach. The servo dynamics in MuJoCo are not identified, and the manufacturer's parameters are taken.
4. One cameraman, one room, one floor.
5. Detectors are evaluated with a name request; the result is sensitive to the wording (see E4).
6. 2D-Roy (E1) is a simplified model of perception and capture; the tolerance to real robots is only verified by E7 demonstration.
7. In early entries, the text of the problem series does not match the actual object (5 episodes of cube with the general text). To be corrected in metadata before training, the source is retained.

## 8. Questions to the Auditor
1. Is E5 design enough (T0 /T1/T2 x k, offline-crystal + 10-15 robot attempts at k = 20) to justify H4? What is the minimum to add?
2. Is the offline evaluation metric (delayed display error) used as a substitute for real attempts at small k?
3. Is E3+ (the frame of the object in position) enough to explain the failure of E3 or is it necessary to have a closed-down experiment?
4. How can we better view the negative results of E2 and E3 as a separate contribution or motivation?
5. Is E4 /E6 sufficient to say "the robot understands what he doesn't know" or does it need a calibrated measure of policy uncertainty?
6. What basic lines of literature are required for comparison (e.g. teaching only in human shows of a larger volume)?
