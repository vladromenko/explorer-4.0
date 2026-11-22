# From MuJoCo to robot: What is checked and what is guaranteed

The goal is that if the model has passed the test, it can be run on a robot. It will be guaranteed to start, it will get the same entrances, and it will give the acceptable commands. As well as it will do the task, we will evaluate the measurements in advance, not the expectations.

## What was wrong (found on 15 November)

| Problem| Consequences| Corrigendum|
|---|---|---|
| In MuJoCo, the other tasks were rehearsed:* SO-101 cubes in a box of raised positions, ROSMASTER also put them in a box.| The MuJoCo model did not see the real arm's starting position, and on the actual frame it offered a 93–101o push.| The new MuJoCo `so101_handover_sim` and `rosmaster_floor_pick_sim` tasks repeat blocks 4 and 3: the same starting position, setting and success rule.|
| The So-101 wrist camera in the Menagerie model is 90 degrees relative to the present.| The MuJoCo picture isn't real.| Turn +90° and a severe random change of view: table, light, hand color and object, ± 5° and camera angle 55–80°.|
| The debugging mark of the tip of the capture was visible in the ROSMASTER policy.| A sign that's not on the robot.| Marks hidden.|
| No leads were checked either.| Possible scale shift.| Checked: the real peace of MuJoCo gives the same folded arm.|

Expert in new tasks: SO-101, 29 out of 30, and ROSMASTER, 20 out of 20.

## Working arrangements

1. **Write down blocks 3 and 4** for [directions](DATASET_RECORDING.md).
2. # Bring the MuJoCo scene to your position #
   `.venv-sim/bin/python scripts/sim_align.py --apply`
   The script runs the recorded joint angles through the same arm model and finds the starting position, site location, transmission point and area of the object on the floor. It needs at least five successful displays of each block. Before this stage is built on instructions.
3. **Collect the MuJoCo shows and rehearse the training:**
   `.venv/bin/python scripts/sim_rehearsal.py`
   The rehearsal goes all the way: expert shows, training through the Explorer line, a test at MuJoCo on new scenes, a run on real shots without motors, and a robot access.
4. **Learn at the present shows.** If you wish, you can add the shows from MuJoCo (joint learning, `cotrain_sim`, arXiv:2503.24361). The shows of MuJoCo are only in the classroom and not more than the actual footage. The test and test remain valid.
5. **Press "Ability to the robot"** in the learning tab. Without the tolerance, the model test on the robot will not start and this is checked by code.
6. **First robot tests** are conducted in limited mode: up to 60 s, with no step or speed in the performer. Only these tests are measured.

## "Absorbs to the robot" (`explorer4/deploy_gate.py`, `configs/deploy-gate.json` thresholds)

| Verification| What it says| Threshold|
|---|---|---|
| Convergence of entrances and exits| The joints and their order, the size of the state, the camera, the frequency, like the robot.| exact match|
| Time of calculation| The complete count on Homebrain through the same code as on the robot, it's all over the end of the package.| ≤ 80% of pack length|
| Real ex-learning shows| On the images the model did not see, the predicted targets are close to human movements.| joints ≤ 8°, capture ≤ 12|
| No push on the start| The first target is close to the current arm position.| 95th percentile ≤ 25°|
| MuJoCo | The closed cycle on the task that repeats the recording block on 20 new scenes.| success ≥ 50%|

The tolerance is tied to the balance hex. If the weights have changed, the test needs to be re-checked.

**Tested for models of night rehearsal SO-101** trained only in MuJoCo on an old task.

| Model| Convergence| Time| Error at the actual shows| Reed| MuJoCo |
|---|---|---|---|---|---|
| SmolVLA | Yes| 1.18 s out of 1.33| ±31° | 93° | 55% |
| ACT | Yes| 0.09 s| ±33° | 101° | 50% |

It should be: the model is only from MuJoCo, and on another task, you can't let it in.

## What can be said after admission

- **Guaranteed:** Model will be loaded into robot performer, receive exactly the entrances that you've been learning, get time, don't shake your hand at start and on real delayed shows repeat the person within the threshold.
- **Not guaranteed in advance:** the percentage of the robot's success in the task. It's given by the first tests.
