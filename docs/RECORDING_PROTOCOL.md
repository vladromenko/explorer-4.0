# Recording and verification protocol — full scope of research

Version 20.11.2026, after independent review. Related documents: [RESEARCH_PLAN.md](RESEARCH_PLAN.md) (what and why)
[REVIEW_PACKET.md](REVIEW_PACKET.md) (techniques and criteria).

**Primary rule: steps are in turn, each is followed by a "gate" — a check that is appropriate.**
If the gate is not passed, we don't write down any more, but we fix the reason, and the records already taken are not missing.
This excludes the situation "for 100 videos, and they are useless".

---

## Common rules for all ROSMASTER records

**Place (really assembled once and not changed until the end of all phases):**
- ROSMASTER stands in one place: the wheel contour is scotched. If the robot is moved, it is placed exactly in the contour.
- **O** is a scotch cross on the floor, with a side of the foot of the foot, and a cross of the floor of the hand, with a cross of the head of the robot.
- The object coordinates: **x**is the forward of O (+ further from the robot),**y** is the left of O (in terms of the robot), in cm.
  **Yaw** is the turning of an object relative to the front edge of the robot, in degrees (for long objects, the angle of the long side).
- Lighting: The upper light is on, the curtains are as usual. Do not change between the stages of one object.
- There are no foreign objects in the zone 50 x 50 cm around O (except for stage 6, where this is specifically assigned).

**One display:**
1. ROSMASTER's hand in **start position** (Button/Back-up): the hand camera looks down, the object is all in frame.
2. The object is placed in the specified position (x, y, yaw) by the line O.
3. "Listen" (F9) is a long-term one.
4. Lead hand: lower, squeeze, **lift ≥ 5 cm, hold 2 c**. One understandable approach; natural pace.
5. F10 "Acceptance." If the object fell/not taken - F11, then **repeat the same position**.
6. No wheels.

**Series title** (Place "Description" in "Next Position": `<предмет>, <назначение>`
The subject matter is one English word: `cube`, `candy`, `toothpaste`. Example: `cube, обучение`.

**What I do after every series (5 minutes while you rest):** audit (passes ≤ 200 ms, sync, coincidence)
The point is that the object is found on the first frame, the rise of ≥ 5 cm is confirmed by the joints, and the position is the one that was set.
Episodes that have not been tested are re-scheduled ** in the same position.

---

## Provisions grids

**Learning (15):** (x, y, yaw)
1 (0,0,0) · 2 (+4,0,30) · 3 (−4,0,60) · 4 (0,+6,0) · 5 (0,−6,30) · 6 (+4,+6,60) · 7 (+4,−6,0) · 8 (−4,+6,30) ·
9 (−4,−6,60) · 10 (0,0,60) · 11 (+4,0,0) · 12 (−4,0,30) · 13 (0,+6,60) · 14 (0,−6,0) · 15 (+4,+6,30)
The attached kset is 5: No.1, 4, 7, 10, 13 (one for all methods). For the cube yaw 0 /30/60 (the cube is symmetric in 90 degrees);
for outstretched items yaw 0 /60/120.

**Checks (5):** The claw is deliberately set to 2-3 cm past, see in cell, pull, pull up, lift.
1 (0.0.0) left-hand misses · 2 (+4, -6.30) right-hand misses · 3 (-4, +6,60) short-range · 4 (0, -6.0) flight ·
5 (+4, + 6.30) press past ~ open ~ take.

**Postponed (5), not enrolled):** 1 (+2, +3,15) · 2 (2-3,45) · 3 (+2, -3,75) · 4 (-2, +3,15) · 5 (0,+3,45)

**Pilots (5 for robot phase 2 testing; not used in final evaluation):**
1 (+3,−4,10) · 2 (−3,+4,50) · 3 (+1,+5,20) · 4 (−1,−5,40) · 5 (+3,+2,70)

**Total evaluation (10 fixed in advance, no longer used):**
1 (0,−3,20) · 2 (+3,0,40) · 3 (−3,+5,10) · 4 (+2,+5,50) · 5 (−2,−5,25) · 6 (+4,−3,55) · 7 (−4,+2,35) ·
8 (+1,−6,5) · 9 (−1,+3,65) · 10 (+3,+4,15)

---

## Step 0: Checking the record today, 10 minutes
- I'm putting on ROSMASTER timeout Leader 1 s (in your "ok" before the record begins; the hand is down).
- You are: `cube, диагностика`, 2 demonstrations in Educational Status No. 1.
- E4 personnel (the detector must not "find" an item that is not available; ~2 mines, arm in starting position, I remove
  Hand cam footage: 3 frames, empty floor; 3 frames, foreign objects only (tyre, wiener, etc.)
  The three frames are a cube + candy + paste together in Zone O.
- **Book 0:** both episodes without passes > 200 ms, camera continuous, cube found on the first frame.
  I'm not getting through the record, we're going to repeat the step 0.

## Step 1: Cube today, ~60 mines
- `cube, обучение` is 15 in the education grid.
- `cube, исправления` — 5.
- `cube, отложенные` — 5.
- **Gate 1:** >15 trainees + 5 postponed have been audited, all provisions covered.

## Step 2: Training pilot - without you (night) + ~15 mines with you
This is the main protection against "all crap" -- before we record the rest of the items, we check that the records are actually being seized.
- I teach T0 (only cube, k = 20) and T1 (start with ACT, trained on 200 scenes in MuJoCo) at night after your "may make noise."
  In parallel, the diagnostics are from the re-hearsal of the recorded commands, re-learning on 3–5 scenes, and checking the semantics of the data.
- You: 5 pilot attempts of each model (10 attempts, ~15 mines), I'm right here, stop at first request.
- **Book 2:** At least one model takes a cube or misses ≤ 1–2 cm in pilot positions.
  I'm not going through the. I'm going through the method (geometrics of the object at the entrance of the model, performance horizon) and I'm repeating the pilot on the same notes**.
  No new records.

## Step 3: Donor SO-101 - ~1 h (pre-stage scoring instruction)
It is necessary that the transfer of SO-101 \ROSMASTER be verified, not "in-eye".
- Dummy measurements (~30 min): claw contact point (TCP), sponge opening curve in mm, C920 chamber delay,
  3 reference points not used for fitment.
- The donor shows are `cube` +2 (total 5), `candy` 5, `toothpaste` 5. Command: take, lift ≥5 cm, hold 2 s, return.
- **Book 3:** The experience package is collected and reproduced in the ROSMASTER mechanics in MuJoCo (reception and retention).
  The T2 is still preliminary, the 4-7 steps are continuing.

## Step 4: ROSMASTER candy and paste - ~1, 5 h
Only after gate 2 (the method is taught).
- For each object: `candy, обучение` 15 + `candy, исправления` 3 + `candy, отложенные` 5; same for `toothpaste`.
  The grids are the same (yaw 0 /60/120).
- Same objects as before: Snickers mini bar, R.O.C.S.
- **Gate 4:** as gate 1 for each object.

## Step 5: robot final evaluation - 2 sessions on ~1, 5 h
- Models: T0, T1, T2 × k = 5 and 20 (cubic); T0, T1, T2 × k = 20 (confection, pasta).
  T2 synthetic data plus **k = 0** (net transport without showing ROSMASTER): T1 and T2 on a cube -
  Ten attempts each; shows how much transport itself gives to the first human display.
- Each model is 10 final clauses; the order of the models is mixed by blocks; and the same for all models.
- Before each attempt, the robot retains the decision "the beer itself / needs help (what is the gap)" for E6.
- Success: raised ≥ 5 cm and retained 2 s; video decision is made by a gauge that does not see the model name.

## Step 6: "Acknows what he doesn't know" - ~30 mines
Each situation is three attempts, the robot first announces the decision, then (if safe) tries:
- New object, **nowhere previously unrecorded** (choice now and remove: e.g. mandarin or sponge);
- cube at and outside the edge of reach (x = +9) (x = +15);
- A cube half covered with paper;
- The object of the wider opening of the claw (e.g. the circle) is "physically impossible";
- A model with only a cube.

## Step 7: Full "Bring" mission - ~1, 5 h
- 10 runs with poi (Tank is looking for, SO-101 merit, SAM 3 finds out, ROSMASTER takes and puts in a square of 40 x 40 cm)
  And 10 without help, same locations, mixed order, time, intervention, outcome.

---

## Human time outcome
| Phase| Time|
|---|---|
| 0–1 | ~1 (Today) |
| 2 | ~15 min|
| 3 | ~1 h|
| 4 | ~1,5 h|
| 5 | ~3 2 sessions|
| 6 | ~30 min|
| 7 | ~1,5 h|
| **Total**| **~9 h**, ready; nights Jetson between stages 1|

Outside this article (selected work): Handing over the object to the person (block 4), the place of transmission, the Tank dataset,
Video training from the phone.
