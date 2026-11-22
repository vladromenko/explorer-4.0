# Reuse of scientific components

Status of implementation; empty checks do not indicate readiness.

| Component| Type| Version/licence| Use and verification| Limitation|
|---|---|---|---|---|
| Menagerie robotstudio_so101 | upstream | `370c439…`; Apache-2.0 | `sim.models.so101_model`, real steps, camera, geometric transport of cube| Local calibration not confirmed|
| MuJoCo Studio WebViewer | upstream | 4.0.1; Apache-2.0 | `sim.worker`: `launch_web.launch`, `ViewerHandle.set_model/sync`; Playwright sees canvas and control| SO /ROS arm/both UI chassis verified; ROS geometry from official archive; common world with three critical tasks verified; joint execution of two stored ACTs and exact replay verified|
| Playground SO101PickCube + RSL-RL | upstream | Playground 1.0.1 / Apache-2.0; RSL-RL 5.4.2 / BSD-3-Clause | Official `mujoco_playground.rl.rsl_rl.train`: CPU step /train/save/new-process reload| While smoke; liff   \ place|
| MuJoCo/Gymnasium + SB3 PPO | upstream integration | MuJoCo 4.0.1; Gymnasium 1.4.0 / MIT; SB3 2.9.2 / MIT | `sim.ppo` uses the official PPO on nyative dinamics| 4 final runs of 16384 steps were performed on early models; 0 /20 each; not skill|
| Playground sysid | upstream + adapted data loader | 1.0.1; Apache-2.0 | `sim.sysid`: Original `build_parameters`, `to_model_sequences`, MuJoCo optimizer; 2 real trajectories fat, 1 postponed| 3 iterations; gold-out residual deteriorated 0.00566 × 0.00595 rad; parameters not applied. UART writing time is proxie, not MCU acknowledgement; zero joints require verification|
| Fleet-DAgger | upstream subset + ported integration | `ifl_benchmark` d35f0f8; MIT/Ryan Hoque | `vendor/fleet_dagger` is the exact Random /TD and assign_humans; `fleet_allocation.FleetAllocator`; 20 steps to the conformance of each method against the individual PASS source| One operator; pure allocation and one operator in the general stage checked; online queries, background transmissions and hand transfer to the next run; new rolling runes were not launched; TD received a Rick /novelty from outside; C.U.R. was not declared|
| Visual/dynamics randomization | protocol_adaptation | Tobin 1703.06907 / Peng 1710.06537; own code| `sim.variation`, seeded parameters and snapshot /restore; nominal /varied contacts checked without training| Accumulated ranges, quality effect of ACT not yet measured|
| AutoIntervene-adapted | ported_algorithm, partial | 2608.07065v1 §III; own code| `autointervene.Memory/SupportMonitor/calibrate`; the real ACT issues frozen features and chunk; queue /snapshot/reload checked without training| Math and disc roundtrip are checked for clearly marked nuxtures; memory/pog preparation from frozen table is connected to UI; online witting in the world is checked for fixtures; new tranded /held-out data has not been launched.|
| RESCUE/Kintsugi branch protocol | protocol_adaptation, partial | In the absence of any repetition of the article, the Committee has not been able to make any further observations on the question of the question of whether the State party should be able to provide a remedy.| `sim.branching`: three comparable branches, budgets, repetition and import of the tested segment| Browser /replay/readback PASS; not human impact research|
| [DART-inspired](https://proceedings.mlr.press/v78/laskey17a.html) | protocol_adaptation | noise_demonstrations + sim.capture, without the old MuJoCo| Scale of wallidation RMSE, clean /noisy budget, selected inside /executed/response; software tests PASS| Not fully DART covariance acceptance; new collection and training not started|
| Sim-and-Real Co-Training (Maddukuri et al., 2025) | protocol_adaptation | arXiv:2533.24361; own code| `datasets.cotraining_episodes`: The display of the levelled MuJoCo tasks is added only to the train, not more than the actual frames; the validation /test is only real; the PASS test| The actual show has not yet started; 1:1 is the initial value, not selected|
| Domain Randomination of the Appearance (Tobin 2017)| protocol_adaptation | 1703.06907; own code| `sim.aligned.randomize_looks`: table, light, hand/subject colour, ± 5° and FOV 55–80° camera; expert 12 /12 in redomization| Transport impact not measured until present display|
| Coordinated multi-robot exploration (Burgard et al., 2005) | protocol_adaptation | IEEE T-RO 21(3); own code| `navigation.choose`: the value of the site is reduced near another robot's target, a plot behind a closer robot| Individual contributions not identified: with the corrections to the pockets and the stitching, examination of the pair of x1.67 [1.38 - 1.90] (v4) against ×1.18 before the corrections|
| GoalSwarm / WildOS (camera cover)| protocol_adaptation | own code| `fleet_map.Grid.seen`, visual frontiers, camera turning to narrow points| Search 28 - 29 /30 simulation; no live check|
| Recipient-conditioned assistance memory | own method on existing store | `explorer4/cognitive` + `fleet_agents` | Piano help cases are written in the same memory with M3 compatibility in recipient's version; PASS browser scenario| No scientific impact established: M0 /M2/M3 on the same scenes|

The current verification artifacts: runtime `validation/corrective-a/`. Three scripted-expert recordings are the exact performance of MuJoCo with contacts, not fixtures, and not human demonstrations. After 50 steps the ACT save /reload passed, three rollouts on seeds 10,000–10002 were completed with the failure /task_deadline.. This tested version with the negative result of short learning.

ROHE is implemented using formula (2) of Fleet-DAgger: (M /N) × sum of award / (1 + sum of Frobenius allocation squares). `plotting/plot.py` also builds a penalised-reward graph in the author's repository, which does not replace the definition of article. "Successed tasks / minutes of assistance", including switch /reset, are published separately; a simulated expert is not considered to be measured by human time.

New models: `policy_catalog`, `training.train_command`, `sim.policy_worker`... use the official LeRobot 0.6.1 ACT /SmolVLA/Diffusion. SmolVLA base revision5e8e8d12a... and SmolVLM revision7b375e... are fixed. SmolVLA inference /snapshot on the available synthetic kheckpoint test, the quality of the skill is not declared; new learning is prohibited by the user. YOLE and SAM3 are separate performance layers, not replacement of motor policy.

## Agent layer · 14.11.2026

This is a working adaptation of protocols to the existing components.
The scientific superiority of the method varies clearly.
or the results of the study in the articles cited are not attributed to the project.

| Method / Primary Source| Source code and licence| Real point of integration| Boundary|
|---|---|---|---|
| [RoboOS](https://arxiv.org/abs/2505.03673), [RoboOS-NeXT](https://arxiv.org/abs/2510.26536) | [FlagOpen/RoboOS](https://github.com/FlagOpen/RoboOS), Apache-2.0 | `cognitive.registry`, typeled by TskGraph, roles, broker and temporal experience: the plan is separated from robotic skills and memory| Architecture adaptation, not RoboBrain/RoboOS cloud installation.|
| [PhysMem](https://arxiv.org/abs/2602.20323) | [verification.py](https://github.com/haoyangli16/PhysMem/blob/main/physmem/learning/verification.py), [hypothesis.py](https://github.com/haoyangli16/PhysMem/blob/main/physmem/core/hypothesis.py); MIT according to README| `store.add_case/verify_case`: Experience  ♪ candidate ♪ independent erisode IDs ♪ supported_in_scope / contracted; tests exclude self-confirmation and countback| Adaptation of the logic of verification /promotion with a more stringent alignment of the artifacts. Upstream sourceds are not copied, confidence is not made up, raw experience is not removed|
| [RoboMemory](https://arxiv.org/abs/2508.01415) | [SP4595/RoboMemory-Code](https://github.com/SP4595/RoboMemory-Code), Apache-2.0 | The division of the experience /facts/events/cases; FTS5 retrieve + frozen memory image changes the context of choice; the options are the same for M0-M3| Adaptation memory ×planning cycle; heavy embedding /VLM article server not installed; this is not complete upstream benchmark|
| [ActiveAlign / Look Before You Act](https://arxiv.org/abs/2610.23378) | Article CC BY 4.0 ArXiv; code not transferred| `run.execute_graph`: The new view of the target allows the continuation but success of the camera, the success of the recipient and the overall outcome are measured separately; both episodes and the compatibility of the camera/policy/geometrics remain.| Protocol adaptation of the continuation verification; VLA adaptation /training prohibited and not implemented|
| [smolagents ToolCallingAgent](https://huggingface.co/docs/smolagents/v1.26.0/en/reference/agents) | `smolagents==1.26.0`, Apache-2.0 | `cognitive.model`: real ToolCallingAgent, only closed proposal tool, maximum two generations with one format correction| CodeAgent not available; ToolCallingAgent does not perform engine/learning commands|
| [Qwen3-VL-2B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct) | Apache 2.0, revision `89644892e4d85e24eaac8bacfd4f463576704203`, hashes at `configs/cognitive-assets.lock.json`| Local inference on Homebrain, source checkpoint without updating the weights| Historical text-plan checked; direct RGB /VLM adapter retains pixels /grid/mask and has been processed-only checked. New generation is prohibited and not performed|

`sim.cooperation` uses the same old FleetWorld, the same ArmModel IK and Doc Expert.
Detector is clearly called OpenCV color /shape baseline only for fixed
orange marker in nominal stage; it does not receive simulator segmentation IDs
Or the true position of purpose.
Simulation /yaw/stable is used separately to estimate the outcome.

New R4 implementation is based on [DART](https://proceedings.mlr.press/v78/laskey17a.html) Article]
and [the official repository](https://github.com/BerkeleyAutomation/DART), viewed on 14.11.2026.
The old relationships mjpro131 /mujoco-py were not established, the authors' code was not copied.
The action label in R4 LeRobot is a test of expert intent to sound; reference
The actual command remains active in research.jsonl, a separate field
Exert_action is clearly connected to it. Redefinition is not allowed to be recorded.
