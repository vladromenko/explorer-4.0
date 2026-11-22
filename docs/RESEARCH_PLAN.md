# Explorer 4.0 is a single study and article plan

It's the main document: what's done, what's left, what's needed and what's what's coming from it.
The old documents (ARTICLE_TASKS_RU, SHOWS_INSTRUCTION_RU, TODO_NEXT_RU, RESEARCH_ROOT_RU) are the history and details;
This file is not valid when the rights are separated.

---

## 1. Question of article

** Can the robot understand for itself what knowledge it lacks for the task and close this gap with the piano —
And how much of a human show does it take?

Robots: **ROSMASTER**(received: wheels + hand, camera on hand),**SO-101** (stairs on table: camera on top,
measure objects, give experience of capture), **Tank** (explorer: search for items on common map),
**Homebrain** (computation: learning, major models).

Four types of gaps and who closes them:

| Gap| The robot asks himself| Who Helps|
|---|---|---|
| Where| Do I know where the subject is?| Tank / own search|
| WHAT| Do I recognize this subject?| Strong Homebrain (SAM3) model instead of fast YOLOE|
| HOW| Do I know the size and how to take it?| SO-101 (measurement)|
| SHAPE| Do I have a trained seizure of this subject?| Simulation, SO-101 experience, human displays|

## 2. The structure of the article and what each experiment proves

| # | Experiment| Entry (data)| Measure| Conclusion for article| Status|
|---|---|---|---|---|---|
| E1 | Roy in 2D "bring"| 50 runs: K0 one ROSMASTER, K1 + Tank, K2 +SO-101, K3 gap assistance, K4 called Qwen| 10 success| Helping to fill a specific gap ~ single and fixed assistant; LLM is no better than rules| **Ready**: 3, 2, 9, 10, 8 /10|
| E2 | Knowledge of the size in MuJoCo| 180 geometric seizures, 6 forms| 60 success| Size is hardly helpful to geometric capture (34 ~ 35, complete information 44); flat objects do not take the correct answer "to call man"| **Ready**|
| E3 | Simulation training| 200 demonstrations by MuJoCo teacher| success of 20| The simulation without object position is missed by 3–5 cm (SmolVLA 2 /20 and 0 /20, ACT 1 /20, teacher 18 /20). **Add**: same ACT with the detector position at the inlet \\ link which /where is seized| Negative is ready; "with situation" is 1 night without human participation|
| E4 | Recognition as a Space| first set of all real shows + check frame; signature of subject in series| % of YOLOE vs SAM3 recognized| A fast model on a robot doesn't recognize a part of the objects ♪ robot sees a gap ♪ That gets a response from a strong model| Preliminary: YOLOE .89, candy/paste, no; SAM3 candy .82, paste 0.57. `scripts/label_episode_objects.py` |
| E5 | **Main real**: seizure from the ROSMASTER floor| Real shows ROSMASTER (3 subjects) + 200 demonstrations MuJoCo + SO-101 experiences| The curve "failure of its show k = 0 /5/10/20 " in three versions| How many shows a person saves a rouge| Records required (Section 4)|
| E6 | Self-assessment of gaps in the real robot| familiar subjects, subject without showing, subject "before/after"| Is it true if the robot said "I know/I don't know/need help"| Robot knows what he doesn't know and he's missing blind.| Need to check after training|
| E7 | Full mission to bring (demonstration)| 3 with piano + 3 without| success, time, intervention| The whole chain works on real robots.| Time; cut|

### E5 - Study options
- **T0** is just a show of ROSMASTER.
- **T1** is a 200-show pre-show for MuJoCo + self-shows.
- **T2** – T1 + SO-101 experience, transferred to the ROSMASTER mechanic (MimicGen adaptation, its own IK ROSMASTER).

For each version of k = 0 /5/10/20 of its own display. The same reference weights, number of updates, sensors.
- Without robot: All 12 models are estimated to be **5 postponed** real shows (faults) - a full curve.
- On the robot: k = 20 for T0, T1, T2 = 10 attempts (E1 hour with owner).

The expected image:
```
Success │            ● T2/T1 (with fleet assistance)
      │        ●        ○ T0 (without assistance)
      │    ●       ○
      │●      ○
      └──────────────────── local demonstrations
       0   5   10      20
```
If a curved above saves human appearances, the difference in k axis is the answer is "how many."
The negative result is also published.

### E6 in detail — how we check "understand what we don't know"
| Situation| The robot's Right Answer|
|---|---|
| Subject on which the cube is trained| "I know, I'll take it myself"|
| Subject not taught by this model (paste without paste)| "no skill ♪ calling for help"|
| A new subject that never was recorded| "I don't know ~ help or person"|
Measure: the share of true decisions, false "know" (a dangerous thing) and false "I don't know" (an unnecessary help).

## 3. What is already available in the data (20.11)

| Source| Yes| Education|
|---|---|---|
| MuJoCo, pair v4| 200 successful| 200 |
| SO-101, donor cube seizure (AprilTag No. 1)| 3 successes| 3 (pack not yet collected)|
| ROSMASTER, floor grab, s02 series of cube / s03 candy / s04 paste| 14 successes, 5 failures, 8 interrupted| 3 clean; 3 short re-schedules of camera (probably fit); 8 with 0.5 - 2.7 s hole (part cut)|

The reason for the hole was found and corrected 19.11 (Homebrain lock-ups); check the first two session records.

## 4. What records to make (and why each)

| What| Robot| How many| Why?|
|---|---|---|---|
| Grabbing from the floor: cube, candy, pasta| ROSMASTER + Leader | ~20 successful (total 25 pure, ~8 for item)| E5 (20 studies + 5) postponed), E4 (staff), E6 (student subjects)|
| Donor candy and pasta capture| SO-101 | 3 demonstrations (~15 mines)| E5-T2 for all items|
| New subject - **Not write**| — | Select and postpone (tyre, mandarin, sponge)| E6: unknown subject|
| Post-training tests| ROSMASTER | 30 attempts E5 + ~10 E6 (+6 E7)| Totals|

ROSMASTER (important for the article):
1. **One series = one subject**, title by one English word: `cube`, `candy`, `toothpaste`.
2. **The "Listen" is seen in the entire hand cell** — the detector finds it on the first frame (E3 /E4).
3. Each show is a new place and a turn, 16–26 cm in front of a robot; no wheels.
4. Down, squeeze, lift ≥ 5 cm, hold 1–2 s. Failures are F11, do not remove.

Do not (outside the endline): Unit 4 "Transfer to man" (50 SO-101), transmission locations, Tank dataset,
Video training on the telephone (the "best work section").

## 5. Working arrangements

| Step| What| Who| Time|
|---|---|---|---|
| 1 | Depletion of timeout Leader 1 with ROSMASTER (in pause, with consent)| I| 2 min|
| 2 | 2 test records ♪ check that no holes are present| Owner + I| 5 minutes|
| 3 | ~20 ROSMASTER captures| owner| ~45 min|
| 4 | 6 donor shows SO-101 (confection, pasta)| owner| ~15 min|
| 5 | Item Mark (SAM3), Audit, Hole Cut| I| Without robot|
| 6 | SO-101 ♪ Transfer to ROSMASTER (MuJoCo)| I| 1-2 days|
| 7 | T0 /T1/T2 × k, E3 "with position" at night, one after "may" owner (noise)| I| 2 - 3 A.M.|
| 8 | Checks on the E5 /E6/E7 robot| Owner + I| ~1,5 h|
| 9 | Tables, graphs, article text, dateset publication| I| — |

## 6. Restrictions called in the article
- One recipient (ROSMASTER), three subjects for training, one new for testing.
- The size of the objects in the simulation is model; 2D-Roy is a simplified model of perception.
- The transport of SO-101 is through measured geometry; quality depends on the accuracy of the measurements of the bench.
- Small sample checks (10) are confidence intervals.

---

## 7. Decisions after independent review (20.11.2026)

External review of 20 November 2026 (PDF, 66 works): Main observation: declared contribution is broader than measured.
Changes adopted (option A by review - honest pilot, 30-45 physical attempts):

1. **The single main subject for motor policy is cube.** Candy and paste remain for recognition (E4)
   and no action (E6): "I know the cube, I take it; the candy/paste on-board detector doesn't recognize the call SAM 3.
2. **The main E5 metric is a self-contained robot success**, not offline error (it's just phase diagnostics).
   Comparison: T0 and T1 at k = 5 and k = 20, 10 identical pre-set scenes, blocks mixed (40 attempts).
   The in-box is: k=5; the pre-selected subset k=20, which is the same for all methods.
   T2 (So-101 donor) is a preliminary result, as long as there is no tested package reproduced in ROSMASTER mechanics;
   When the donor is concluded, it is mandatory to monitor the equal amount of synthetic data of the teacher.
3. **Statistics:** Results table, fractional difference, truthfully stated power.
   One primary contrast (T1 vs T0 at k=5); the rest is exploratory. E3+ is corrected: steam test for
   The new pre-recorded seeds (old 10,000–10019 became diagnostics).
4. **E6 – Shadow mode at E5 attempts:** before every attempt, the decision "brew/needs help" is retained, then
   It's compared to the outcome.
   Plus "sympathetic but difficult" (bench reach) and "new but achievable".
5. **E3 first diagnostics, then new models:** replay recorded commands at MuJoCo; overfit 3–5 scenes;
   Data semantics verification (cam, joint order, unit, claw, normation); horizontal comparison
   implementation 1/5/10/100 On the finished checkpoint; phase errors on all 20 scenes.
6. **E1:** Add "best fixed assistant", "accident assistant", "always," oracle; new 100+ rooms.
7. **E2:** The phrase "sock is the low reliability of this controller" (not "not" takes over) and the factor size of × yaw.
8. **E4:** pre-recorded prompts and synonyms, 10-20 personnel without target and similar objects,
   Comparison of YOLOE-only / SAM-always / selictive; marking is not the same model.
9. Checked 20.11: in the field, the command is written **after IK and restrictions** (arm_barget in force for the following:
   The intention of Leader and the actually directed team are written separately.
10. Cut to endline: comparison of architecture (ACT /SmolVLA/Diffusion/ pi0), video from the phone, Tank-tasks,
    Human transmission, LLM controller as the main method.

Working title: *Explorer 4.0: Selective Knowledge Reuse for Data-Efficient Learning in Heterogeneous Robot Teams*
(If no savings are confirmed – An Emerical Study of Knowledge Reuse in Low-Cost Heterogeneous Robotts*).

## 8. Record 20.11 - Session sheet (~60 min)

Preparation: ROSMASTER on the tape under the wheels (not to move the entire session).
**Backpoint O 21 cm in front of the centre of the base of the arm**. x - forward of O, y - left of O (see), yaw - turning
The cube is relative to the front edge of the robot (the cube is symmetric in 90°, so 0 /30/60).

| Series (description)| Appointment| How many|
|---|---|---|
| `cube, диагностика` | Checking the record, auditing immediately| 2 |
| `cube, обучение` | k = 20 (input k = 5: No.1, 4, 7, 10, 13)| 15 |
| `cube, исправления` | Recovery after failure| 5 |
| `cube, отложенные` | Independent verification, not in training| 5 |

Training (x, y, yaw):
1 (0,0,0) · 2 (+4,0,30) · 3 (−4,0,60) · 4 (0,+6,0) · 5 (0,−6,30) · 6 (+4,+6,60) · 7 (+4,−6,0) · 8 (−4,+6,30) ·
9 (−4,−6,60) · 10 (0,0,60) · 11 (+4,0,0) · 12 (−4,0,30) · 13 (0,+6,60) · 14 (0,−6,0) · 15 (+4,+6,30)

Corrections (intentionally bring the claw 2-3 cm past, see the gaps in the cell, pull, squeeze, lift;
  or close off target, reopen and try again. Positions: 1 (0,0,0), approach from the left; 2 (+4,−6,30), approach from the right; 3 (−4,+6,60), undershoot.
4 (0,-6.0) Flight 5 (+4,+6,30) past disclosure and repetition

Postponed (between grid points): 1 (+2, +3,15) · 2 (-2 -3,45) · 3 (+2, -3,75) · 4 (-2, +3,15) · 5 (0, +3,45)

Each display: Start with the same folded position with the cube in the camera frame of the hand ♪ Record immediately ♪
lower, squeeze, lift ≥ 5 cm, hold 2 with ≤ F10. Failure is F11, repeat the same position.
So-101 donors are not writing today (reveal only after a tested package).

## 9. Achieved by a no-bot review (20 - 21.11.2026)

| Point by review| What's done?| Result| File|
|---|---|---|---|
| E3: Repeat recorded commands| 40 learning scenes v4 lost without model on the same seed| **40 /40 success**; colors not mixed, starting position coincides, command is ahead of 3–4 steps.| `docs/results/e3_diagnostics/replay_40.json` |
| E3: error phases| Steps (CT and SmolVLA)| The claw is compressed in time (~100 step as a teacher) but 2.5–5.5 cm from the subject: traffic has been learned, the object has not been studied| `act_v4_phases.json`, `smolvla_v4_knowledge_phases.json` |
| E3: Performance horizon| Same ACT weights, replanning every 10 / 25 / 1 steps instead of 100| n=100 (constant): 1 /20; n=25: 3 /20; n=10:0 /20; n=1: 0 /20 is not a cause (dissisting within noise)| `DATA/diagnosis/e3_horizon_act` |
| E3: 3–5 scene memory| Training on 6 scenes with the same ACT test| Waiting for a noisy study permit (~2 (c) | `scripts/e3_overfit.py` |
| Error budget: time| 14 real ROSMASTER shows| 41 ms (p95 78), 66 ms (p95 109), **5 steps (250 ms) behind team, 3–4 (150–200 ms)**: simulation difference, factored in transport; tracking error 0.3–2° (p95 to 4°, claw to 10°)| `docs/results/latency_budget/summary.json` |
| E2: size × bend| 120 scenes x 4 conditions, added "dimension + compression direction of its chamber (| Short objects: without knowledge 60 /82, size 58 /82, **dimension + direction 74 /82 ** (p = 0.0025), full knowledge 75 /82; wide 1 /38 everywhere - claw limit| `docs/results/knowledge_transfer_mujoco_v3/ANALYSIS.md` |
| E1: Baseline lines| Added K5 "always call everyone", rooms with pre-known "where"/ "how"/both, calculation of oracle/random/best fixed| sample: all known ♪ K3 no one, 78 s; K5 calls both, 151 s.| `scripts/knowledge_gap_experiment.py --priors` |
| k = 0 | Added to final evaluation| T1, T2 on a cube without ROSMASTER| Protocol, step 5|
| E4: Negatives| "empty floor/outside/all three" personnel in phase 0| I'll take it off myself, ~2 mines| `scripts/grab_frames.py` |
| ROSMASTER installation| File reconciliation, backup copy, agent restart, error reset| Waiting for the robot to turn on.| `scripts/deploy_rosmaster_agent.py` |

Not yet done: decision "take/call for help" before each attempt (up to stage 5 with launch)
The following are the following:
Co-education, updating the package for the inspection.
