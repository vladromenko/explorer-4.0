# Explorer 4.0 is a complete technical upgrade of all machines before recording a dateset.

Date: 14 November 2026. perpetrator: Agent on Homebrain (Jetson Orin NX),
`~/Projects/explorer-4.0`, UI:8030, `~/.local/share/explorer3` data.

## 0. Purpose and how to understand what is ready

User in the morning:
1. includes Homebrain, ROSMASTER, Tank, connects SO-101;
2. Opens one Page "Ready" by Explorer: all green and red
   It says what to do;
3. In 10 to 15 minutes, the robot is briefly tested for "all goes": each
   Direction, discharge, STOP;
4. Opens "Registration of the Dataset", selects the task and writes the show in a row.
   series, metering, checking every record is automatic.

Without the intervention of the agent, manual commands at the terminal, corrections of the JSON files and
This document is the only task.
Part (`SOFTWARE_AUTONOMY_PROMPT.md`, self-contained frame, analysis,
This is not the same as the one on the dataset.

**Tank is driven by sex.** User Decision 14.11.2026: Tank Control
corrected after USB-incident 13.11 (including charge wire), lock
Take off, drive on the floor, and adjust.
automatically, retained and reinforced (Section R2).
All Tank functions are on and set
User: camera (RGB and depth), lidar, IMU, power.
Disables and does not re-install; the challenge is to use them in management,
The following information is available on the web site:

**Work without question to the user.** All decisions taken (Section 5).
No waiting for interim reports: packages are run in a row, total one
(Section 6) Machines: Homebrain, Tank (Pi 5 + Container MentorPi),
ROSMASTER, SO-101 (on Homebrain).

---

## 1. Limitations

- SO-101 /WristLab:8020 and Consol:8090: code, services, data not to change.
  Stop and launch:8020 - only by action of user (knob c)
  The R4 or manual confirmation) is not by the agent himself.
- The agent doesn't send the motion commands himself.
  UI. The agent is authorized:
  - SSH reading;
  - Installation of their agent files on robots;
  - Restarting its services `explorer3-*`;
  - Remove the Tank lockdowns on R2.1 (user decision above).
- Training, fine-tune, model generation not to start.
- No change in the board.
  (starting and stopping only by normal means).
- UI:8030 Do not restart when active control or recording is in place.
  The tests are in an isolated UI of 8035–8039 with temporary `EXPLORER3_DATA`.
  Without the wide `pkill`.
- Git: Only your complete changes, checked diff, without force-push.
  `GH=~/.local/share/explorer3/tools/gh_2.103.3_linux_arm64/bin/gh; GIT_TERMINAL_PROMPT=0 git -c credential.helper= -c credential.helper="!$GH auth git-credential" push -q origin main`.
- No secrets, calibration, weight, video, manufacturers.

---

## 2. What is now found (checked 14.11.2026)

### 2.1. Tolerance labyrinth (principal reason "nothing included")
Movement and recording are allowed to cross a dozen files, some of which are not.
out of date:

| File| Where| What's doing now?|
|---|---|---|
| `configs/workflow.json` `allowed_robots: ["tank"]`, `phase: C_tank_read_only_diagnostics` | Homebrain | `local_work.hardware_allowed` **prohibits ROSMASTER and SO-101**|
| `configs/local-only.json` | Homebrain | Homebrain only mode|
| `configs/so101-external-owner.json` | Homebrain | SO-101: cameras and flyer given:8020, Explorer does not open them|
| `stage-b/c-authorized.json`, no `stage-d-authorized.json`| Homebrain | `control.py` requires a step file for each robot|
| `stage-c-authorization-suspended-incident.json` | Homebrain | Tank suspension|
| `validation/tank-motion-incident.json` | Homebrain | `control.py` prohibits Tank|
| `/home/ubuntu/explorer3/incident-block.json` (in the container MentorPi)| Tank | `motion_permission.require_motion_permission` prohibits movement except 15 min. of the mode of the stand-by|
| `configs/{robot}-hardware-enabled.json` | Homebrain | Individual flags|

### 2.2. Tank
- MentorPi T1, Raspberry Pi 5, RRC Lite (`/dev/ttyACM0`, USB `1a86:55d4`,
  Agent `explorer3-tank-agent.service` (docker exec to container)
  The MentorPi, `/home/ubuntu/explorer3` ) and two sensor monitors are operational;
  The agent is inert when he starts.
- **Speed limits only UI.** `motion_permission.limited_command`
  Unlocked and unmounted returns `v, w` **without restriction**.
  Limit 0.2 m/s and 0.5 rad/s (`BENCH_V/W` ) is a set-up
  `explorer4/control.py:127` for keyboards.
  The other source is not limited to the agent.
- No floating speed: step 0 to maximum.
  13.11. with currents at start-up **not proven** but smooth
  It's cheap to run and reduce that risk.
- If the USB fails, the agent writes `incident-block.json` forever; it can be removed
  It's too hard for a day-to-day job.
- SDK charges are powering, IMU, buttons, gamepad, SBUS.
  No.** You can measure motion on IMU and lidar.
- Observed Pi load: flat range about 5.3 - 5.6.
- Hiwonder instruction (local copy)
  `~/.local/share/explorer3/cache/references/mentorpi-t1-complete/`):
  - **Chapter 3.4** - Zero command mandatory, program closure
    may not stop the chassis; the recommended limits.v... 0.6 m/s
    ♪ ♪ 2 rad/s; control through `/controller/cmd_vel` ♪
  - **Chapter 3.2** - IMU calibration, linear and angular speed
    (`imu_calib.yaml`, `calibrate_params.yaml`) if it moves away;
  - **Chapter 3.3** - `/imu` via `imu_filter.launch.py`; EKF;
  - **Chapter 1.3** - charge below 6.4 V, disabled, regular
    8.4. B 2 A; the payment shall be made using a threshold of 6.9 V;
  - **Chapter 1.3.4** - The gaming of several robots interferes;
  - **Chapter 1.5** - loading of about 1 min, then the ready signal.

### 2.3. ROSMASTER
- The basic office and STOP have been accepted by the user earlier.
- The `*_rgbd_lidar` profile page has not been checked.
- `trial_start` (`static/rosmaster-console.html`) does not transmit `collection`.
  It's about testing politics, but correct it now.
- UI:8030 works on the old 7305589, needs to reset to the HEAD.

### 2.4. SO-101
- The devices are in place (`/api/health`: leader, flyer, wrist percent).
- Explorer doesn't take them because of `so101-external-owner.json`.

### 2.5 Data and disc
- 32 GBs out of 233 are available. Current shows are 1 to 7 MB per episode (RGB).
  `*_rgbd_lidar` is larger: evaluate by test record.
- 4 tasks x 50+ shows are placed, but the reserve is small: we need control.

---

## 3. Work packages

Order: R0  ~ R1 ~ R2 ~ R3 ~ R4 ~ R5 ~ R6 ~ R7 ~ R8 ~ R9. Each package:
code, tests, comms, cannon, `STATE.md` report.

### R0 Test countpoint
- `scripts/run_all_tests.sh`: Main groups (`.venv`, `PYTHONPATH=.` ),
  Sim (`.venv-sim`, `MUJOCO_GL=egl` ), browser (Playwright, isolated port).
  The band is a group of `conftest.py` markers.
- Outcome: Group files, passed /failed, time
  `validation/tests-<дата>.json`.
- **Reception:** 0 file; all 56 files in one group.

### R1. One understandable tolerance for maze
1. New `configs/fleet.json`:
   ```json
   {"version": 1,
    "robots": {
      "so101":    {"enabled": true, "owner": "explorer|legacy_8020"},
      "rosmaster":{"enabled": true},
      "tank":     {"enabled": true, "mode": "floor"}},
    "training_authorized": false,
    "updated_by": "user", "updated_at": "..."}
   ```
2. `explorer4/fleet_config.py` is the only function
   `robot_allowed(robot) -> (bool, reason_ru)`. It is used
   `local_work`, `control.py`, `rosmaster_*`, `hardware.py`, `leader.py`.
   Old file checks, remove them from these locations.
3. Migration `scripts/migrate_permissions.py`:
   - reads old files;
   - ♪ `fleet.json` by user decision ♪ ♪ It's all on, Tank `floor` ♪
     SO-101 `owner` on R4);
   - Moves old files to
     `~/.local/share/explorer3/archive/permissions-<дата>/` with `README.json`
     (from where, why, by whom);
   - I'm not a good guy. He can roll back.
4. Page **"Parries"** (R5) shows `fleet.json` and
   The switch "activate/activate robot." The change is written by `updated_by: user`.
5. **Texts:**
   - Each robot is authorized or prohibited only by `fleet.json`;
   - The reason for the refusal to Russian;
   - migration to copies of a real file set gives the expected
     `fleet.json` and archive;
   - Restarting doesn't break anything.

### R2. Tank: Gender
1. **Freezing** (user-decided):
   - On Tank: move `/home/ubuntu/explorer3/incident-block.json`
     (through `docker exec -u ubuntu MentorPi` ) and `bench-authorized.json`
     `/home/ubuntu/explorer3/archive/<дата>/`;
   - on Homebrain: `validation/tank-motion-incident.json` and
     `stage-c-authorization-suspended-incident.json` is an archive of R1.3.
   - History of the incident (`docs/TANK_INCIDENT.md`,
     `tank-usb-incident-20261113.json` ) stays, finish paragraph
     "14.11. The lock is lifted by the decision of the user; R2 protection. "
2. **Restrictions on the part of agent Tank** (not only UI), in
   `agents/tank/motion_permission.py` or new `agents/tank/limits.py`:
   - limits from `configs/tank-limits.json` to Tank, copy in profile:
     Manual control 0.2 m/s and 0.5 rad/s (as now);
     The policy and any non-manual source shall not exceed 0.3 m/s and 1.0 rad/s;
     absolute ceiling 0.6 m/s and 2.0 rad/s (direction, Chapter 3.4).
     The excess shall be cut off with the record;
   - **float acceleration**: acceleration limitation 0.5 m/s2 and 2 rad/s2
     (parameters in the same file); braking to zero on STOP, TTL and protection -
     **...f., without the ramp;
   - TTL 350 ms without new command \\0 0 (there, save).
3. **Failure of USB - a regular event, not permanent blocking:**
   - `pyudev` or `udevadm monitor` monitor on `1a86:55d4` and recording errors
     (EIO) Response: StOP latch; overopen and re-open when port returns
     Send zeros three times; event in magazine and in UI red cloak
     "The engine board connection has been interrupted at HH:MM:SS. Make sure Tank
     Standing, press "Stop""
   - session is over, the episode is marked `aborted` with cause
     `motor_link_lost`;
   - new session only after "Stop" by user
     No automatic movement.
     After recovery;
   - If in 10 minutes more than 3 refusals are given, UI warning "often refusals"
     USB: Check cable and power," traffic remains available by decision
     User;
   - Failure counters and minimum voltage under load - into metadata
     Each episode and the "Readness" page.
4. **Pi protection, no Wi-Fi and Homebrain:**
   - Lidar: when moving forward, stop if closer than 0.15 m in sector ± 30°;
     Back is similar to the back sector, if any.
     Free side allowed. `tank-limits.json` threshold. Profile
     `tank_dock`, when approaching the target, shall allow access to the zone:
     The threshold is selected so that the stopping zone is below the threshold
     (check on position; if target is closer - separate "target" threshold
     For speed not exceeding 0.1 m/s;
   - IMU: inclination greater than 20°. stop;
   - The voltage below 6.9 V: stop and ban on start (there is).
     Yellow warning "About charge";
   - Every stop with cause goes to UI.
5. **Background manufacturer:**
   - Prior to the session, the agent checks that the full-time application (app auto-start)
     does not keep the charge, and `/controller/cmd_vel`; if held, regular
     stops it in a way from Chapter 3.4 (`~/.stop_ros.sh`) and
     Returns the application control back (there is a button);
   - `/dev/ttyACM0` is only open by our driver (`serial_guard`);
   - The gamepad and SBUS packages are ignored during the active Explorer session and
     are written in a journal (Chapter 1.3.4).
6. **Recording motion measurement** (in `tank_dock_rgbd_lidar` profile):
   - write raw `/imu` (angle speed, acceleration) and scan lidar with
     Time tags (part already exists: check completeness);
   - derivative `yaw_rate_imu` and `forward_displacement_lidar` (comparison)
     (See neighbouring scans in the front sector), `measured_response_kind`
     Write it down; leave the command rating as a separate field;
   - Read-only check `/odom_raw` source (Chapter 3.4,
     `odom_publisher_node.py`, `linear_correction_factor_tank: 0.52` ) and
     Write the output in `docs/TANK.md`.
7. **Salibration (Chapter 3.2)** - Check, not launch:
   - `scripts/tank_calibration_report.py` reads `imu_calib.yaml` and
     `calibrate_params.yaml`, output the values and hashs;
   - "Readability" is a part of the R8 test:
     user passes 1 m forward, IMU agent counts accumulated
     For an integrated angle above 10°, recommend the manufacturer calibration in section 3.2.
     I'm sure you're going to be a good team.
8. **Load Pi and communication:** `scripts/tank_health.py`:
   - CPU, temperature, `vcgencmd get_throttled`;
   - Camera frequency, lidar, IMU;
   - RTT Homebrain ♪ Pi and delay command ♪ payment.
   Red threshold: throttled is not 0, RTT p95 is more than 150 ms, camera is below 10 km/s.
   The result is "Readability." If CPU keeps unnecessary Explorer staff
   knots are a list in the report; do not turn off without the user.
9. **Tank Profiles:** `tank_dock` and `tank_dock_rgbd_lidar` check
   New limits, 20 Hz frequency, new dimension fields.
10. **Techs** (fake serial and ROS as existing Tank tests):
    - The manual command is cut without lock and in mode `floor`
      0.2 /0.5; the policy command is cut to 0.3 /1.0; ceiling 0.6 /2.0;
    - The ramp is respected; STOP, TTL and protection are given zero at once;
    - Simulate the U.S.B. \L.L., zero after port return, episode
      `aborted`, new session only after "Stop"; files of eternal
      No lock-down;
    - A lidar is closer to the threshold as the stop moves, and you can go back;
      The inclination. stop; 6.9 B stop;
    - Gamepad is ignored;
    - The old Tank tests pass (change only the waiting times of lockdown and
      The Committee notes that the State party has not yet submitted its observations on the merits.
11. **Tank:** existing (staging bindle), c
    Responsive copy of the current agent and check the hash.
    Restart `explorer3-tank-agent.service`, agent inert before "Super
    "management."

### R3. ROSMASTER
1. Restart:8030 to the current HEAD only when UI is idle
   (no control, no records, no assignments).
2. `collection` in `trial_start`; in `record_start` make sure that
   The transfer is `collection` and `scene`.
3. Profiles `rosmaster_dock_rgbd_lidar` and `rosmaster_pick_place`: check
   on a fake agent (`scripts/fake_rosmaster_agent.py`) that
   It reads back with all the fields.
4. Base and hand speed limits, if set only to UI, duplicate by
   The ROSMASTER (like R2.2) agent's side.
5. On "Ready" is the charge, fresh flow, delay, arm condition.

### R4. SO-101: Take from the old system and return
1. `fleet.json` `owner` field.
2. Page SO-101 - button **"Take SO-101 to Explorer"**:
   - "Old system:8020 will be stopped before return";
   - Stops **service**:8020 staff (`systemctl --user stop <unit>`;
     The name of the youth is defined by reading, code:8020 not to be touched;
   - Checks that ports and cameras are free;
     `owner: explorer`.
   Button **"Return to:8020"**: closes its devices, starts
   The service checks that:8020 answers, sets `owner: legacy_8020`.
3. Leader is always read when SO-101 is on Explorer./3°
   (`hardware.py:489`).
4. **Texts:** on the fae system and devices - take, return, fail
   at a busy port, no changes to files:8020.

### R5. The "Parcing Readiness" page
One page, update every 2 s, for each robot:
- On the network (ping /SSH), the agent is running, the agent's version is consistent with the repository;
- Tolerance for `fleet.json`;
- charge (voltage, threshold), freshness of the chamber, lidar, IMU, depth, k/s;
- Delayed communication;
- Locking and protection: what worked last and when;
- For Tank: USB today, throttled, temperature;
- For SO-101: owner, Leader in place, calibration found.

Total:
- Disc space (red below 15 GB, not allowed below 8 GB);
- Hour synchronisation (Homebrain ♪ robot shift on `chrony` or by
  Marks; red more than 20 ms);
- active missions.

Every red point has one line, which is to do it, without jargon.
Bottles: "Super control" and "Screen ♪ Everything goes ♪" (R8) on the robot.
The Playwright browser test is on the fairies.

### R6. Dateset collection page
1. Select task (4 profiles and options). For default bases
   `*_rgbd_lidar`, for hand, is normal.
   No: UI doesn't.
2. **Serium without hand-in-hand:** New Series button creates
   `<задача>-s<NN>` and `<задача>-layout<NN>` location. It may be indicated that
   The location repeats the previous one: then the group is in common, and UI writes.
   A short field "what changed in position."
3. The metering:
   - Successful / unsuccessful / interrupted in the series and in total;
   - "To 50: N";
   - Independent groups;
   - Goal 10 series x 5;
   - Average duration;
   - The CD is the only place to show.
4. One display: "Start" ♪ indicator of growing staff for each stream ♪
   "Accept" / "Bad" / "Stop".
   - After saving **automatic**: Rereading record, check
     The flow rate (no pass more than 200 ms, the images match the actions,
     The duration is between 3 and 120 seconds, and the first and last shots.
   - The problem is a yellow cap with a reason and a button called "Stop Learning"
     (without removal).
   - The next "Start" is available as soon as it is saved.
5. Hot Keys: Start / Success / Failure — Separate From Keys
   STOP remains a gap and always a priority.
6. In the metadata of the episode: operator, series, placement, description of the change,
   Start voltage and minimum voltage, communications failure, agent version, profile,
   Speed limits.
7. After each episode, the screen "Look at 1–2 records" with the player.

### R7. Data security
- Back up the SQLite catalogue daily with `sqlite3 .backup` in
  Python is a `sqlite3.Connection.backup`) and a manifesto of the Heshes of the episodes.
- Option to copy new episodes to external disk if connected (wire)
  The user requests the request).
- Protection: the recording does not start with a free space below 8 GB;
  The finale of the episode is the correct end of the episode.
- Test: Backup is recovering, the hens match.

### R8. "All moves" test (user passing)
Walking artist at UI for each robot, about 10 minutes.
What do \ automatic check on the \PASS sensors/FAIL.
The result is in `validation/physical/<робот>-<дата>.json`.
- **Tank:**
  - The charger is off (voltage below 8.3 V and does not increase);
  - forward, backward, left, right 2 s;
  - - release.. zero;
  - STOP while in motion;
  - "Shorts straight?" (R2.7);
  - Lidar stop in front of the box;
  - Open tab  ♪ stop;
  - The camera and the lidar see the scene.
- **ROSMASTER:** same for base; joints and small steps;
  Sensors; STOP.
- **SO-101:** take from:8020 (R4), Leader  ♪ follower, seizure, STOP, autopsy
  Injections.
- At the end, one test entry for the automatic check (R6.4) task.

FAL does not block forever: there is a reason and what to do.

### R9. Documents
- `docs/RECORDING_DAY.md` - One page "recording day":
  "Readability", check, collect, switch off, charge (Tank - only)
  (b) The following table shows the number of units which are not in operation:
- Update `README.md`, `CURRENT_STATUS.md`, `docs/TANK.md`,
  `docs/DATASET_GUIDE.md`, `docs/PHYSICAL_ACCEPTANCE.md` under new
  Remove outdated allegations of the closure of Tank and 92 PASS.
- `SOFTWARE_AUTONOMY_PROMPT.md` should mark "the next step after
  Dataset records."

---

## 4. What remains user (after R0-R9)

1. Mark the scene:
   - The same cube and box for SO-101 and ROSMASTER hands;
   - The same target and stop zone for Tank and ROSMASTER;
   - Ten sets.
2. Insert robots ♪ Readiness ♪ Checking "everything goes" for each.
3. "Datchset collection" ♪ task ♪ series. Target orientation: 10 series × 5
   Successful, about two or three hours.

---

## 5. Decisions taken (no user to ask)

1. SO-101: Make the "Take to Explorer"/"Return to:8020" (R4).
2. Tank Lidar stop: 0.15 m at speed above 0.1 m/s; in the target area of the approach
   (`tank_dock*` profile ) may approach to 0.05 m at a speed other than
   The values in `tank-limits.json` are visible on "Reception".
   Same rule for ROSMASTER.
3. External disc: auto-definition of mounted film disc with
   `explorer3-backup/` directory; if not available, only local copies
   Catalogue and Heshes, yellow paragraph on "Ready".
4. The recording options are `*_rgbd_lidar`, and the hands are the usual profiles.
5. Procedure for placing on robots: Backup... check
   ♪ Restarting his service ♪ "Readyness" test.
   A mistake is an automatic rebound to a backup.

---

## 6. Ready when

- R0-R9 is done in a row, without intermediate questions; is combed and fired; `scripts/run_all_tests.sh` is 0 failed.
- In `fleet.json`, all three robots are on, Tank `floor`.
  There are no active lock-in files on Tank and Homebrain.
- Agent Tank limits speed and speed itself, USB failure is processed
  Without permanent lockdown, Pi's defenses are working.
  It's installed on Tank with a backup.
- :8030 works for HEAD. "Ready", "Resort of the Dataset" and the test master
  I've been on a browser test on a fake robot.
- User received `docs/RECORDING_DAY.md` and short report:
  It's done, which is verified, which is only physically available.
- The agent never sent any movement teams.
