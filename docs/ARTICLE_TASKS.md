# The article's mission is to show, learn, experiment

Orders upstairs. Details of the recording in [DATASET_RECORDING.md](DATASET_RECORDING.md), the route "MuJoCo ♪ robot" in [SIM_TO_REAL.md](SIM_TO_REAL.md). Everything is made of a browser, terminal needs to be done once on Mac.

**Working title of article:** "A range of diverse robots with a common map and memory of assistance aligned with the recipient's skills".

**Order for the second audit:** First experiment A is a search by one robot versus two (most ready, no hands required)./M2/M3.

**What is measured in it:**
1. Team wins on a single robot: inspection, search, bring.
2. Hand training at the show, including with the MuJoCo shows, and their transfer to the robot.
3. The benefit of the memory of the help that checks compatibility with the recipient's skill is M3 vs. M2 and M0.

---

## Step 0: once (E30 min)

| # | What| How| Ready when|
|---|---|---|---|
| 0.1 | Mark on Mac| In Terminal: `curl -s http://192.168.0.168:8000/mac/install.sh \| bash` | There's a Robota on the desk, the menu opens.|
| 0.2 | Charging| Tank and ROSMASTER are fully charged. Tank from the couch or table do not start| — |
| 0.3 | Transfer area| Box or stand at SO-101, corners marked with scotch. ROSMASTER should reach it with his hand (to ~25 cm from the center, low)| — |
| 0.4 | Transmission locations| "Roy" ♪ "Message" ♪: place and position for ROSMASTER, 5 SO-101 lead hand| "Message" sign on Roy Green|
| 0.5 | Marks on the floor| Scotch two robot startups and 10 items| — |

---

## Step 1: Shows (E7h, 2-3 days)

Record arm tasks before approach tasks.

| Block| Task at the Dataset Collection| Norma| Time| What for?|
|---|---|---|---|---|
| **3** | ROSMASTER · take from the floor`rosmaster_pick_place`) Description to start with `взять с пола: …` | 10 stations x 5 = **50**| 1.5 h| The trained capture of ROSMASTER, without it, "bring" does not work on any subject|
| **4** | SO-101 · gear (`so101_pick_place`) Description to start with `передача: …`| 10 × 5 = **50** | 1.5 h| Trained Human Transfer|
| 1 | Tank · access (`tank_dock_rgbd_lidar`)| 4 × 5 = 20 | 25 minutes| Calibration of Tank in MuJoCo, comparing "man versus planner"|
| 2 | ROSMASTER · approach (`rosmaster_dock_rgbd_lidar`)| 4 × 5 = 20 | 25 minutes| Same for ROSMASTER|

**Rules on which education depends:**
- **Items.** Scratch the cube, cookies, bottles and socks, each in two to three positions. `pick up the cookie`.
- The same old position.** ROSMASTER is a view position, SO-101 is a loose-to-open-to-take model.
- **Failure to delete.** Failure to mark F11 and not delete: this is also data.
- - No. - No.
- **Check.** At the end of the day, watch 1–2 videos in each series, the bad ones delete the button.

---

## Step 2: Training (4 nights, without you)

Everything in the Learning tab is done in the background.

| # | Action| When| Time|
|---|---|---|---|
| 2.1 | "Call MuJoCo under My Show" button: The MuJoCo scene is being brought up to your location on blocks 3 to 4 and immediately collects 70 expert shows per arm| after ≥5 success in each block, better after all 50| ~1 h|
| 2.2 | ROSMASTER, task `rosmaster_pick_place`: Checkbox "Add MuJoCo" then **"SmolVLA · Basic education"**| Night 1| ~9 h|
| 2.3 | Same task, main ACT training for the baseline comparison | Night 2 | ~11 h |
| 2.4 | SO-101, task `so101_pick_place`: SmolVLA with MuJoCo| night 3| ~9 h|
| 2.5 | SO-101: ACT | night 4| ~11 h|
| 2.6 | **/ For the article:** ACT ROSMASTER only in the present shows (both ticks removed), then separately "Start with MuJoCo weights" and separately "Add MuJoCo shows" are three versions of B1 /B2/B3 in the same shows.| Nights 5 - 6| ~11 h each|

After each training, select a row and press **"Absorbsorbs to the robot"**. The column will show "Absent" or "not allowed" with cause.

---

## Step 3: Testing of trained robot models (E2h)

Only for models with "permissible" status.

| # | What| How many| Measured|
|---|---|---|---|
| 3.1 | "Prepare the checkpoint test" ♪ "Stop the permitted test", ROSMASTER takes an object from the floor.| 15 per model (SmolVLA, ACT, SmolVLA without MuJoCo)| success, time, intervention|
| 3.2 | Same for SO-101| 15 per model| same|
| 3.3 | Geometric capture without training, by comparison: "come to...", then "bring"| 15 | same|

The rule is:** press STOP only in the event of real danger.

---

## Step 3a. Experiment A: Search by One Robot versus Two (Pilot E2h, before hands)

"Roy". "Research experiment." One category of object that SAM 3 is sure to find (cubic). 6-10 sets, each ID (S01...S10), photo and mark the actual location. Each location passes A1, A2 and A3 in a pre-mixed order. Before each attempt: "start the map again", robots on start marks, time T=180 s. After trying to cross-check the find with the mark and press "reliable / error / not found", specify interventions.

## Step 4: Roy on real robots (E3h, block 5 of the instructions)

The trained capture will connect to the piano itself as soon as the clearance passes.

| # | Command| Modes| How many| Before each run|
|---|---|---|---|---|
| 4.1 | "see the room"| both / ROSMASTER only| 10 + 10 | "Start the map again", robots on start marks|
| 4.2 | "find <items>"| both / ROSMASTER only| 10 + 10 | "Start the map again" (wiring and objects), object hidden in a new place|
| 4.3 | "Bring up <items>"| both| 20 | 10 with a familiar map and 10 after card release|
| 4.4 | "bring..." and after you see the object, you put it quietly elsewhere outside the field of sight.| both| 10 | Checking aid between robots on real iron|

The numbers are written themselves: the main page, "Slip Table (CSV)". The memory of the aid is on "Roy".

---

## Step 5: Experiments in simulations (without you)

| # | What| How| Time| Status|
|---|---|---|---|---|
| 5.1 | Benchmark piano: 30 rooms x single / pair / three x inspection / search| Ready.| — | `docs/results/fleet_benchmark_run30_v4`: pair x1.67 / x1.64, three x 1.75 / x 3.86, zero collisions|
| 5.2 | Help M0 / M2 / M3, 30 pair virtual rooms| "Learning" ♪ "Acception (simulation)" ♪| ~10 h| start|
| 5.3 | Transfer from MuJoCo to robot: tolerance and testing of the MuJoCo and without| from 2 to 3| — | After the show|

---

## Step 6: What I'll prepare for the article when the data is available

1. **Tables and graphs** 95 per cent intervals as for the benchmarking (`scripts/benchmark_stats.py`): Roy, trained skills, help.
2. **Dataset to publication:** LeRobot display unloading, dateset card (bots, tasks, layouts, license), without unnecessary personal data.
3. **Text of methods:** Common map, agents, robot access, co-education, experimental protocol.

---

## Summary

| Phase| Your time.| Time without you|
|---|---|---|
| 0. Training| 30 minutes| — |
| 1. Shows| ~7 h| — |
| 2. Training| 4 - 5 presses| ~50 h (5 nights)|
| 3. Tests| ~2 h| — |
| 4. Roy.| ~3 h| — |
| 5. Simulation| 1 press| ~10 h|
| **Total**| **~13 hour in ~1 -1.5 weeks**| |

## Known limitations to be described in the article

- **Tank doesn't always find himself in the common map.** His lidar is lower than ROSMASTER and sees other objects. Until he learns the common map, he works his own way.
- **The capture of ROSMASTER without training is unreliable.** The camera is set at 3–6 mm by 16 cm, but at the floor 2–5 cm. Therefore, the main route is a trained seizure (block 3).
- **Tank engine charges do not have independent hardware stops** when USB is lost. Software protection: zero on return, 25 cm stop in stand-alone sessions, no driving without fresh lidar.
