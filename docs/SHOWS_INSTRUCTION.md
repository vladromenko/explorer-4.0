# What to do and what robot

All in the Explorer browser (Mac label "Robots" ♪ Explorer 4 or `http://192.168.0.168:8030` ).
The entry section: **"Campaign of the Dataset"** (`/recording/collect`). Do not remove failures, mark F11: this is also data.
Tank is not needed for the show, so let's get him on charge.

Order is important: first, what research does not work without.

---

## 1. SO-101 (white hand on the table) is a donor experience, with 3 demonstrations of ~20 mines.
Why: Of these shows SO-101 transmits ROSMASTER, ** how to take an object (the main idea of the article).

Training (section **"So-101 Responsive Capture Tests"** on "Datchset Collection" page):
1. Mark: The Cube already has an AprilTag 36h11 No. 1 (black square of the E20 mm) in the field "Metch on the Cube" to choose.
   You don't need to print ArUco No. 7.
2. Enter the dimensions of the cube (width, length, height in mm), note
   "Save upper camera and geometry in the next SO-101 screenings" ♪ Save training."
3. "To complete a series of test seizures."
- The upper chamber C920 and the base SO-101 **don't move**.

Show (Leader's lead hand, Fullover's knowledge repeats), in the panel below or with keys:
F9 "Start Show": take the hold, take the cube, **raise at least 5 cm, hold 2 seconds**,
Return to the table, open the capture of the F10 "Light" (F11 "Bail"). **3 display**, cube each time in a slightly different place.

---

## 2. ROSMASTER – Unit 3 "take off the floor", 50 demonstrations · ~1.5 hour
Why: trained capture of ROSMASTER, without it "bring" finds the object but takes it unreliable.

Task for Dateset Collection: **ROSMASTER · take from the floor** (`rosmaster_pick_place`).
Start with `взять с пола: …`, e.g. `взять с пола: кубик`.

Rules:
- ROSMASTER stands on the floor, with an object **ahead of it 16–26 cm** from the center of the robot (within reach of the arm).
- **New and important:** before each display, put your hand in a position where **the object is visible in the arm window**
  If the object is not in the frame, the model will not be able to target
  (It's the same way that MuJoCo gave me 0 out of 20).
- ROSMASTER controls the lead hand SO-101 (Leader   ♪ ROSMASTER) as before.
- Capture: down, squeeze, ** up 5 plus cf, hold 1-2 s. No wheels.
- The objects are: cube, bottle, brace, ball, alternate; each in two or three positions and bends.
  10 sets x 5 demonstrations = **50**.
- At the end of the day, watch the 1–2 video series, the bad ones delete with the button.

ROSMASTER can stand by the charger if the cable does not interfere with the arm and the camera.

---

## 3. SO-101 is the gear, 1 time · ~10 min
Why: "Bring" is the end of the transfer to you, not "ROSMASTER holds the object."

"Roy" ♪ **"Message"**: place and position for ROSMASTER, then 5 positions for SO-101 by the lead hand
The badge will become green.

---

## 4. SO-101 is a block 4 "transmission to man", 50 demonstrations · ~1.5 ch (may be later)
Objective: **SO-101 · gear** (`so101_pick_place` ), description to start with `передача: …`.
SO-101 takes an object from the site and extends it to you.
10 stations x 5 = 50.

---

## What do I do after your show?
- After paragraph 1: Verification of the geometry of SO-101 ♪ the set of experiences ♪ transfer to ROSMASTER (MuJoCo), comparison
  "learning with SO-101 experience" against "normal" with equal numbers of shows.
- After paragraph 2: training SmolVLA and ACT (at night), "Absolution to the robot", then 15 tests on the present ROSMASTER with you.
- The MuJoCo v4 is currently being experimented with at night (knowledge of size in the task against it), the result of which is in the morning.

## Order for the coming days
| Day| What| Robot| Time|
|---|---|---|---|
| 1 | c. 1 (3 donor) + p.3 (transfer points)| SO-101 | ~30 min|
| 1–2 | (50 seizures from the floor)| ROSMASTER + Leader | ~1.5 h|
| Later| Paragraph 4. (50 gears)| SO-101 | ~1.5 h|
| After training| 15 capture checks, 20 "bring" runs (10 with help, 10 without)| ROSMASTER, Tank | ~2 h|
