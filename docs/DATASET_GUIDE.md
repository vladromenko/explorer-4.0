# Explorer 4.0 dataset collection and training preparation

Start with one repeatable task on one robot. Keep the original episodes with their observed outcomes, including failures and aborts. The software checks documented on November 14 covered recording, training preparation and the interface. Use the physical readiness check for the specific collection setup. [Physical acceptance](PHYSICAL_ACCEPTANCE.md)

## Choose the task and observation profile

| Task | Profile | Completed demonstration |
| --- | --- | --- |
| ROSMASTER arm | `rosmaster_pick_place` | Pick up the cube, place it in the box, release and retract the arm. |
| ROSMASTER base | `rosmaster_dock_rgbd_lidar` | Approach one visible target and stop inside the marked zone. |
| SO-101 arm | `so101_pick_place` | On the table, pick up the cube, place it in the box, release and retract. |
| Tank | `tank_dock_rgbd_lidar` | Approach a visible target and stop in the zone after the hardware check. |

The depth and lidar variants record RGB, states, actions, numeric depth, lidar and IMU features, availability masks and raw sensor packets. ROSMASTER also uses rear lidar, odometry and a magnetometer. ACT supports these inputs. The raw point cloud and raw streams remain available as records. A sensor capture from the Environment page has no paired actions or task outcome. For training data, record a demonstration from Recording or the ROSMASTER recording card.

## Record and review a short series

1. Open [Fleet readiness](http://192.168.0.168:8030/recording/readiness), complete the [hardware check](PHYSICAL_ACCEPTANCE.md), then open [Dataset collection](http://192.168.0.168:8030/recording/collect).
2. Choose a task, one observation profile, the operator and a layout. A new series creates `<task>-sNN` and `<task>-layoutNN`. When repeating a layout, choose it explicitly so the attempts stay in the same group.
3. Start the recording and wait for the frame count to increase. Demonstrate one complete task and mark success, failure or abort. Recordings run for 3 to 120 seconds. F9, F10 and F11 control recording. Space stops motion.
4. Wait for the save and stop before resetting the scene. The next attempt can begin while the completed recording is being checked.
5. The automatic check reads the LeRobot episode back, checks numeric state and action fields, and flags timing gaps over 200 ms and invalid durations. The player and first and last thumbnails are available for inspection. Review one or two videos per series and keep flagged recordings for review.

The usable-demonstration counter includes successful, verified and non-excluded recordings. Episode metadata records operator, layout, agent version, profile, motion limits, completion and failures. Initial and minimum voltage are included when measured. Missing values are recorded as unknown.

Recording requires 8 GB of available disk space to start. At the 2 GB reserve, recording ends and saves the data collected so far. Make an external backup from Fleet Readiness after collection. The local backup contains the catalogue and manifests. An external destination provides a second copy of the videos.

## Build independent training, validation and test groups

The main recipe starts at 50 usable successes in one profile and at least three independent groups. A practical collection is ten distinct layouts with five successful examples each. With ten independent groups, the default split assigns eight to training, one to validation and one to test.

For mobile tasks, vary initial position and heading within the verified control envelope. For arm tasks, keep the calibrated camera mount, object and task consistent. Vary permitted initial positions and orientations. A shared session or layout connects episodes into the same group, including through other episodes. In a one-group collection, add genuinely independent sessions. Keep frames from one episode together and freeze the same split when comparing methods.

Review actions and outcomes. If a recording is mislabelled or unusable, exclude it from training while preserving the original.

## Prepare a training plan

1. Open [Training preparation](http://192.168.0.168:8030/training/prepare). Choose a physical task and supported policy. ACT is supported for the ROSMASTER and Tank physical profiles. SO-101 offers its own recipes.
2. Select successful demonstrations of the exact profile. Choose a fresh model or a compatible checkpoint. Set a finite update budget and batch size.
3. Prepare the plan without launching the trainer. The system checks source files, LeRobot readback, video, causal order, command provenance and split grouping. Review the error if a source prevents preparation.
4. Confirm the episode and frame counts, the model and the training budget. Download the plan. It pins the source inputs and checksums, including raw sensor packets. Generate a fresh plan if the inputs change.
5. Starting training is a separate action with explicit confirmation. The legacy smoke and main training buttons start jobs immediately.

Prepare simulation datasets in `/sim/training`. Preserve the existing holdout groups when fine-tuning. Choose checkpoints with validation and use the test group for the final measurement.

A usable dataset has readable originals, reviewed actions and outcomes, matching input schemas, independent groups and a saved plan. A checkpoint requires a finished training job. Physical task success requires separately approved trials with recorded outcomes.
