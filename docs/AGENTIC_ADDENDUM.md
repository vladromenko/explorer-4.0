# EXPLORER 4.0 — Agents, General Memory and Tested Mutual Assistance
## Adjustment supplement for already working Codex on Homebrain

It's a continuation of the existing project, not a new project, and not a team to start over.

Main repository: https://github.com/vladromenko/explorer-4.0
Sources of components tested that need to be maintained:
- https://github.com/vladromenko/explorer-embodied-intelligence/tree/so101-ai-learning-homebrain
- https://github.com/vladromenko/rosmaster-cubebot

## 0. Start with the current job, not the reset.

Read the current CURRENT_STATUS.md, the last part of STATE.md, RESEARCH_REUSE.md, ROS2_COMMON_SYSTEM.md, GAIN_PREPARATION.md and the modules actually used. Compare the working copy, Git HEAD, uncomplexed changes and the version of the process launched. The image tested in the addition: e4297038a034a68c2d2d9d6d9da1a50a5ec98aed5. This is a reference point, not a command to roll back to it.

Do not cancel the task, do not rewrite the changes and do not start a parallel developer on the same files. Add this to the current session after maintaining the agreed state. If the component is already implemented, check and use it, not create a duplicate. Change is a small self-contained comms; no force-push, new Git story and new web application.

Maintain the restrictions of the current operator. In the tested CURRENT_STATUS.md, training is prohibited until a separate permit; the physical admission of Tank after USB /EIO- is not restored. This document does not remove such prohibitions and is not a permit to start new training exercises or engines. The software, reading of available data, allowed inference and simulation testing without changing weights are allowed. The real testing permits and training campaigns are allowed to obtain individual understandable actions of UI, not for every small program operation.

Design, model, memory, MuJoCo, recording and learning - Homebrain Jetson 16 GB. Mac is a browser/terminal. After initial installation, normal work is local, without external Internet and cloud models. Codex as a tool for development may require the Internet; the complete system should not depend on active Codex session.

The existing ROS 2 surveillance tyre is read-only. Do not turn it into a new motor controller. Old ROS home, drivers, calibrations and desktop panels:8020:8090 are retained. Using isolated copies of the proper controls and documented interfaces rather than runtime-imports of old backend. Do not remove suitable new datasets called "old attempts".

## 1. Outcome and scientific goal

Finish the Explorer to SO-101, ROSMASTER and Hiwonder Tank, which:
1. Receives a common task and selects only existing skills;
2. Exchanges confirmed observations and knows the limitations of each performer;
3. Notes the difficulty and chooses between continuation, additional observation, limited assistance from another robot and human;
4. Checks not only the action of the assistant but also the successful continuation of the specific skills of the recipient;
5. Maintains good and negative experience of assistance and checks its applicability when reused;
6. After authorization, improves selected motor policies based on the quality of their platforms.

Working topic: "General memory of assistance agreed to by the recipient's policy for diverse robots" / Recipient-Conditioned Charized Assistance Meeting for Heterogeneous Robotts.

Main hypothesis: With the same available skills, observations and budgets, checking the compatibility of aid with the current recipient policy reduces harmful interventions and enhances the success of continuing relative memory of similar situations without such verification. Second test: moving A ≤B experience without changing weights B; third, improving self-help behaviour after re-learning on collected corrections.

The architecture of "LLM /VLM + memory + several robots" is not being announced: RoboOS /RoboOS-NeXT is already exploring this structure. PhysMem is already testing memory hypotheses, ActiveAlign is reconciling active perception and further management. Our contribution should be compared to data rather than a new name for modules. Not replace this goal with an endless search for another topic.

Save the previous G rating as a component by expanding the context to the type of assistance, delay and version of the recipient's skills.
- The benefits of helping in an ongoing attempt;
- Transfer of memory records to another recipient;
- The value of the data obtained for further training.

Not to count one successful attempt as proof of causal benefit, but the real robot has no known counterfactive outcomes of one attempt, but in simulations comparable branches are allowed, but they describe a specific simulation assistant, not automatically living.

## 2. Architecture: six roles, not six heavy neuronets

Agents here are limited software roles with tools and state. They are not six independent LLM processes, they are not endless chatter agents and developers changing their code while working. They have one common local model inference service, separate short contexts and clearly limited rights.

### A. MissionCoordination — task manager

It takes to turn a human request into a verifiable sequence of available skills and not to transfer to a human a manual switch of all robots.

Incoming: mission, fresh world image, skills register, current permits, accessibility of performers and memory.
Output: a small TaskGraff with addictions, performers of each step, preconditions, postconditions, deadline and a test method.

He only chooses registered scill_id. He does not invent a capture from Tank, he does not declare an arbitrary command as a new ACT skill, and he does not change the motor policy. If the right skill is not available, he gives a specific missing skill or an available alternative plan. LLM can propose a plan; the tolerance checks the normal code. Do not create several physical plans simultaneously for one resource.

### B. SceneObserver — Agent for Observation and Clarification

We need to combine the available evidence and ask for clarification when one perspective is not sufficient.

Main work: existing YOLO /YOLOE, tracking, dept /IMU/lidar and time tags. VLM is only called for a mixed event for a small selection of selected personnel. Quit: typed observations and relationships with experience_id, time, source, frame_id, quality and status unknown /hypothesis/observed.

He can ask for a new picture or offer a checked observe_from_position. Moving for review is a motor skill through a common performer, not an explicit right of an observer to move a robot. The 2D does not automatically become a 3D position. The ID tracker of one camera is not equal to a global ID object. If no overall calibration exists, maintain local coordinate systems and undefined conformity.

### C. AssociationBroker — A Help Choice

You need to avoid calling a man at every rejection and not to appoint a robot for useless or harmful help.

Entry: short history of the recipient's performance, available risk /progress/AutoIntervene/G- signals, his skills card, cases of assistance found, available assistants and the cost of waiting.
The answer is no more than three admissible candidates -- continue, refine surveillance, perform limited recoupy scill, request a man with short cause and experience_ids.

The G/measurer shall rank the result; the LLM text confidence does not replace the probability. The untrained G is a unavailable, without fictional numbers. The main choice should be a functional fixed baseline. Assistance is only given after checking that the recipient is able to continue from the expected state. If compatibility is unknown, the hypothesis for simulation/authorised diagnosis is not confirmed.

### D. MemorialCurator - Agent of the Audited Memory

Needed to reuse experience between episodes and robots without re-training motor models.

It uses a common local SQLite. Creates links to the original events, groups cases, suggests hypotheses and applicability conditions. It may be short-cut to describe a causal assumption but not to declare it proven. Statuss: candidate, supported_in_scope, negotiated, Stale. Transitions are set by software rules and independent audits, not by LLM decision "I'm sure."

The curator does not edit raw magazines, delete conflicting examples, or change the experimental sample. The fact of rereading the record does not increase the number of confirmations. When changing policy, calibration or camera, the previous application requires a recheck.

### E. OutcomeVerifier - Audit result

We need to make sure that the agent who offered help can't count as a success.

The main test is fixed measurable task conditions and fresh observations. For dock: a pre-defined area, allowed orientation/speed and stopping time using an accessible independent dimension. For a pick-place, the object is inside the given area, the capture has released it and the object is not held by hand. If the stage is not determined by the means, the output of unkown and one simple request to the operator.

VLM is allowed as an additional certificate, not only a ground article, nor an independent second expert if the same model is used. The monitor is allowed to transmit a goal and measurements that are not successful with the coordinator text. The delivery of assistance has been completed/received/the whole task is completed. HTTP 200, exit code 0 and reducing train loss are not physical success.

### F. LearningAndExperitionCurator — Data and Learning curator

Needed to complete the cycle from experience to reproducible and to improve skills.

Checks the design, quality, break-ups and budgets; prepares proposals for the following shows, training and comparisons. Only the existing authorized types of jobs, fixed entry, versions and confirmed budget are started. When learning is banned, only the plan is prepared; weights are not changed. LLM can explain what data are missing but not automatically change loss, break, success criterion or test set.

Individual ACT /SmolVLA remains at their platforms. The Tank does not become a target joint action of SO-101. The memory transfer with frozen balance is first checked; the further training is the next separate experience.

### Non-agent execution loop

The monitors, the controls, the hardware, the blocking of incidents, the limits, the Watchdog, STOP and the permits check are determinated components. They are above any LLM decision. They cannot be replaced by "SafetyAgent", which is reasoned by the text. No LLM in the drive control cycle 20-30 Hz.

## 3. Library and research framework

Don't set up all the projects found.
- Existing Explorer /NiceGUI/FastAPI/SQLite and work line;
- Pydantic for circuitting and checking structured messages;
- A fixed compatible LeRobot for motor policy and data;
- Existing MuJoCo /Playground/Menagerie for simulation;
- Existing YOLO /YOLOE, OpenCV and tracker; SAM3 only if necessary outside the engine cycle;
- Hugging Face smolagents.ToolCallingAgent as the first ready wrapping of limited tool calls, if compatible with a local model backend;
- Existing graph/automatic performer; py_trees only if the necessary interruptions and sequences are not in place. Do not simultaneously add LangGraff, AutoGen, CrewAI, Redis and a separate graph server.

For local LLM /VLM reuse is already proven to be a valid backend. If not available, one first candidate is Qwen /Qwen3-VL-2B-Instruct through compatible Transformers; do not count the quality tool-QXZ or shared memory on Jetson as proven in advance. One documented smaller alternative from available local models is allowed. Do not reset LeRobot environment for the Transformers version: isolated worker if necessary. Do not incorporate the second VLM copy into each role. Do not count VLM balance inside SmolVLA automatically ready dialog service.

ToolCallingAgent is selected instead of CodeAgent: Runtime agent cannot perform a generated Python, Shell, SSH, SQL without restrictions, change the embroidery and install the packages. All tools are registered Python functions over existing API. If the model does not support a completed tool-call template, let's say one small JSON adapter with Pydantic; do not rewrite the format. The format error is a maximum one attempt at correction, then fail without action.

Mandatory re-use table in existing RESEARCH_REUSE.md:

| Source| We're gonna take it to the project.| Checking|
|---|---|---|
| RoboOS / RoboOS-NeXT | Segregation of the overall designer, the skills and spatial and temporal memory register and the design characteristics| The plan uses real capability records, outdated data are not facts; it's an adaptation of architecture, not a transfer of RoboBrain cloud|
| PhysMem | Experience  ♪ Hypothesis ♪ verification; storage of field of applicability and denials| Untested recommendation does not become a permanent rule; transfer of exactly needed modules/logistics with licence|
| RoboMemory | Sharing the world today, history of events and shared knowledge| Learning from experience really changes the choices that are allowed, not just the text of the report.|
| ActiveAlign, arXiv:2610.23378 | Verification of post-observation/posting continuation and collection of suitable continuation| "You can see better" does not mean "policy will continue"; do not set big models for the article|
| Fleet-DAgger | Existing allocation bases and labour metrics| Same waiting/reshuffling cost, not rewrite functions already transferred|
| AutoIntervene / SAFE / ActProbe | Existing monitor and one strong accessible monitor-baseline| Fair designation adapted, same entrances and accessible compute; do not all simultaneously|
| LeRobot HIL | Recording human /policy- segments and returning to policy| Coherence of the fixed version; cleaning of old chunks, correct control transfer|
| MuJoCo branch protocol | Comparable branches of continuation/waiting/help| Image of the whole environment and policy state, lack of true hidden coordinates on online signs|

For each source: accurate publication/version, availability of code, license, file/function used, type of reuse (upstream /ported/protocol), differences and verification. If the non-enclosed copyright code does not declare it integrated. Do not copy the entire repository for one function. No access to cloud API in a ready runtime.

## 4. Peace, skills and memory contracts

Use the migration of the existing SQLite and compact Pydantic models not new distributed OBD. The following names indicate the facts, do not require renaming of the already valid tables.

ObservationEvidence: source /robot/camera ID, sample /frame IDs, source /receive timeamps, boot /clock domain, ege, coordinate system, units, over-schedule /estimated/hypothesis, reference frame/measure, quality evaluation. The number of conferences VLM is not considered to be a calibrated probability.

WorldFact: object/relation, last experience_ids, valid_since /expiry, possible contradictions and unknown. No TF world circot is not a fictional common XYZ. Raw servo radioans cannot be directly considered calibrated URDF jint positions. Maintain existing divided frameworks and ROS-domes.

SkillCard: robot, skill_id, version, learned/scripted/geometric/manual, policy/processor/calibration hashes, action/state schema, permitted targets, entry chambers, area of conditions tested, pre/postconditions, resources, timeout, mode of cancellation and verification, separate tolerance sim/real. The policy, which is trained on a fixed container, does not automatically receive an arbitrary goal from LLM.

The result of the task, the limits of applicability and the negative results is: donor /recipient, reasons for the request, references to status before assistance, version of the recipient's skills, type of assistance, expected impact, actual actions and their origin, actual change of scene, delay/cost, outcome assistant, outcome continuation of the recipient.

Computability Record: What conditions are verified for the recipient, what is unknown, what is the observation, the identity of the policy/cams/calibration; initially these are verifiable conditions and empirical statistics; do not declare the formal "gravity pool" found for several examples.

ExerimentManifest: original memory/hash, scill/policy The following are the following:/validation/test, authorized memory updating, aid limits and independent evaluation procedure.

First retrieval on the Tsk /effect/capability and SQLite FTS5/ filter, then ranking on compatibility. The vector OBD does not enter until proven need. The image or text type does not replace the verification of units, geometry and available actions.

Images, recognized text, recovered memories and other models' findings are data, not new instructions, nor resolution. They cannot include an engine, change limits, or record "access" in the primary journal.

## 5. Implementation of the task and instruments of agents

All roles use a common tool call broker. Minimum set of operations: get fresh observations, read a capability profile, find cases of help, offer graphs, offer help, prepare a scill job, check postcondition, add a memory candidate, prepare a collection/learning plan, request a person. Engine job only through an existing performer after all checks.

For related action, the order is fixed:

fresh snapshot ♪ check the plan and the capacities ♪ safe state of the recipient ♪ reserve the right resources/zone ♪ recheck the requirements ♪ limited scill assistant ♪ check the change ♪ check the conditions of the recipient ♪ discharge of obsolete chunks ♪ authorized continuation ♪ measure the outcome ♪ experience.

Save the TaskGraff dependencies. The completion of the timer or exit code assistant will not automatically unblock the recipient. Do not correct the scene while another robot moves through the same area. Resource grab -- in one fixed order and with deadline; if not possible without deadlock cancel the new request.

Each call receives a request_id, mission_id, current energy, snapshot /evidence IDs, allowed sim /real and validity date. Dubli request_id returns a famous job /status, does not launch a second motion. Do not promise magical exactly-once: after timeout/start, unknown output requires a reconciliation of state, not blind command. The older LLM results are not performed after STOP, a change of robot or a change of world.

The operator allows a specific physical block/mission with limited devices, skills and duration. This is not a permanent permit for any movement. The server startup, new connection, memory recovery and completion of training are never armed with a robot. The crash uses an existing LLM-independent loop.

There is no trusted model solution: a manual control and a proven fixed scenario with fair mark of fallsback is maintained. Maximum 4 model /tool steps for one solution and 2 replans for one reason of failure, then an understandable request to the operator. These are initial engineering restrictions; change them only by measurement, not by test, no final self-checks and recursive calls by agents are prohibited.

## 6. Real resources Homebrain

One loaded high-level LLM /VLM backend; one request at a time. The main roles do not require continuous generation. Use a short state, a limited number of frames and a maximum of 5 relevant memory cases; do not transmit the entire STATE.md and all video recordings to each request.

Check the actual peak RAM /VRAM, circuit frequency, frame age and p50 /p95 delays. Allow joint work to be measured rather than the number of parameters. Start with a small resolution/context and already operating accuracy; quantize only if backken is actually supported on this aarch64 /CUDA- system. Do not beg incompatible bitsandbytes /vLLM.

Not allow memory-consulation, SAM3-marking, new training or batch-stimulation parallel to physical rollout without separate resource application. High level can wait; engine watchdog cannot wait for LLM. For the first option, reasoning is only allowed in authorized safe waiting states. Reserve and measure the influence even of read-only monitoring.

All weights, tokenizer, chat tags, configs, browsers and detector weights are local pinned snapshots. One automatic start-up command for the existing Explorer. No manual YAML, Hub logic, cloud endpoints or remote scripts for normal use.

## 7. Perception and challenges without imaginary possibilities

Do not introduce a new detective network if the existing YOLOE /OpenCV decides the right scenes. The existing tracker is used for each stream; the comparison between cameras is only performed with sufficient evidence. If memory is not compatible with fresh measurement, both of the evidence and the conflict are observed, not the choice of a convenient answer.

The additional camera helps the coordinator/observator first. You can't replace the ACT wrist frame with a Tank image or add the entrances to the saved checkpoint. The changes in the policy input are a new profile version and a separate training.

First related S1 scenario: Assistant specifies position/access to the apparent target; the recipient only starts his tested dock/approach under the conditions fulfilled. If the ability to adopt an arbitrary target is not available, choose a fixed option or explicitly recognize the need for new display. Communication with coordinates without influencing the acceptable plan is not considered joint execution.

S2: The limited geometric /recovery scill restores conditions for further performance of the recipient. First, in MuJoCo. On reality, only when the reach, the geometry of the common area and the lack of collisions are verified. Do not require physical transfer of the object between the floor robot and the desktop hand if height and attachment do not allow it to be fulfilled. In this case, show S1 separately and memory transfer; S2 on the iron honestly observe unsupported geometry rather than simulate.

S3: Another platform uses S1 /S2, checks its own compatibility and continues its skills. Maintaining a complete donor_episode link \memory_case \recipient_episode. Then separately investigate the reverse direction B\A. Different robots performing independent trajectory at the same time are not proof of mutual assistance.

## 8. Simulation and learning remain part of the system

Do not create new duplicates. Use existing SO-101, ROSMASTER arm /base, Tank and fleet_lab_sim. Do not update MuJoCo just for the word "last": check steady release and compatibility, secure the selected; work 4.0.1 and its models do not replace without cause. The calibration of the dynamics and the cameras is separate from the CAD.

Agents cause the same scill contracts in sim and real through different tested adapters. The sim process does not have the default engine devices, real agent currents and real-time rights. Switching sim /real does not carry the permits, data or physical status.

In the branch, maintain the state of MuJoCo, RNG, time, latent /history, action queues, skill phase, memory at the time of the development and the assistant budgets. Continuation / waiting without help / help is given comparable conditions. Hidden true geometry is available only to simulation or to a clearly privileged teacher, not real-compatible actor /observer. If the teacher is privileged, indicate this in each dateset and comparison.

Existing ACT /SmolVLA/Diffusion/PPO does not rewrite. ACT is the main first engine baseline; SmolVLA is an additional tested profile. New neurosnets are not mandatory for each agent. For HIL, re-use compatible LeRobot functions and already available segmentation. Start processors, normalitation and chunk scedulation are mandatory: a valid SO-101 standard does not break for the convenience of the detector.

Mutual learning:
- Observation/memorandry: Information and skills selection changes, weights frozen;
- Data selection: the curator offers suitable segments of his robot;
- :: Training rund: after permission to follow up from the established basic cockpoint;
- Verification: new policy on independent scenes without helper;
- Promulation: The new version is allowed separately, memory with old policy has not been automatically tested for it.

A useful correction can be saved for review even when a general failure occurs, but it does not automatically become a standard behavior call. All selections document. Maintain human /policy/scripted/helper/safety origin and boundaries; act chunks do not cross the source boundary. A new 50-episode set SO-101 does not delete or mix with previous erroneous entries.

## 9. Data for agent research

Do not duplicate the main video. New magazines refer to existing erisode_id /frame_id and heshes.

Write down: sequence of observations and plans, short-checked base of choice, recovered memory IDs, model /prompt/template versions, tool inputs /results, scill /job IDs, delays and resource indicators, owner of team, help/drop, time of person and discharge, test results and version of the politician. No hidden reasoning of the model is required: sufficiently structured solution and performance_ids.

The agent's proposal, the command accepted, the transmission confirmation and the measured motion are different records. The missing Feedback /latency is null with mask, not zero or undirected command. The label is measured_joint_profition default not to be used for an unknown source. The previous correction of the cause of the timetamps does not cancel.

Tsk deadline without execution is task failure on a pre-set protocol; hardware error, user cancellation and unknown output are separate categories. Technical interruptions show by group, do not remove silently from the report. OutcomeVerifier cannot change the train /test or output at the request of the coordinator.

## 10. How to prove good, not just to gather a beautiful demonstration

Prepare one managed protocol, not a dozen unconnected projects, first the fixed-policy experience; the fiine-tune after it.

Comparisons with the same observations/skills /LLM and budget:
M0: fixed rules of cooperation, without LLM.
M1: LLM Planner, memory between episodes off.
M2: Same command with a general episodic memory, without recipient-compatibility filter.
M3: Same memory with conditions for the continuation of the recipient and verification of the actual outcome of the assistance.

All have the same hard safety checks: ablution of compatibility does not mean the failure of physical security. Equalize the number of available memory, donor experiences, attempts and compute or honestly show differences. In M2, /M3 use the same original case library and search conditions; do not give M3 additional cameras without being noticed.

Main metrics: total success, continued beneficiary after aid, share of harmful aid, call-lock, active operator/shift/drop time, autonomous success after re-education. Quality metrics tool calls and grounded plans are diagnostics, not replacement of physical result. "Didn't request a person" is useful only if success is maintained, not when failure is silent.

Check the transfer of A ×B on new episodes and separately B \A. First, the weights B are frozen. For the memory series, a general source prefix and order, the same start snapshots, independent sequences; do not transfer the memory between the pilot groups. For the static comparison memory snapshot is frozen. For online-learning comparisons, the update is allowed, but all the causal sequence is a unit of repetition. Not to count neighbouring frames as an independent sample.

After the pilot, record the size of the study, splits and the basic criterion to test. Do not promise sufficient power for three demonstrations. Simulational success, success scripted helper, success of a person and trained policy to show separately. Without independent measurement of the real outcome, do not declare proven usefulness or universal mutual learning.

## 11. Design and connection sequence

The following are new stages of the agent supplement, not the renaming of the current physical A /B/C.

### AG0 is an integration point, only Homebrain

Save the current work. Keep track of what is already available, what is added and what restrictions are in effect. Do not wait for the inaccessible Tank. Select small modules cognitive-layer/scheme/tool using accepted catalogues; do not confuse them with existing low-level agencies/. Complete the change of current Branch without restarting active physical tasks.

### AG1 is a memory and tool, only Homebrain

Implement types, design, inventory of existing skills, experience retrieval and broker. Use the recorded data and the actual MuJoCo. Check unknown skills, old observation, duplicate requests, owner conflict, rejection of the inaccessible real mode. After this small task, move on, do not build a complete universal ontology engine.

### AG2 Local Intelligence and Through Schematic

Add one model worker and six logical roles. Start one completed S1 /S2 script in a browser simulation: play \\\\\\\\\\\\\\Rememorial re-suspension. Evidence of orchestration can use clearly marked skills; this is not evidence of a trained motor policy. If learning is prohibited, do not start a trainer or approve closing a scientific hypothesis. Show real delay, memory consumption and offline behavior.

### AG3 – ROSMASTER separately

Ask only ROSMASTER if it is not yet available. First, read-only and Shadow: agents watch and offer but do not control. Then a separate authorized set of skills already tested, check raw servo angles/calibrations and confirmation of the outcome. The old Console 8090 does not change. Change owner and return the previous system once in the affected scenario.

### AG4 — Tank separately, mandatory platform

Ask only Tank to be connected at this stage. Save its further development in the plan. First, restore access to the existing scheme, find out why it is not available and check the read-only observation. Do not remove the incandent-block without removing/distinguishing the hardware reason and separately confirming the safe stop. Watchdog on Pi does not guarantee delivery of STOP when the USB is broken. Do not move Tank on charge and do not test the floor until the permitted stand-by device is checked. If you need a physical correction, give one specific instruction; do not replace it with an increase in time-out. To allow, touch agent and simulation, with fair status real acting blocked.

### AG5 — SO-101 separate

Ask the Leader /Follower/wrist when you need this hardware unit. Save calibration and a tested performance contract. The training and replay are not automatically activated. Check Shadow surveillance, record skills, collect results and allow control transfer. Do not require a mandatory new camera for training; additional evaluation is a separate channel and status.

### AG6 — Joint hardware and research

Only after independent tolerances ask for the required pairs, then the entire park. First, joint observations and real transports, then one related task of two robots, then expansion. Three open panels do not mean joint autonomous performance. The unaccepted robot is not excluded from the project, but its dangerous actions are not replaced by READY. If the physical blocker interferes with the couple, the other completed functions are retained, the dependency status is accurate.

The user does not need YAML, terminal piplines and library selection. The only way to use the software is to access, to do a single physical act/check or to allow a particular transaction /physical unit. Do not ask again what has been reported or verified.

## 12. UI Finalization and Final Use

To expand the existing Explorer:8030, not a new site. Add linked pages/billions "Comanda", "Agents", "General Memory", "Assistance and Results", using the style already adopted. Main actions to leave the path clear: choose sim /real and the task, get a plan, allow a permissible launch, see the result. Technical fields are hidden in diagnostics.

Show this selected robot, data source, tolerance level, skill and policy version, short basis for solution with experience, memory found, expected and actual result of help, delay and reason for blocking. Do not make decorative buttons. Unrealized function: NOT_IPPLEMENTED with the designer's task, not "do not set the user." Unaccessible robot or learning ban is a real BLOCKED with an understandable reason.

Check Playwright in a real browser and saved artifacts. A limited list of cross-cutting scenarios is sufficient:
1. Cold offline start: interface and memory available, engines not open.
2. The UI task: The real local model gives a valide plan; unknown scill /robot IDs are rejected.
3. Simulation related scenario: assistance, recipient verification, preservation and review of the case.
4. Re-learning: memory is actually involved in the choice; incompatible version/old position is rejected.
5. STOP/Cancell/Close: Late Model Response and Reclick do not create new action; unknown output after restart is not repeated blindly.
6. VLM error, loss of camera, conflict of resources: fair status and verified fallsback without free movement.
7. Preparation of the train rund: unchanged entrances and lineage; no transferor PID and no change in weights; after a separate resolution, the real trinxave ~ new process reload, not mock.
8. Collection and report: Memory/policy/stage versions are reproducible, the result is not announced on HTTP 200, sim /real and scripted /learned are clearly different.

Each path to check the backend effect and the visible result, not just the availability of the TML. When the defect occurs, correct it and repeat the affected script. Do not change the application in months of new test frames. Moxies check contracts not physics; scripted scill checks orchestration, untrained behavior.

## 13. Quality and volume limits

Simple Python reading, clear types/units, small functions, minimum adapters. Do not use the continuer. Do not copy the insides of LeRobot /Transformers instead of addictions. Do not create a common training framework, an automatic programmer inside the robot and a global code self-change system.

One basic documented integration and one simple alternative to the compatibility block. Then stop the specific component and describe the reason, not change the whole stack. Do not promise fast skills, reducing the science-based learning to smoke, but also do not start a long exercise to check the path of the file.

Save one relevant CURRENT_STATUS.md, STATE.md history, existing RESEARCH_REUSE.md /RESEARCH_PROTOCOL.md/UI_ACCEPTANCE.md and one compact agent contract document. /lock/ tests in Git; weights, images, real keys and magazines locally. The status change is accompanied by an artifact of verification, version and date. "The code is implemented", "checked on records", "verified in MuJoCo", " physically tested", "science effects are established" - different status.

The result of the current phase: what is actually finished, the exact UrL/UI action, which evidence is retained, is one next step. Do not give the following plan for work done and promise an asynchronous continuation without a real process.

Start with AG0 on Homebrain and continue in sequence. The current task is to complete the limited layer of agents over the already created Explorer; not to create a new platform. The user only participates where physically necessary and does not perform manual administration.

## Tested source

When implementing, secure compatible versions and check README/licensing. References are based on the reference, do not require all the lacquers to be installed. Scientific relevance and the results of your own transfer do not follow the source.

1. RoboOS: https://arxiv.org/abs/2505.03673 ; https://flagopen.github.io/RoboOS/
2. RoboOS-NeXT: https://arxiv.org/abs/2510.26536
3. PhysMem: https://arxiv.org/abs/2602.20323 ; https://github.com/haoyangli16/PhysMem
4. RoboMemory: https://arxiv.org/abs/2508.01415 ; https://github.com/SP4595/RoboMemory-Code
5. ActiveAlign / Lock Before You Act (namely, this job is not the same): https://arxiv.org/abs/2610.23378
6. smolagents: https://huggingface.co/docs/smolagents/main/guided_tour
7. Local VLM candidate: https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct
8. YOLO tracking: https://docs.ultralytics.com/modes/track/
9. LeRobot HIL: https://huggingface.co/docs/lerobot/main/hil_data_collection
10. Fleet-DAgger: https://proceedings.mlr.press/v205/hoque23a.html ; https://github.com/BerkeleyAutomation/ifl_benchmark
11. py_trees: https://py-trees.readthedocs.io/en/devel/
12. Playwright: https://playwright.dev/python/docs/intro
13. Ongoing project: CURRENT_STATUS.md, docs /ROS2_COMMON_SYSTEM.md and docs /RESEARCH_REUSE.md in explorer 4.0; take into account more recent changes after this document.
