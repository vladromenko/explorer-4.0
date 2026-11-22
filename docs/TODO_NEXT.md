# What to Do — November 16, 2026

Current summary: [CURRENT_STATUS.md](../CURRENT_STATUS.md). Main assignment: [ON_DEMAND_SKILL_TRANSFER.md](handoffs/ON_DEMAND_SKILL_TRANSFER.md). Previous timeline and teams performed are saved in Git.

## Ready.

- K0-K4: All 50 runs and baseline protocols published; results 3, 2, 9, 10, 8 successes out of 10.K4: 1 time-out, 1 failure, zero technical errors.
- MuJoCo K v2: 180 runs, 44 /60 with full information, 34 /60 with no size, 35 /60 with dimensions. The 80 per cent threshold is not confirmed on all forms.
- The v3 pair with the size inside the class; the first actual pair and reading of both sets were passed.
- Query skills, packages, transfer to ROSMASTER, origin, line/end and interface are connected to existing components.
- The real geometry SO-101 is recorded in a separate setting; the package is collected only after verification of independent measurements.
- The final area is selected by the owner through the delegation: a separate square of 40 x 40 cm on the free floor next to the rebound. In 2D, the free space is chosen 70 cm from the original object. These are not the coordinates of the real room.

## Now: Programmatic work on Homebrain

1. The small set is ready: six pairs of seeds 50000–50005, both sides of readback PASS, group 4 /1/1 coincides.
2. The technical SmolVLA run is complete: 50 updates, batch 8, seed 1000; checkpoint /reload/validation is passed. The Cgroup peak 6 GiB, swap 0.45 GiB, minimum MemAvailable 7.05 GiB, without OOM. This is not the result of acquiring skill; these six pairs and weights are excluded from the complete comparison.
3. After a successful run, collect 200 successful pairs. Four hard classes are suitable for learning: cube, box, ball; cookie/sock The following are the most recent attempts: the first 200 successful pairs./knowledge-policy-v3.json. New dimensions of one class are mandatory.
4. Freeze the same groups train /validation/test for both textual instructions; the raw frames and the actions of the pair are identical. The only standard is train. Record the same reference weights, 12000 updates and actual batch.
5. To consistently train two SmolVLAs and to evaluate through the existing ringime /MuJoCo on the same new scenes. To check the actual text of the tasks, reports, losses/benefits and costs. Not to consider ACT as a linguistic comparison.
6. Publish completed results and interpretation, including negative results, and leave the finals on "process started".

An example of a guy trying from the root of the project:
```sh
MUJOCO_GL=egl .venv-sim/bin/python -m explorer4.sim.paired_capture --seed 50000 --output ~/.local/share/explorer3/runs/knowledge-policy-v3-20261116/50000.json --external-spool
```
The command repeats the final attempt. Start inside the compute /physical-activity options and limited scope, one by one. The complete old sim_rehearsal is not used for a pair comparison: it collects options independently.

The complete run is used by /knowledge_paired_training.py collect, then the same script train.
He checks frozen reference frames/base weights, uses the existing Jobs line and limited processes. The DATA /runs/knowledge-policy-v3-20261116/full/pause file stops the collection between attempts or between assignments; the already ongoing learning is cancelled by the previous Jobs button. The status/value/all outcomes are retained there. The technical error stops the series; there is no automatic budget increase.

## Need for ownership: only SO-101

Three diagnostics are requested in the chat room for the right time.

1. On the existing /recording/collect page, open "So-101 to transfer capture." ArUco No. 7 is placed at the centre of the cube; measure the black square after the seal and three dimensions of the cube.
2. Save geometry settings and prepare a separate series of donor captures. Command: take a cube, lift ≥ 5 cm, hold 2 s, return it to the table. Do not indicate this as a transmission to a person or the previous complete task "in a box".
3. The owner performs three hand-held shows through the previous Leader /Follower control; clearly starts/ends each and notes the outcome. Nothing is automatically launched.
4. Then check the record and phase boundaries. For a real package, you need a measured contact TCP, a metric sponge curve, a delay in the camera and at least three independent control points/openings not used for the fit. Unknown numbers do not be made up.

Collector: Scripts /build_so101_skill_packet.py --episode ID --review PATH. Review should refer to actual checked files/heshes. Synthetic test locks and old nominal calibration do not replace the current check.

## First result T and continuation

- Accept one tested real SO-101 package, perform your own rollout ROSMASTER in MuJoCo, save source/produce/all failures. The success of the prototype with simulation donor does not close this paragraph.
- Then prepare a specific T1 /T2 at one non-zero k. The same k shows, the same generation budget, sensors, number of updates and reference weights. The allowed options k=0 /5/10/20; 50 self shows are super-data baseline, not hidden mandatory entry.
- Finalize the preparation of small budgets in existing datasets /training_drafts: precise number of tran-shows, separately calibrating /test/, grouping all derivatives and counting human time/calculations. Do not launch a new heavy T-learning until a specific plan is agreed upon after the first transfer.
- Train the recipient's own policy and check the repeat on independent terms without online help SO-101 and geometric correction. T0 /T3 expands only after limited T1 /T2.
- For physical ROSMASTER: independent visual lift/retention, shadow, separate limited test with owner and exact weights, then recording the area of skill.
- For the full mission: measured coordinates of the final zone/posting and independent observer. The clear continuation of the protected target shall check the fresh stage, charge and resolution. After the restart and completion of the training, traffic is prohibited.
- Tank is connected after separate checks. Independent stopover at USB break is a hardware task; dangerous refusal to check. Return of the regular control is an existing way.

## Permanent restrictions

All performance/data on Homebrain, Mac is only a console. Disable minor verified changes. Do not touch Wristlab:8020, so101_autonomus_pick_place:8010, Console8090, CubeBot, embroidery and motor calibration. Do not create a second dispatcher, trainer or motor manager. Movements only after a specific current permit of the owner nearby; mobile robots must be disabled from charging before doing so.

Update this report, CURRENT_STATUS.md and RESEARCH_ROOT.md; do not finish obsolete commands at the end. The main current real transfer block is the lack of a suitable donor display, not the number of program tests.

## 16.11, 12:20 - K v4 launched (night)
- Diagnostic v3 (0 /20): model closed lips 3 - 11 cm from object; in starting position (beat 25°)
  The object was in the arm frame of 0 /30 scenes, the model could not target. The teacher took it because he knew the situation from the simulation.
  Outcome: `~/.local/share/explorer3/diagnosis/knowledge_0425eff7/summary.json`.
- v4: Start position of wrist -15° (showed 30 /30), teacher 18 /20. Protocol `configs/knowledge-policy-v4.json`.
  Chain: collection of 200 pairs (~2.6(h) ♪ SmolVLA with knowledge ♪ 20 scenes ♪ SmolVLA without knowledge ♪ evaluation ♪
  Status: `~/.local/share/explorer3/runs/knowledge-policy-v3-20261116/full-v4-lookpose/state.json`, log `../run_v4.log`.
  Pause between stages: `touch …/full-v4-lookpose/pause`.
- Control training v3 (uninformed, job 9b28bb8a) is stopped by the owner by 31%.
- It's important for real block 3: to start the recording in the position where the object is seen by the hand camera.

## 16.11, 23:05 – Outcome K v4 and Night ACT
- K v4 (SmolVLA, 12000 vol., package 8 = 2.8 eras): with knowledge of 2 /20, without knowledge of 0 /20, teacher 18 /20.
  Diagnostic (`~/.local/share/explorer3/diagnosis/v4_knowledge/summary.json`): motion and compression moment as y
  The teacher (~step 100) but the sponges close at three to six centimetres from the subject and repeat no ~ lack of education/precision.
- By night: ACT on the same 200 pairs (no knowledge profile), 30,000 nb, package 16 (`scripts/act_floor_pick.py`,
  `runs/knowledge-policy-v3-20261116/act-v4/state.json`, ~11.5 hours + 20 scene evaluation)
  If the ACT \SmolVLA is sufficient, the ACT/longer is needed; the knowledge for the ACT is given by a dimensional vector in the state.
- `DATA/configs/training.json`: number_workers (1) and memory_limit_mib (8192). 2–4 flow: OOM/swap, speed does not increase (GPU-bound).
- 16.11: SO-101 donor 3 /3 success (AprilTag 36h11 No.1, rise 7–17 cm C920).
  ROSMASTER block 3: 0 demonstrations — mirror carries angles 1:1, SO-101 posts the shoulder/lox of ROSMASTER
  A pair of "snatch SO-101 on table ♪ grab ROSMASTER on the floor" is needed.
  (IK ROSMASTER x = 0.20 m: [90.16.9.85.90]; Leader joints when seized ER [15, 13,51.40,-54]) or
  Decarto mirror. Amended: Round(None) in agent magazine; claw in mirror to gripper_hold_max (165).

## 17.11, 21.10 – ACT pairs v4
- ACT, 30,000, 16 (14.2 Episodes, loss 0.069), without knowledge: **1 /20 ** (seed 10,000), 19 - Time Out.
  Comparison on the same scenes: SmolVLA with knowledge of 2 /20, without knowledge of 0 /20, teacher 18 /20.
- Diagnostics (`~/.local/share/explorer3/diagnosis/act_v4/summary.json`, seeds 10001–10003): sponges are closed
  At the same time, the ~100 (as a teacher step 101) is 3.3–4.7 cm from the subject, no rise, no repetition.
- Conclusion: The "negative" hypothesis was not confirmed (5x more learning - same failure).
  The average time trajectory is not targeted, but the teacher's data do not contain any correction of the miss.
- Next (one at a time, cheap first): (1) check whether the position of the object in the hand frame is visible/distinguishable at the moment
  The approach and the extent to which the object is scattered in data; (2) DAgger: the teacher corrects from the state to which the object is located
  hands control back to the policy after a miss and re-approach, one or two rounds. (3) Add the overview camera or object position to the state.
