# Simulation models

Stage A, Homebrain. Real profiles and data are not replaced by simulations.

| Wednesday| Source and status|
|---|---|
| SO-101 pick-place | Menagerie `robotstudio_so101`, commit `370c43965323c0944b433b202aac5058b5f907a9`Compilation, contacts, wrist RGB, capture/carry-out/dismissal by the teacher are checked. |
| ROSMASTER pick-place | Original Yahboom M3Pro URDF/STL + SRDF from the official code archive. Five changes and the camera match the saved panel. The Native Import, mimic, contact capture/retention/delay/dismissal are checked at three locations without training. |
| ROSMASTER dock | Same initial geometry in a fixed arm position, flat movement from forces and moments, drive approach, unmeasured mecanum dynamics, script approach complete.|
| Tank dock | The MentorPi T1: the original URDF /STL package, the match with the installed files are checked. Geometry is no longer a dimensional model. The flat drive remains a power drive, not yet calibrated model; the published mass does not replace the weighing of the assembly. The real USB incident is open.|
| Fleet lab | One MjModel /MjData for SO-101, ROSMASTER and Tank, total time, gravity and contact. Three options for space, real mesh objects, interaction through observation and separate verification of robot-related activities. Physical transmission of the object and the live-body ROSMASTER are not declared.|

## SO-101

All six original positional actors and the original mesh /contact geometry are used. Local expansion adds a free cube of 32 mm, mass of 35 g, open box, light and viewer. These dimensions are the parameters of simulation task, not measuring user items. Five joints: radians ~ degres; capture: range of an agent ~ 0 - 100 per cent. The match between zeros/directions to local calibration requires verification. This model is not automatically applied to a real robot.

Physical 2000 Hz; interface manager 30 Hz alternate 66/67 The command is delayed by one stroke control, then passed through a 25–60 ms filter; the actual positions are set out by MuJoCo, `qpos` not appointed to `step`Success is the center of the released cube inside the box, a small speed and a 0.5 second capture.

ACT only sees Wrist RGB 640×480 and six joints. State-PO is additionally provided with true object/target coordinates; this policy is not allowed to be physically managed. Snapshot retains MuJoCo INTERGRATION state, command line/filtration, RNG, phase/time and policy chunk state. The determinism of recovery is verified in real physics.

The original Playground `SO101PickCube` is checked separately: one CPU environment, PPO checkpoint and download in a new process. Its rise criterion does not replace the pick-place. This is a short test of the ability of the substream, not proven skill.


## ROSMASTER Reference Model

[Official page of Yahboom](https://www.yahboom.net/study/ROSMASTER-M3PRO) → Code-Firmware → `ROSMASTER M3 PRO-Code.zip`B. Fixed SHA-256 `7f9083d301fef50633445272505e9acb561a4b6abe362dd946d7deaaf4caff0f`II. Model: `orin/M3Pro_ws-0.0.1.zip`, `m3pro_ws/src/M3Pro/urdf/M3Pro.urdf` and 20 STL. Supplement: `orin/yahboomcar_ws.zip`, `M3Pro_config/config/M3Pro.srdf`. `python -m scripts.cache_m3pro --download` Once downloads the archive and only removes the original files that are needed; the Internet is not used when it is normally launched.

`sim.manufacturer.native_tree` uses this MuJoCo URDF importer. The dimensions/axies/geometrics of /CAD-inertia and five mini-limits of capture are retained; the list of exceptions to collisions is taken from the SRDF factory. Zero empty visual tags are removed; wheels and additional chamber rotation are fixed in the arm scene. For dock the hand is fixed in the published/saved working position [90.130.0.25.90.30]. `package.xml` states Apache 2.0, but contains the old TurtleBot attribulation: the original Assets remain local, only the loader and hash are in Git.

Masses/inertia The original CAD is not a measurement of a fully assembled robot. Control coefficients, friction, lateness, camera FOV and the physical sixth CAD servo still require verification; none of them are recorded in the real agent. The chassis uses the real force/moJoco time, but with limited flat DOF: the wheel-to-ground contact is replaced by a clear response/slip model, impact with objects is saved. This is an honest-marked approach to the dynamics.

Previous ROS /Tank records and ACT /PPO checks are done on the first simplified geometry and stored with its hash. They confirm the software version of that version rather than the quality of the new original model. When geometry changes, new data have another model has been added; old certificates are not rewritten. The main training will be started by the user on its own after the program is ready.

**Measured 2026-11-13 (ROSMASTER, uninitiated):** chamber 640×480, fy=480.711 px \ vertical FOV 53.06° (now in both ROSMASTER scenes), sensor frequencies, joint limits of the URDF = controller limits; source and unmeasured - `docs/handoffs/rosmaster_measured_params.json`**Response identification:** `explorer4/sim/rosmaster_sysid.py` (`scripts/rosmaster_sysid.py <profile>`) selects the time lag, constant time, ratio (base) and speed limit (hand) from real records and compares the nominal sim, the shape of the simulation (one lag) on the postponed sequences/slipThe result is a candidate file, not automatically applied (`apply_to_env` There are no real traffic records yet, so the status of the model remains `assumed_uncalibrated`At the synthetic test with a late and speed limit, the hand simulation is wrong 5 to 9 times more complete; if the real data shows the same, the arm model needs to be supplemented by these two parameters.

## Tank and actual charges

Complica and references to nine saved chapters of the instruction: [TANK.md](TANK.md). The user machine is MentorPi T1 Advanced with its Pi5 ModelB Rev1.1 class RAM8GB /4CPU in historical kernel. The current free memory/temperature is unknown until the next hardware check. No M1 /A1 parameters are used instead of caterpillar T1; the missing source `mentorpi_description` is intended to be copied from the installed Tank at stage C without changing its current files.

## Correcting Contacts — Without Training

Both hands use the original contact geometry. SO-101 retains the Maintenance collition /meshes and friction; ROSMASTER has the SL, mimic and SRDF. The numerical softness of the contacts and the connected links are corrected: timestep 0.5 ms, solref [0.001.1], solip [0.95.099,0.001,0.5.2], 100 iterations; for the minic solim [0.99.0999,0.001,0.5.2]. These settings limit the numerical error, **are not measurements of the tibia of the parts.** See [MuJoCo solver parasmeters](https://mujoco.readthedocs.io/en/stable/modeling.html#solver-parameters)].

The scripted teacher SO-101 is also corrected: the target position is interpolated with speed limits so that the sharp transition to the box does not throw out the object. The cube remains free: without attachment /weld, the purpose of qpos or the removal of the finger contacts. The rise above 100 mm, retention to the box's opening command, release and steady position in the box are checked.

`scripts/check_grasp_physics.py` measures contact on the physical lift, retains capture/carry-over/dismissal and JSON with the original hashs./2/3: SO-101 3/3, penetration of a maximum of 0.403 mm; ROSMASTER 3/3, maximum 0.221 mm, mimic error < 0.00038 rad. These are tests of a given geometric trajectory, not training or the quality of an autonomous policy. `test_rosmaster_sim_contacts.py` it covers both hands.

After the physic change, the old episodes are saved; the UI study only selects the version of the open stage. `datasets.select_simulation_revision` prohibits implicit mixing of versions. The ACT evaluation and the PPO renewal test the model version. The old kheckpoint is not declared tested on the new geometry. The main instruction was not launched on the instructions of the user.

## Clarification T1: Reference geometry found

`sim.tank_model` imports original package CAD via MuJoCo URDF loader. Source: public mirror `gongyizhi0425/Shipcleaning-Robot` e637226dcd51620fd1778672a1296c6d7c3d29a; downloading `scripts/cache_tank_model.py`, local manifest SHA of each file. Official open T1 repository still does not contain these files. Chassis herometry/conversion is checked with the official chapter 6.2.3. All 10 used files coincided with the installed user Tank package (docs /tank-stage-c-readonly.json). This is not a verification of mass, dynamics or optical fixation. Do not declare mirror official release. TODO-license is retained; the Assets are not included in Git.

The STL chassis has more than 2,000 dimensions; the exact conversion to OBJ preserves all the original triangles./FOV Trick mesh is a single fixed geometry inside the planar model, not a simulation of the caterpillar./slip - individual assumptions, not the result of odometric calibration.

`fleet_lab_sim` is a world, separate namespace and working areas, ROSMASTER only an arm profile. Common solver 2000 Hz /elliptic/impratio10; this is a new version of the model. Mechanically controlled tests do not replace the assessment of the Trained policies. The overall scene is not yet minimal; individual variations are retained in individual media.


### Tank: measuring chamber, 14 November 2026

===Reception===The actual CameraInfo RGB640×400: fx415.28833, fy416.6935, cx318.07541, cy188.47833. Instead of the assumption of fovy65°, MuJoCo resolution /focalpixel/principalpixel. is used. The total arbitrary scale of the pixel is required only for the ratioofocal /sensorsize; the physical size of the matrix is not declared measured. The signoffset is checked by the figure of three ROS K (acceleration <0.8px). The basic vertical FOVE51.35o. Lens distributionD is retained but not applied in the range; extrinsics relative to CAD and the dynamics are not yet identified.

The Randomization FOV also changes the camera_inrinsic, snapshot /restore retains their 11 test /variation/mobile/fleet/branching projection without learning. The change of camera changes the modulehash; the old checkpoints are not proven politicians for the updated model.


## World and World Affairs. 14.11.2026

`sim.room` adds workshop, storage area and assembly area.
Reproducible options selected in `/sim/fleet` and `/team`: Change of location
The calibration mats are limited to the working units.
Zones; there are floors, walls, desks, open packagings and shelving.
remains a fixed physical marker in the frame.
The user room does not mean that existing dock can be arbitrary.

Bottle, can and lemon use original mixes/textures [robosuite](https://github.com/ARISE-Initiative/robosuite),
`5ce6643f3092639d08f7b0f90ed1c6a84f50552c`; MIT and all SHA are stored in a row
in `sim/vendor_props`Runtime works offline and checks the hashs.
Another simulation. Visual geoms have zero mass/no impact; separate
collison geoms are the contact and the apparent mass. Closed forms use convex.
The packaging is made of five walls and is not filled with a common bulge.
The full bottle, liquid and deformation of objects are not modelled.

Mass 80 /150/70 g, surface friction and rolling resistance - clearly defined
The parameters of the test stage, not the measurements of real objects.
The contact has slip, twist and rock.
(condim=6); solref=003 s with a total step.0005 s. Parameters follow the limits
[MuJoCo models](https://mujoco.readthedocs.io/en/stable/modeling.html), but require
Identification for real-life material transfer.

`check_shared_room.py` checks the support/force, penetration < 2 mm in this MuJoCo,
Speed blackout, exact snapshot /restore, three full-scale help scenarios and contact
Tank to object. The same commands from the same image are compared for contact:
An obstacle to the building against the barrier outside the way.
A diagnostic physics test; the planning model does not receive its hidden coordinates.
The ball can be clamped, so successful interaction is not necessarily considered
"Greatly pushed away": real displacement restriction and contact force are measured.

The dynamics of caterpillars and mecanum are flat so far: forces/times affect the hull, themselves
Ribbon/wheels are not allowed dynamically.
The simulations do not demonstrate the accuracy of the odometer or the STOP hardware.

### Correct the operator's position to specify (until the startup has been checked)

SO-101 and its task is raised to a separate physical table; ROSMASTER and Tank
The `configs/physical-layout.json` contains `measured_height_m=null`.
And the nominal height for the 0.75 m simulation. That's a guess, not a freeze on the table.
One copy of the process parameters defines the table, the model shift and the TuskView;
The file change is applied by the following worker. Geometry, location and contracts
The measured height with the source doesn't create any
Total world TF. Interplatform transfer of items is not permitted.

After the "nothing to run" was ordered, the code did not re-run or physically run.
Previous /browser PASS does not confirm new geometry; it is retained
As historical evidence, re-entry is pending.
