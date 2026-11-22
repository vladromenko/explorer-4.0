# Explorer 4.0 — robot learning from demonstrations and selective help across a robot fleet

Explorer runs on Homebrain, a Jetson Orin NX workstation. An operator can record a demonstration, turn it into a LeRobot dataset, train a policy and replay it on controlled MuJoCo scenes. The research question is practical: **when a robot struggles to pick up an object, does it need a better estimate of the object's position, information about its shape, or more examples of the movement?**

The research register traces the fleet’s controllers, pretrained policies and assistance mechanisms to their primary sources. It includes the measured results, known gaps, and the acceptance test for each proposed change. [Research register](docs/RESEARCH_REGISTER.md) · [Read on Homebrain](http://192.168.0.168:8030/simlab-media/reports/research-register-20261122/index.html)

## How the fleet works

| Component | Role in a pick-and-carry task |
| --- | --- |
| **ROSMASTER** | The mobile manipulator that approaches and picks up the object. Its arm camera and servo feedback provide observations for recording and policy evaluation. |
| **Tank** | A MentorPi T1 scout that can search for the object. Its agent exposes camera, depth, lidar and IMU observations for navigation and replay. |
| **SO-101** | A tabletop arm with an overhead camera. The station can measure objects and prepare grasp examples for transfer to ROSMASTER. |
| **Homebrain** | Hosts the browser interface, episode catalogue, training jobs, perception models and simulators. It can run the experiments with the physical robots powered off. |

## From a demonstration to a measured result

1. **Record.** The operator selects a task, checks the platform and records one attempt per episode. An episode associates images and measured state with actions, timestamps, scene identity, outcome and interventions. Control of the physical arm requires an explicit handover. [Recording guide](docs/RECORDING_DAY.md)
2. **Prepare the dataset.** Collection checks flag unreadable frames, timing gaps and invalid measurements. Related sessions and layouts are grouped when assigning training, validation and test episodes. The split, source episodes and training recipe can be inspected before a job starts. [Dataset guide](docs/DATASET_GUIDE.md)
3. **Train and replay.** Homebrain runs the pinned LeRobot trainer, saves checkpoints and reloads the selected weights for evaluation. In MuJoCo, two methods can try the same starting scenes. The resulting per-scene outcomes reveal whether a lower imitation error actually improves a grasp. [Simulation models](docs/SIM_MODELS.md)
4. **Test a request for help.** Change one piece of information, such as the target position or the direction in which the gripper should close. Compare independent action, selective assistance and a fixed helper on the same task. A physical trial has its own approval and outcome record. [Fleet execution](docs/FLEET_EXECUTION.md)

## What the experiments have shown

| Setting | Measured outcome |
| --- | --- |
| **Choosing a helper in a 2D delivery task** | On the same ten rooms, the rule that requested help according to missing knowledge completed **10/10** deliveries. ROSMASTER alone completed **3/10**, with Tank alone **2/10**, and with SO-101 alone **9/10**. [Paired room results](docs/results/knowledge_gap_sim/20261116-v2/summary.json) |
| **Grasp orientation in MuJoCo** | On 82 scenes with narrow objects, a controller given object size succeeded **58/82** times. Adding the closing direction brought this to **74/82**. For the 38 wide-object scenes, every condition scored **1/38**. [Geometry experiment](docs/results/knowledge_transfer_mujoco_v3/ANALYSIS.md) |
| **Learning the movement of a fixed cube grasp** | A frozen RGB model estimated the cube's position, and a joint trajectory was interpolated from simulated demonstrations. Training the movement on 5, 11, 20 and 32 demonstrations yielded **40, 53, 54 and 55 holds out of 60** respectively. Giving the same 32-demonstration model the mean training position yielded **6/60**. The shared vision model had its own 1,024 labelled simulation images. |
| **Requesting a larger movement library** | On 40 additional simulation scenes, the robot asked for help when the estimated target lay outside the region covered by its five local examples. It held the cube **38/40** times with **26 requests**. Always asking yielded **37/40** with 40 requests, and acting locally yielded **36/40**. |
| **Training on physical demonstrations** | Two ACT policies trained on 11 archived human demonstrations each held the cube **0/20** times when replayed in MuJoCo. Pretraining reduced mean joint-command error on two diagnostic recordings from **6.73° to 6.13°**. Physical grasp success and the number of human demonstrations saved still require trials on the robot. |

The first two experiments link to evidence in Git. The November 22 trajectory, assistance and human-demonstration studies have separate records on Homebrain. Under the data directory, open `simlab/reports/article-20261122/index.html` for the manuscript and the per-scene results. Each study identifies its demonstration set and evaluation scenes.

## Repository structure

| Path | Contents |
| --- | --- |
| [`explorer4/`](explorer4/) | Main Python application. `app.py` serves the NiceGUI/FastAPI interface. `recording.py`, `datasets.py`, `training.py` and `evaluation.py` implement the recording-to-evaluation workflow. |
| [`explorer4/sim/`](explorer4/sim/) · [`explorer4/simlab/`](explorer4/simlab/) | MuJoCo environments, robot models, scripted teachers and policy replay. SimLab also contains docking scenarios, system identification and PPO experiments. |
| [`explorer4/cognitive/`](explorer4/cognitive/) | Records observations, decisions and requests for assistance so that an intervention can be traced to a task outcome. |
| [`agents/`](agents/) | Robot-side adapters for ROSMASTER and Tank, Homebrain service definitions and the ROS 2 observation bridge. |
| [`hub/`](hub/) | Browser launcher for the Homebrain robot consoles and services. |
| [`configs/`](configs/) | Fleet inventory, task and simulation profiles, training settings, deployment thresholds and pinned dependencies. |
| [`scripts/`](scripts/) | Environment setup, dataset checks, job entry points, experiment runners, benchmarks and replay tools. |
| [`assets/`](assets/) | Shared physical reference assets, including the SO-101 donor-station marker. |
| [`tests/`](tests/) | Application, simulation and browser tests. The root `conftest.py` defines the execution groups. |
| [`docs/`](docs/) | Operator and research protocols, hardware notes and handovers. [`docs/results/`](docs/results/) holds experiment protocols, summaries and per-scene records. |

## Running on Homebrain

The application targets Python 3.12 on Linux. The bootstrap script installs the pinned CUDA build of PyTorch; the MuJoCo environment is installed separately. On a newly provisioned Homebrain checkout at `~/Projects/explorer-4.0`, use:

```bash
bash scripts/bootstrap.sh
bash scripts/setup-sim.sh
bash scripts/install_service.sh
```

On a configured host, `./start.sh` and `./stop.sh` control the UI service. Open `http://localhost:8030`. Use `/recording/readiness` and `/recording/collect` for physical demonstrations, `/learn` for training, `/sim` for simulation and `/swarm` for fleet missions. The test runner is `./scripts/run_all_tests.sh`. [Operator guide](docs/OPERATOR_GUIDE.md) · [Test environments](docs/SOFTWARE_TESTS.md)

New code imports `explorer4` and uses `EXPLORER4_DATA` to select the data directory. Existing installations can still import `explorer3` and use `EXPLORER3_DATA`. The deployed systemd unit names, ROS 2 topic namespace and default data directory (`~/.local/share/explorer3`) are shared with earlier installations. Raw recordings, calibration files, checkpoints and logs live outside the Git checkout. Restarting the UI can interrupt an active job.
