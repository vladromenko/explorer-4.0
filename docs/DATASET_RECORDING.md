# What and how to write for the Excel 4.0 dateset

Only six blocks, blocks 1 to 4, are human displays, and they are taught skills (ACT), and block 5 is autonomous piano runs, which are numbers for article 6. Block 6 is inspection and unloading.
Order is important: first, units 3 and 4 (hands), which are the weakest parts of the automatic.

---

## 0. Preparation (every day of recording, ~10 mines)

1. Turn on ROSMASTER, Tank and SO-101 (with the lead hand). On Mac, open Homebrain and press "Stop" at Explorer 4.0.
2. Open the Explorer, then **"Purity of the Park"**. All robots must be green. If not, you can't write first.
3. **The same set of objects.** The same set of items all day, ROSMASTER takes objects 3–8 cm wide:
   - Cube 4 - 5 cm;
   - Cookies in the package;
   - small bottle or bottle;
   - A sock wrapped in a lump;
   - The circle (only for search, not for capture).
4. The box or the set at SO-101, don't change all the days of the recording.
5. * Lighting** is a regular room, if it's light in the afternoon and dark in the evening, write it both times, not in a row, otherwise the model will not learn in another light.

**How to complete the series form** on the "Datchset Collection" page:
- **Task** — specified in each block.
- **Flows option** for access (blocks 1-2) with `rgbd_lidar`. For arms (3-4 units) with** without lidar: `rosmaster_pick_place` and `so101_pick_place`. SmolVLA learns by cell and joint and you cannot mix options within a task.
- **Operator** - Your name is Latin, the same on all episodes.
- **"What changed in placement"** short and specific, such as `кубик, 2 м слева от двери, робот у дивана`.
- **A robot box** is derived from the description itself, such as `pick up the cookie` or `hand over the cube`. Check that the object is correctly named: by this phrase SmolVLA learns to distinguish objects.
- **Positioning**:
  - New placement for each of the new 10;
  - "Stop the series" if you continue to interrupt.

**Keys during display:**

| Key| Action|
|---|---|
| F9 | Start display|
| F10 | Finish, Success|
| F11 | Finish, fail|
| Space| STOP |

Unfavourable display **//////: Mark F11. This is also data.

---

## 1. Tank · Access to object (E25 min)

**Task:** `Tank · подъезд к цели`, version `tank_dock_rgbd_lidar`.
**Norma:** 4 placements x 5 success shows = 20.
He's not driving on a course of learning policy, but on a map and a planner. These shows are for two things: to bring Tank physics into a simulation under real and to make an article comparing "man versus planner."

**The installation** is a pair of "where the object + where Tank starts." Four different pairs:
- Start at 1 - 3 m from the subject;
- Half the distribution of the object is not direct but side (up to 90 degrees);
- In 1 position between launch and object there is an obstacle (stool, box) which must be bypassed;
- The items are in turn: cube, cookies, bottle, sock.

**One display:**
1. Put Tank on the start of the setup. It looks about the same side in all five displays of this setup, ± 20 degrees.
2. F9.
3. Lead the arrows smoothly, without any jocks: turn to the object, approach, stop the object at the centre, 20–30 cm in front of the face**.
4. Hold it one second, then F10.
5. They hit an object or an obstacle, and they passed by the F11.

The display lasts 10–40 seconds. In between the shows, return Tank to start; do not touch the object.

---

## 2. ROSMASTER · Access to object (E25 min)

**Task:** `ROSMASTER · подъезд к цели`, version `rosmaster_dock_rgbd_lidar`.
**Norma:** 4 x 5 = 20. Installations according to the same rules as Tank (may be the same 4).

The difference is:**you have to stop at the location of the capture --** the objects in the center, 5–10 cm in front of the front edge of the hull.** From here, ROSMASTER's arm is reaching it.
The hand is on the way in the view position, and it's not moving.

---

## 3. ROSMASTER · Take an object from the floor (E1.5h) is the most important block

**Task:** `ROSMASTER · взять с пола (блок 3)`, version ** `rosmaster_pick_place` ** (without lidar).
In the "What has changed" field, ** start with `взять с пола:`, for example `взять с пола: печенье, 7 см впереди, 3 см левее`.
**Norma:** 10 x 5 = 50.

**Positioning** — which object is in front of the robot; robot stands in position; object in zone 5-10 cm in front of the front edge, shift to left or right to 5 cm 10 places: each of the four objects in 2-3 different positions.

**One display** (hand controlled in ROSMASTER panel, which opens at the bottom of the page):
1. Hand in the view, lockdown open.
2. F9.
3. Put your hand above the object, put your hand down, close the capture to the point of the object.
4. Raise your hand in the carry-over position: as a view, but with a closed hold.
5. The object is F10. It's F11.

The display lasts 20–60 seconds. Place the object **in the same place** (scotch mark), return your hand to the view position.

---

> After writing blocks 3 and 4, start `scripts/sim_align.py --apply`: MuJoCo will fit into your configuration. The order from recording to robot is described in [SIM_TO_REAL.md](SIM_TO_REAL.md).

## 4. SO-101 · take from the site and extend to the person (E1.5 h)

**Task:** `SO-101 · передача человеку (блок 4)`.
In the "What has changed" field, start with `передача:`, e.g. `передача: печенье, левый край площадки`.
**Norma:** 10 x 5 = 50.

**Position** which object and where on the site, divide the area into 3×3 zones and use different zones.

**One display** (lead hand):
1. SO-101 in the original position, capture's open.
2. F9.
3. Get down to the subject, take it, lift it up.
4. Push to where the human hand usually stands: always the same point, right of the table at ~30 height.
5. You stay between 1 and 2 seconds and open the hold. The other person takes the object if you're alone, the object falls on the soft.
6. Return to your original position, then F10, dropped to the transmission point, F11.

**Old test records** "cube in box" (SO-101 and ROSMASTER, recorded earlier) before learning delete the button "Expel from learning." Otherwise, the model will mix two different tasks.

---

## 5. Autonomous Roi Runs — Figures for an article (E2 - 3 h, different days)

You don't drive anything here, but you set the stage and you run it, and you write it all yourself into the self-contained epizodes.

**The rule of intervention is:** press "STOP Roy" ** only if the robot is going to hit or fall into something. Each STOP counts as human intervention - one of the metrics of the article. Do not stop the robot "because it is slow."

**One set before block 5**, set the gear position (Roy unit, "Message area", instruction ibid.).

### 5.1. "Look the room" - 10 times "Both robots", 10 times "ROSMASTER only"
1. Before each run, press "Start the map again."
2. Put the robots in the same starting points (scotch marks), Tank and ROSMASTER at different ends of the room.
3. Set up five items from the set. 10 different sets, each used in one run "both" and in one ROSMASTER only.
4. Select mode, press "Look the room" and wait until the bed is "free".

Screen the regimen so that the battery and the time of the day do not distort the comparison: both ♪ one ♪ both ♪...

### 5.2 "Find <items>" — 10 "Both", 10 "ROSMASTER"
1. Before running, press "Start the map again" and "Forget everything" (both buttons in "General robot memory"). Otherwise, robots will find a memory object.
2. Hide one object in a new place: behind a chair, by the wall, under a table.
3. Write `найдите <предмет>` and press "Secure".

### 5.3 Bring <items> 20 times, "Both robot" mode
1. Put the object (cubic, cookie or bottle) in a new place on the floor.
2. In ten runs, the map and memory are old: robots already know the room. In 10 runs, after "Start the map over", they need to find first.
3. Write `принеси <предмет>`. When SO-101 extends the object, take it and press "Pick it up."

---

## 6. After recording (every day, 10 minutes)

1. In each episode, open 1–2 records on the "Datchset Collection" page and watch the video. Bad (shots missing, wrong subject) is "Stop learning."
2. On the main page, click "Slip Table (CSV)" are episodes of piano for the article.
3. Don't remove anything manually from the folders. All lies on Homebrain in `~/.local/share/explorer3/`:
   - `datasets/` shows;
   - `episodes/` is a piano run;
   - `world/` is a map and memory.

## How it's taught
- **Hands (blocks 3-4)**is the basic model**SmolVLA**, the basic model for comparison **ACT**. Both are learning from the same shows.
  1. The training board ♪ Real Shows ♪ task.
  2. Press "SmolVLA · Basic Education": 20,000 steps, about 9:00 on Homebrain, convenient for the night.
  3. Next night, "ACT · Basic education": 40,000 steps, around 11.00 a.m.
  4. Start when the problem is ≥30 successful demonstrations.

  SmolVLA understands a command, for example, "pick up the cookie", so one model takes different objects. ACT can do one task, but very quickly. Comparison of two models is a separate result for an article.
- **Access (blocks 1-2)** is not taught in politics: Roy is a map-driving driver, and is needed for calibration of simulation and comparison.
- **Policy check.** "Prepare the checkpoint test" \" Start the authorized test." This compares "classic versus trained policy."
- **Policies in the roi.** Connect themselves: Once ROSMASTER's hand training has passed "Absorbs to the robot", "Bring" takes the subject instead of geometric capture.
- **The approaches (blocks 1-2)** also adjust the MuJoCo simulation to your robots, which are the source of delays and inertia.

## Time summary

| Block| What| How many| Time|
|---|---|---|---|
| 1 | Tank access| 20 | ~25 min|
| 2 | ROSMASTER approach| 20 | ~25 min|
| 3 | ROSMASTER take from the floor| 50 | ~1.5 h|
| 4 | SO-101 gear| 50 | ~1.5 h|
| 5 | Roy: 20 inspections, 20 searches, 20 "bring"| 60 | ~3 h|
| | **Total**| | **~7 p.m. 2 days** |
