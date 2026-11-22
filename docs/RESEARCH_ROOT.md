# Main issue after clarification of owner 16 November

The long-term task is suspended by the owner. [New transfer of](HANDOFF_20261116_CURRENT_WORK.md): results, check run, tasks and problems. The RNG policy has been tested by 5 KPU tests; not yet developed and applied to the current K.

Does the targeted request and adaptation of SO-101 experience reduce the number of ROSMASTER demonstrations itself
And the full time of a person in acquiring a self-exposure?
The measurement of the object, the transfer of the trajectory, the training of the recipient and the physical absorption are separate results.

T0 Target-only / T1 general-sim / T2 donor-transfer / T3 seducted-transfer is given in
[](handoffs/ON_DEMAND_SKILL_TRANSFER.md): First pilot: one non-zero k,
T1 /T2, equal reference weights, sensors, update and generation budget; launch after verification
One transfer and harmonization of a new heavy budget.
Leader.ROSMASTER, not considered as an SO-101 experience, all derivatives of one donor belong to a common group.

Relevant results and work: [CURRENT_STATUS.md](../CURRENT_STATUS.md), [TODO_NEXT.md](TODO_NEXT.md).
K0 - K4 completed: 3 /10, 2 /10, 9 /10, 10 /10, 8 /10. MuJoCo v2: 44 /60 previleged, 34 /60 without size, 35 /60 with size.
The new pair v3 changes the dimensions within four hard classes. The technical pairs and 50 SmolVLA updates have passed (batch 8, without OOM); they are excluded from full comparison. The main protocol: the first 200 successful pairs of maximum 300 seeds 50006-50305, two SmolVLAs for 12000 updates, the same train /validation/test., the complete collection is complete: 200 successful pairs of 224 attempts, 24 failures are saved, technical errors 0. Both parties have received the same train /validation/test 160 /20/20. The first SmolVLA completed the 12000 extensions and gave 0 /20 on the new MuJoCo scenes, all task_deadline, without technical errors; data published. Control without size is being studied. Until the comparison is completed, the benefits of the information sub-sample are not stated.
For the future T-take, a complete set of new scenes is recorded: ≥80% success, at least three independent success stories with observed up/down and no prohibited contact. Only successful episodes from a failed series cannot be selected; the version of the tester and weight are retained. Import and measurement code is checked, the T-policy has not been evaluated.
The work line separates the actual learning blocks and the old "inbox": normalizing the text does not cancel the test of the archive series, cameras and units. The donor grasp SO-101 is not considered to be a show to a person. This is a correction of the data production, not a learning result.
The small target budget can now capture exactly k=5 /10/20 learning shows, individual gold-outs and general origin groups. For example, 5 train + 1 calidation + 1 test is 5 for learning, but 7 target records are fully valued; additional measurements are taken separately. This is a training not already performed by T output.
The change in the definition of the task cancels the previous physical tolerance of the model: the initial training plan, the task diagram and the relevant hash contract are checked; this is a policy condition, not a guarantee of physical success.
The real donor packages are still zero.
The clear program extension of the saved target is linked to the existing Swarm; the old observation is not carried over, the weights are checked again, the repeat/late launch after STOP is prohibited. The isolated tests of this ligament are not considered to be a complete physical mission.
The first full T-mission has a separate end zone of 40 x 40 cm on the floor; SO 101 is a teacher. The conditions of the completed K remain unchanged.

The research context and history of K is maintained below. They do not replace the relevant list of actions and prove the acquisition of motor skills.

# The root study: the robot knows what he doesn't know and calls a Roy

## Question
Can the robot recipient (ROSMASTER) determine before action what knowledge it lacks,
To choose which piano will give them, and whether it will be more successful than alone or with
A fixed assistant?

## Three kinds of knowledge and who gives them
| Gap| When considered a space (`explorer4/knowledge.py`)| Who Helps|
|---|---|---|
| Where| No common map space below 15 minutes or error > 0.35 m| Tank, ROSMASTER itself|
| HOW| No proven knowledge of the object (wide, altitude, altitude)| SO-101 bench (cam above + SAM 3 + calibration)|
| SHAPE| No compatible tested model — maintain request and wait for experience| Human beings (indications), carry-over, training and independent testing|

Knowledge of the subject is metric and independent of the robot; each robot translates it into its own capture.
Knowledge is confirmed or denied by the capture of the recipient (`record_use`) and the case
The help is written in memory of the help (type `knowledge`).
The language model (local Qwen3-VL-2B, `cognitive/gap_advisor.py` ) may offer gaps and
The rules are the basic line.

## Experiments
| Level| What| Conditions| Where|
|---|---|---|---|
| 2D piano simulation| "Bring" in virtual rooms| K0 one ROSMASTER · K1 + Tank · K2 +SO-101 · K3 on gaps · K4 calls gaps Qwen| `scripts/knowledge_gap_experiment.py` |
| MuJoCo | Taking of objects of different sizes from the floor| without knowledge · knowledge of SO-101 ( ± 1.5 mm) · complete information| `scripts/knowledge_transfer_mujoco.py` |
| MuJoCo, training| SmolVLA with knowledge in the task text and without| Same seed| Plan: `docs/TODO_NEXT.md` para.|
| Real robots| "Bring a cube": gaps ♪ SO-101 measures ♪ search ♪| with / without| Roy, episode log|

Measured: success of task, time, number of human interventions, benefit of assistance to recipient
(Associate has done, recipient continues, task accomplished).

## What already shown
- The real SO-101 bench measures a 298 mm cube (the truth of ~29.5) without movement of the arm.
- Real chain: ROSMASTER defines the KAK space, the metering platform, ROSMASTER finds and approaches;
  The geometric grab at the floor is missed by 2–3 cm, and a trained grab (block 3) is needed.
- MuJoCo: flat objects (cookies 1.2 cm, sock) are not taken from above by this capture even with full knowledge —
  Then knowledge should lead to "inclusion of man" rather than to an attempt.

## What the owner does
1. Block 3: 50 display of capture from the ROSMASTER floor by the lead hand (section "Datchset collection").
2. The SO-101 transmission sites are once (~10 mines) to reach the person.
3. Real runs "Bring..." with robots on the tags: 10 with help, 10 without (ROSMASTER only).
4. Presence during the check of the stopover of Tank in front of the chair.

## Restrictions to be called
The size of the objects in the simulation is model.
Tank has no hardware stop; the software is a.25 m + deep camera (low obstacles).


## Adaptation of object experience: proven sources of implementation

Researched by MG_EnvInterface (TCP/site positions, conversion \\target,
DataGenerator /WaypointTrajectory and transform_source_data_segment_using_object_position:
https://mimicgen.github.io/docs/tutorials/datagen_custom.html
https://github.com/NVlabs/mimicgen/tree/c0fbff22ba40060f05a917a80817f3f5c20731e7
NVIDIA source code licence limited to search /evaluation; wholesale copying and installation
The other person's robosuite /MuJoCo was not executed.
The published conversion of `MimicGen-adapted`, not a precise play of the copyright bookmark.
The site's foot position is frozen at the beginning of the phase: the rise after capture is not deducted by the movement of the object.
The scheme and test package are not real experience: audits of existing SO-101 records have not been accepted.


### Query: retention of mission, 16 November 2026

Readiness now separates the unknown position, properties of the object, missing/determinate capture and measured incapability. The regular ROSMASTER command with missing skills retains the request in the existing cognitive_missions /cognitive_requests and releases robots. The geometry experiment is clearly selected; it does not become a acquired skill. /swarm and /today show the reason for waiting and the next action. Re-demand reuses training; cancellation closes all associated expectations. Restarting and completion of learning is not allowed.

Checked on Homebrain: 20 mission target tests, readiness and data origin; 6 additional tests after the cancellation was linked to the missions and the cards were entered into the general register; these tests were software tests, physical acceptance was not performed; the training package selection path and browser testing were still in progress.


### Transformation: Limited prototype, 16 November 2026

Added to the minicGen-adapted adapter of the existing ROSMASTER scene: measured object-related phases SO-101, fixed phase supports, own IK ROSMASTER and metric disclosure. Donor joints are not copied. The independent auditor monitors the rise/retention and impact at every step of physics. If monitored, the option is rejected after 2 s. The failed record is retained. The general donor is transiting the derivatives for data separation.

Artifacts: `docs/results/skill_transfer_preflight_20261116/summary.json` and `packet.json`The source here is **symmetric SO-101**, not real. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

Checked: 3 MuJoCo adapter tests, 7 origin/contract tests, import and plaster reading of their own records. All derivatives of the single source are one group: total train /validation/test of which is prohibited. Next: complete the recorded SO-101 geometry measurement; after three test real-world displays, form a suitable package. Mass T-learning has not been started.


### Relationship of the request to the data and the current line, 16 November 2026

The selection of packages, the retention of all transfer results, the preparation of the unmodified budget and the existing Jobs task are now linked to the request. The final weights are being checked for their own records and lineage; random episodes cannot be added. Start/end is used as the previous one. Re-press does not create a duplicate, the cancelled request does not accept late start. The completed weights translate the request into a check rather than a accepted skill. The physical wait/takes are only taken out of the individual recorded results; they do not resume movement.

/swarm is available with a basic package and request information, selection of experience and reference to the previous training site; /today reads the same state. Checked out: 19 readiness tests/training plans and one final Playwright scenario with six states. Brouser worked on an isolated directory without controllers and no worker; the viewing package is copied from the actual simulation artifact. Physical waiting/admitors check the display, not physical capture.

Until completion, the measured geometry stream of real SO-101, the choice of the end zone and the recent confirmation of the mission's continuation, actual displays and independent tests remain: the T-learning has not been launched; a specific budget will have to be agreed upon after the first real transfer.


### Preparation of real SO-101 geometry, 16 November 2026

The current manual SO-101 adds default-set top camera C920 1280x720, frame time, measured joints and fixed tip positions based on the original kinematics. ArUco No. 7 (black square 20 mm) is used to independently observe the cube: settings and downloads are in the section "SO-101 to move capture" to /recording/collect.. The settings do not include anything; the camera only connects within the clearly started display. With an outdated frame, the session ends as aborted.

Only six static beginnings of joints and the position of the tip from so101ik 3456805bf11d86d6c0b6b625aed62395acd0862c; Apache 2.0 and notification are retained. The drivers, IK, embroidery and old backken are not moved or summoned. Quinematique is not considered physical calibration: the current chamber, the contact TCP, the metric release of the sponges and errors still require separate verification. These unknowns are clearly stored in the original records; SkillPacket is not automatically created.

Checked: 6 geometry/schedule checks, browser settings inside the previous collection screen. All devices are present and free at the last check but no real movement is started. Three manual diagnostics of the owner are required after the label is prepared, then geometry checks and bag collection; the old three box epidiums are not re-marked.


### Clear choice of geometric baseline, 16 November 2026

The usual skill request is no longer replaced by a geometrical performer even in 2D mode. The scripts K and the previous aid experiment select the geometric baseline clearly. Twenty-one mission tests, virtual room and protocol K (4 min 15 s) have been tested, separately both waiting modes for missing skill. The current background K4 continues to operate on unmodified main; its source does not change.


### Collection of real SkillPacket from verified measurements, 16 November 2026

`build_so101_skill_packet.py` links the original episode to a view of the four phases and a separate geometric check report. The camera hashs/calibration/models and all the reference frames, the joints match to the record, the current contact TCP, at least three independent control points/openings, the metric curve of the sponge and the measured errors are checked. The unknown values are not replaced by zero. The hand is consistent with the individual upper chamber staff for the adjacent joint measurements and measured camera delay; the repetition of one frame does not extend the retention.

Only continuous observed rises ≥5 cm and retention ≥1 c give positive donor verification. Phases are fixed; the initial entry is unchanged. The training is not included in this operation. Checks: 8 assembler/geometric tests, 3 additional after reference to stable cell parameters. These are synthetic isolated locks, not physical. The actual package is still missing: recording and independent geometric verification of SO-101 is required.


### Measurement tolerance and final zone, 16 November 2026

The adapter refuses the source with an error of >5 mm, orientation >0.2 rad or disclosure >3 mm. The real bag assembler transfers the measured uncertainty of the camera delay to the error of the moving TCP. The actual registration requires a real donor and a training assignment. Checked: 10 assembler/readiness tests and 3 MuJoCo adapter tests. Physical accuracy is not yet measured.

The owner has selected the end zone on his own. For the first mission, a separate square of 40 x 40 cm is selected on the free floor next to the rebound, with a deviation from the reference cube and the SO-101 base. The coordinates in the real map and the position require the current measurement; the nominal simulation coordinates are not translated into reality. SO-101 remains the teacher. A rise without the presentation does not mean delivery.


### Final condition of the new mission, 16 November 2026

The normal new mission retains a separate end area on the floor and does not include SO-101 as the recipient. In 2D room, the 40x40 cm square is selected in a free space 70 cm from the original object; the former DriveTo /place is used; and the separate observation checks the release and location of the entire object in the error-based area. The projection model does not move the item directly to the requested coordinates. This is a 2D logic check, not MuJoCo physics, and not a real delivery. The real mission is waiting to measure the area/position and independent observer before moving.

The rise without checking the presentation is given a separate outcome; the normal mission does not produce the SO-101 online measurement. The former K retains its clearly selected geometric performer and the former end-state. The 2D performer now refuses to choose a trained policy instead of a hidden replacement by geometry. The specific end area remains with the mission; the new position of the subject or assignment does not create a re-training of the same skill.

Checked: 23 mission logic/readiness/former fatch tests; 13 target tests and one final browser scenario after last revision. Physical presentation, new learning and acquisition of real skills are not yet complete.


### V3 pair data and K closing, 16 November 2026

The full 2D series of K0-K4 is complete and published in Main a36b991: 3, 2, 9, 10 and 8 of 10 respectively. K4 has one time out and one failure; technical errors/hidden fallsback is not available. Qwen has not shown an advantage over the rules in these 10 rooms. The K reference and the old end-state are kept separate from the new mission on the floor.

The first actual pair of new geometry v3: seed 50000, the rigid approach of the balloon 44.2×45.2 mm, 217 frames, successful rise to MuJoCo. Both records are imported and read back; images and actions are identical, the result is that the task text is different. The result is: docs /results/knowledge_paired_v3_preflight_20261116.json. Reference PNG is placed on the outer section of the sheckpoints /sim-staging; the lack of a mounting prohibits such collection. Five pair/group/storage tests plus actual collection and import tests have been tested. The next step is a small set of SmolVLA memory checks, then agreed 200 pairs and two trainings of the 12000 updates. This is K, not motor transport T.
