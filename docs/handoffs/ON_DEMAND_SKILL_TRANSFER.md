# CODEX – Explorer 4.0: acquisition of missing skills from another robot

This is a continuation of the existing project, not a new project, nor a return to the old topic "when to continue after correction".

## 1. A goal that cannot be replaced

ROSMASTER receives the task "Find a Cube and Bring it to a specified location." It checks what it knows and what it knows. If it does not know where it is, it requests a search from Tank. If it does not have a proven capture skill, it requests a suitable SO-101 experience, adapts it to its own hand, trains its own policy, tests it and then performs the task itself. At the next similar task, it uses the acquired skill without re-learning.

Differentiate four outcomes:

- **Exchange of observations:** Tank reported where the subject was. The user's motor skills have not changed.
- **Subject properties transfer:** SO-101 measured dimensions. This is useful information, but not yet successful capture experience.
- **Transfer of capture mode:** The recipient used verified object-related movements of another robot through his own controller, which is the transfer of demonstration/parameter, not necessarily training new policy.
- **Acquisition of skills:** ROSMASTER has acquired its own policy of experience with SO-101 and has confirmed self-implementation in new tests.

The main scientific question is, does the targeted request and selection of the experience of another robot reduce the number of self-initiated demonstrations and the time needed by ROSMASTER to master capture? The mere existence of a common map, messages between robots or the size of an object in the instruction not to declare a new skill.

Physically impossible is not a lack of learning; it needs to be rejected, changed, or passed on to another performer, and not run an endless learning.

## 2. From which to continue

Repository: https://github.com/vladromenko/explorer-4.0
The test version for the task is `0078ae6a7033af889e3a3dc619fb7f7a17f33ad8`, `main`, November 16, 2026.

First read the relevant `CURRENT_STATUS.md`, the last section of `docs/TODO_NEXT.md`, `docs/HANDOFF_KNOWLEDGE_GAP.md`, `docs/RESEARCH_ROOT.md`, local HED and uncomplexed changes. Do not turn back to the specified SHA if the local version is newer.

The checked image already shows:

| Component| Use Reuse|
|---|---|
| `knowledge.py` | Knowledge Warehouse, `assess`, `best`, `record_use`, helpers for who /how/skill|
| `swarm.py::_fetch` | Request for information from SO-101 in parallel with search, follow-up with ROSMASTER|
| `so101_station.py`, `so101_vendor/` | Isolated copy of the upper chamber and SAM3 measurement|
| `fleet_agents.py`, `cognitive/` | Agency roles, diagrams, memory, vetted calls and `gap_advisor.py` counselor|
| `rosmaster_arm.py` | Kinematicals and performers, capture with knowledge parameters, downloading approved policies|
| `recording.py`, `datasets.py`, `training_drafts.py`, `jobs.py`, `training.py` | LeRobot, fixed samples, learning plans, one computing line, further education|
| `policy_runtime.py`, `deploy_gate.py`, Skills Register| Single policy launch and tolerance for restricted tests|
| `sim/aligned.py`, `sim/capture.py`, `sim/import_episode.py` | Existing MuJoCo physics, teachers, imports and individual instructions|
| `knowledge_gap_experiment.py`, `knowledge_transfer_mujoco.py` | K0-K4 conditions and already initiated checks on information assistance|
| `/swarm`, `/today`, existing learning page| An interface that needs to be supplemented, not replaced|

In `so101_station.py`, the real `practice()` now measures an object without movement of the arm. In `knowledge.assess()`, the absence of a model now leads to the name "geometric capture", but not to a full-scale skill application. These are the main expansion points if they are not already corrected in the local version.

TODO describes the run-in K0–K4 and MuJoCo series. First, check their actual status; do not run duplicates, do not restart the interface under the running line, and do not change the physics files that read active processes. Do not attribute the planned series to the results already obtained.

## 3. Limitations

The design, data and computations are left on Homebrain. Mac is an existing browser remote remote. Once the relationship is installed, the models and resources of the interface should operate locally without the Internet; a local network with robots is needed.

Do not change or call in the old backland Wristlab/:8020, `so101_autonomous_pick_place` /:8010, Console8090 and CubeBot. If necessary, move the minimum component with a copy to the Explorer with an indication of origin and licence; do not copy the entire old platform. Do not touch their calibration and embroidery.

Save existing data, weights, current tasks, SSD storage and reservation. Do not remove old files automatically. Do not mix tasks "in box", "get up from the floor" and "transfer to the person".

Use the LERobot ACT /SmolVLA and the current line. Do not create a trainer, a second mission control, a second drive manager or a new website. Do not install GR00T, Isaac Sim and a large universal motor model. New relationships are only necessary, with a recorded version, without mass updating of the CUDA /JetPack/ROS/MuJoCo.

Understandable Python, small functions, without `continue`. Optimization after measurements. Do not rewrite the entire project for style.

The software training is done on its own. The existing clearly authorized computing tasks continue in its budget. New heavy training is not allowed without checking the current agreed budget. Real movements, automatic capture samples and changes in hardware tolerances require a valid resolution for specific experience. The model cannot give it itself.

## 4. Step A - Homebrain: This Request for Missing Skills

Expand the existing `knowledge.assess()` and the skills register, do not add a parallel register.

Split up:
- `where_missing`: No new confirmed position of the correct copy;
- `object_properties_missing`: missing object measurements;
- `skill_missing`: no verified performer under proper conditions;
- `skill_uncertain`: The performer exists but conditions are not in the area checked;
- `physically_infeasible`: Mechanic or stage restrictions make action inaccessible.

The existing geometric function is only considered available to the performer in the confirmed application area. The Python function itself does not close the skill gap. Do not turn off the accepted geometric baseline: its choice must be clear and recorded.

Knowledge has been divided into status: measured; seized on donor; transferred and tested in recipient simulation; trained recipient policy; tested on real recipient. `success=None` and LLM's verbal conclusion are not equal to confirmed capture.

Keep an object copy, class and the permissible size range separately. One word "cubic" does not confirm the same properties of all cubes. Unknown error is unknown, not zero.

LLM uses existing `gap_advisor` and limited structured sentences. It can offer an assistant but does not eliminate the lack of skill, mechanical limitations, outdated observation and resolution. Models leave verified rules with error. KnowNo calibrations add only after calibration data are available; do not promise a successful physical capture from the LLM coverage guarantee.

**Acceptance:** In small cases prepared, the system is distinguished by "don't know where", "no skill", "no skill already exists" and "physically impossible." Once acquired, the re-entry does not set the same training in line.

## 5. Phase B - SO-101 as a source of proven experience

First transfer: **go over, take, hold, hold.**. Absolute starting position, home pose and transmission to a person are not carried as a single joint trajectory.

Extension of `SO101Station` by two clear operations:
1. Measure the object — the existing path without movement;
2. To obtain or record successful capture is a new route with valid permits.

First, look for suitable SO-101 entries in the Explorer. Check the old data for completeness, semantics of the task, calibration, time tags and use rights. Do not import them by the name of the folder only. Undergémmetry allows you to extract a reliable piece of the limit; do not make up missing positions.

If data are not available, prepare one simple entry: user puts an object on a safe site, includes existing teleper Leader ≤ Follower and shows capture/upset. First, three test episodes and rereading. Next, a small agreed pilot, e.g. 10–20 general skills shows; sufficient learning not to promise.

Leader, the direct manager of ROSMASTER, creates **-own-scale ROSMASTER** demonstrations, not the knowledge acquired by SO-101.

If you say "SO-101 has learned", there should be a separate checkpoint SO-101 and its own tested attempts. Human shows or a copied geometric program are acceptable sources, but that's what they call it. Do not require a new donor training if there is a proven compatible skill.

For transmission, create a minimum version of the SkillPacket over the existing storage/rester. It contains:
- Donor, source of behaviour (human, policy, geometrical), ID/hesheshes of the original episodes and authorized use;
- A copy/class of the object, dimensions with error, surface type, applicability limits;
- The coordinate system of the object, measured positions of TCP relative to the object, time marks and phase limits;
- The release of sponges in comparable units, direction of approach and rise;
- Checking the retention after lift, not only the closure of the capture;
- Real versions of calibrations/chambers/policy, units and quality of measurements;
- The individual status of the verification by the donor and the recipient.

The object-related position formula: T_object_tcp = inverse(T_world_object) × T_world_tcp. Record the conversion agreement and the object-accounting system at the beginning of each phase. After taking over, the movement of the object with the hand shall not untrap the lift command; the rise is set relative to the support/gravity or a separate target.

Use the available upper camera of the station to measure if it is available and calibrated. Wrist-only the entry of the engine policy can be saved. The additional measuring chamber does not become the input of the model in a rearward way. If the correct position/orientation of the object is not re-established, request specific physical calibration or re-entry.

**Prevent physical magic:** One object is not simultaneously on SO-101 and on the floor before ROSMASTER. Use previous experience or a separately identified similar copy. If you need to move an object to a person, request this clearly and take into account the costs. The station must confirm that it is the appropriate copy that is being measured.

**Acceptance:** One package is visible until a real successful capture of SO-101. For a non-capture package, the system is fair to show a different status.

## 6. Phase C - Transfer package to ROSMASTER

Do not carry raw joint command SO-101 and not serve it directly to ROSMASTER. Do not copy the checkpoint donor as a ready model of the other hand.

The first practical way is to demonstrate object-related adaptations to the existing MuJoCo scene ROSMASTER ♪ new observations and actions ROSMASTER ♪ its own training.

The basis is MinicGen: Object-related sub-tasks, phase boundaries and transformation of the initial demonstrations. First, check the original `MG_EnvInterface` and the required datagen /trajectory. functions. Make the minimum adaptation of the existing environment. If the complete package is incompatible with the current stack, reuse the authorized licensed components or implement a narrow adaptation of the published algorithm with the explicit name `MimicGen-adapted`. Do not install the old MuJoCo stack instead of the working environment and do not give your adaptation for accurately replicating the copyright results.

For each reference trajectory:
1. Re-establish TCP movement relative to object and contact/phases available from the record.
2. Set the object's position on the ROSMASTER stage and get target traffic from its TCP.
3. Build a safe approach to the real starting position ROSMASTER.
4. Decide IK its model, check limits, base contact, impact, achievable, leaps and time.
5. Agree to release the capture by his own calibration, not by the number of SO-101 engines.
6. To perform the trajectory in MuJoCo physics and to maintain the measured states, the actual actions taken and the ROSMASTER images of itself.
7. Independently check the rise and hold; also maintain the causes of the trouble.

Do not impose an arbitrary complete 6D position on a not sufficiently moving hand. Use the acceptable symmetry of the subject, position and direction of approach; record weakened restrictions and deviation from the source. Hand/stage is not required to allow each seizure of the donor.

The table conversion must take into account the support, height, collision and accessibility of the camera. Start with one solid object available to both hands, then add different dimensions and orientations. A sock, cookie and unknown deformable mechanics should not be included as a mandatory condition of the first result.

The preferred geometry of the simulation is allowed to use the teacher and test, and only the entrances that are actually available are given to the policy. The hidden true orientation should not be covered only by the "knowledge from SO-101".

**Accept:** A small set of reference trajectory gives tested ROSMASTER self-images; for each result, a donor episode and transformation are known. There is a clear failure for an impossible option. Do not perform mass generation before this check.

## 7. Phase D - Selection of experience and training of the recipient

The selection shall have a verifiable meaning: task, form/size, approach direction, capture detection, reachability and sustainability of transport in development scenes. Start with clear metrics and ready NumPy /SciPy, not with a new large selection. Selection does not see final test results.

If the donor records are almost identical, you don't promise the advantage of selection. You really need different options for the test; you don't create a known harmful artificial baseline for a positive result.

Use the existing `EpisodeWriter`, import simulation, `datasets.freeze`, `training_drafts`, `Jobs` and official trainer LeRobot. Keep the allowed `command_source`, and indicate the origin of the transfer separately: donor IDs, source of behavior, transformation, version of physics, seeds, method of selection.

Segregate:
- The same is true of the same person as the same person.
- ROSMASTER;
- ROSMASTER demonstrations from SO-101;
- Demonstration of the same ROSMASTER from an already existing simulation expert without SO-101;
- Self-contained tests and failures.

Raw incompatible action /state of different hands does not form a single set. Donor images do not be given as images of the recipient's camera. All derivatives of one source show group in break-up; lineage is taken into account transitively. Final objects/sizes/stages do not participate in calibration, generation or selection. The semantic text of the task is to transmit in the same way when writing, learning and rollout.

SmolVLA remains a basic profile, ACT is a low-cost track check and motor baseline. Do not stop previously authorized training to change the main method. Start with one policy family; connect the second architecture after the first result. ACT without a special modification does not pass on text knowledge.

Adaptation uses its recipient's weight model/same reference model rather than a motor-head donor. First engineering test: preparation of batch. short coordinated learning. Save... reloading by a new process. closed simulation test. This is not yet a demonstration of physical skill.

The heavy tasks go one by one. Check the limits on the actual process of the trainer, not just the script starter. Do not set a universal memory limit that kills the workman trainer without measurements; save the already agreed budget and reserve for /UI. management.

## 8. Stage E — The recipient does acquire skill

Check artifact compatibility, evaluate on development data and in simulation, run shadow evaluation with motors disabled, perform a bounded physical trial with the operator, and register the scope of the accepted skill.

Use the existing `deploy_gate`, but do not declare it a guarantee of success. In scientific comparison, the choice of a particular checkpoint is clearly recorded, not automatically replaced by the newest. All movements remain under the existing restraints and hardware tolerances.

The registered skill must contain a lineage package SO-101, ROSMASTER training, target budget, cell/calibration options and real tests. The next request for the same task uses it without re-adapting if the conditions are appropriate.

Success must be demonstrated by observing the rise and hold, not just by the non-existent servo of capture. Not substitute for failure of neurosisting with geometric correction without separate recording and the specific conditions of the experiment.

To approve "required skill", perform a separate repetition on new development conditions after the donor's online help is disabled. Permanent locally saved parameters from the package are acceptable, but the count must distinguish balance learning from inference with the clue. A non-participant SO-101 should not secretly supply current measurements.

**Reception:** ROSMASTER itself is taking over its own policy; the new skill is available to the next mission.

## 9. Phase F — incorporate on-demand training into an existing mission

Add `_fetch`, `FleetAgents`, `gap_advisor`, current line and `/today` states:

`проверка пробелов → поиск / запрос опыта → выбор пакета → проверка переносимости → подготовка данных → обучение → проверка → готово к испытанию → навык принят → продолжение задачи`.

The training is not required to be placed in a short motor session. For the duration of the training, the mission retains a goal and links to tasks, robots release resources and remain in a safe and consistent state. Restarting the application does not resume. Once the model is received, the permits, object position, charge and stage are rechecked. The old Tank observation is not considered relevant only because it is still in the mission.

Search can go hand in hand with the preparation of experience if there are enough resources. On one GPU computations, STOP does not block and launch two heavy models contrary to the current budget. Time-out of the external task should not leave an uncontrolled stream that will later start moving.

On `/swarm` and `/today`, show by human phrases:
"Don't know where," "no verified capture", "So-101 found", "needs to set an example", "transfer checked", "learning", "waiting to test", "new skill accepted".
A few things are what the user needs and why. The existing buttons do not duplicate.

In the first cross-cutting mission, SO-101 is a teacher, not a mandatory physical recipient of an item. Do not require that it be moved from the dresser to ROSMASTER ≤SO-101. ROSMASTER should deliver the object to a clearly defined, achievable end zone. Only when it is checked that it is "checked", not "taked." The change in the mission's end-state requires a clear choice, not an automatic renaming of success.

**Acceptance:** Target request results in the right information/skill and proven delivery; repeat similar task does not repeat learning. Lack of a suitable source leads to exact request or refusal, not an endless cycle.

## 10. Study: Save K, add separate T

The existing K0-K4, the knowledge of size and comparison of text instructions, are experiments about information aid, do not rename them as motor skills.

Add a separate reproducible plan to acquire the skill:

| Condition| ROSMASTER data|
|---|---|
| T0: target-only | Only k-shows, without SO-101 experience|
| T1: generic-sim | Same k plus same target simulation from the previous expert without SO-101|
| T2: donor-transfer | Same k plus demonstrations converted from good SO-101 experience without targeted selection|
| T3: selected-transfer | Same k and equal generation budget, but the source experience is selected for the recipient's mechanic and mechanic.|

Mandatory T1: Otherwise, the benefits may be explained simply by additional simulation practices. The measured properties of the object/accessible sensors should be the same in the comparable transfer options. Adding numbers to the text is analysed by a single factor, not hidden by the advantage of one method.

Target budget orientations: k = 0, 5, 10, 20. Start with one non-zero budget and a pair of T1 /T2 to confirm the source's usefulness, then expand the matrix on the agreed budget. k=0 does not mean no hardware calibration and verification attempts; their cost is necessarily shown separately. Do not create a new formal result "learning 5 demonstrations" by using hidden additional 50 in the fit/normament.

The 50 ROSMASTER shows themselves are allowed as a super-data baseline and source of input tran-subsets, but not as a mandatory entry for each low-data option. Statistics, simulation calibration and donor selection do not use extra target-demonstrations outside the declared budget; total hardware calibration is counted separately and equally.

Same reference weights, rules of regulation, number of updates, generation budget and test scenes. Maintain all efforts at generation, failure, failures and causes. Warm the dimensions within the same class and leave new physical copies/sizes for verification: the name of the subject should not explicitly give the size.

Main results: Autonomous success of ROSMASTER versus number of self-image; full human time; cost of preparation of source and calculation; frequency of useful/excess requests; re-examining without new training. Donor demonstration not to be considered free. Verification of individual seizures and full mission is divided.

Additional help choice check: coordinates are known/unknown x skill is available/no. Compare simple rules, always request the current LLM counselor; the general set of available helpers and their data are the same. Access to the disabled assistant or hidden sensors is excluded.

Do not announce peer learning only on SO-101 ROMASTER. First show single-directed acquisition. Real reverse transfer will require separate experience; before that, the text will include a general exchange and a single-directed transfer of skills.

Refusal criterion: donor-transfer does not exceed the genetic-sim /target-only in the budget accounting or the choice of source does not exceed the use of all relevant experience. In such a case, show negative transport and its causes, not change baseline in the back.

## 11. Connectivity and final acceptance

1. **Homebrain only:** check active tasks, use their results, prepare a skill request, package, integration of the dataset, simulation adapter, interface and a small non-admission test. No new moves are needed.
2. **SO-101 as part of Homebrain:** unless there is sufficient proven initial experience to request the Leader /Follower and the specific camera to be connected; three test displays, then an agreed source. Tank and ROSMASTER do not need to be activated.
3. **ROSMASTER: ** Check the availability of skills in its model, then with the operator only perform missing physical reading, targeted display and testing. Previously accepted controller does not rewrite.
4. **Tank:** Not to retrain navigation for the article; check changes in the observer role and relevant tolerances. Independent stopping at USB break remains a hardware restriction; it cannot be closed without malfunctioning several trips. Do not reproduce dangerous failure on a moving robot.
5. **Joint mission:** only after separate checks, the old telephone/staff office is returned in the current tested manner.

To interface a small set of Playwright scenarios: request for missing skills; fail for an inappropriate package; turn and cancel; view real artifacts; wait for physical clearance; reuse of already accepted skills. Python unit testes and fairy controllers are not considered physical acceptance.

After each stage, one small committee of its changes and updating of the existing `CURRENT_STATUS.md`, `TODO_NEXT.md`, `RESEARCH_ROOT.md`. Do not produce dozens of conflicting instructions. Do not communicate the unfinished work and change the history of Git.

When you block, name the exact missing amount/interface/physical action and finish independent program points. Do not switch to the new architecture. Do not cross models indefinitely. Do not give a failed training or one successful display for the skills you have adopted.

The final report is: what is implemented; what SO-101 package is actually accepted; how it has affected the data/ROSMASTER model; what tests are performed; what is not confirmed; and one physical instruction to the user.

**First final result:** One verified capture of SO-101 is transformed into a ROSMASTER demonstration in its MuJoCo media with full data origin, followed by its own trained ROSMASTER policy and independent verification of whether the donor has given the advantage.

Start with the state of Homebrain, which is a task to implement the missing path, not another plan of the system.

## 12. Scientific and policy bases

Use as specific components and comparisons, not just links. Check licences before moving the code; save notices, upstream committee and description of changes. Public GitHub does not itself allow any code to be republished.

- **MimicGen (CoRL 2023), object-related demonstrations and transfers.** https://mimicgen.github.io/; https://github.com/NVlabs/mimicgen; https://mimicgen.github.io/docs/tutorials/datagen_custom.html. Author interface requires objects, sub-task phases and team transformation; this is not the ready integration of SO-101 /ROSMASTER. the Original indicates NVIDIA Source Code License, sets — CC-BY 4.0; conditions of specific transferable components to verify.
- **LeRobot ACT /SmolVLA. ** https://huggingface.co/docs/lerobot/main/act; https://huggingface.co/docs/lerobot/main/smolvla. Use the API installed fixed version rather than automatically update it to Main.
- **KnowNo (CoRL 2023).** https://robot-help.github.io/ ; https://github.com/google-research/google-research/tree/master/language_model_uncertainty B. Suitable as a basis for checking the ambiguity of the request; statistical coverage, when assumed, does not replace evidence of physical safety and successful capture.
- **Proactive coalition va autonomous interference (2026).** https://www.nature.com/articles/s41467-026-72797-8. Next-to-be equivalent to calling the participant by need; the very call to Tank not to state new.
- **Silicon Language (present 2026).** https://arxiv.org/abs/2610.07650. Close setting of transferable experience exchange and recipient testing. Do not promise a finished copyright package or exact play without checking the availability of the implementation.

The expected contribution is the measured reduction of target displays through the request, selection and adaptation of the experience of another design with self-checking. It remains a hypothesis until the monitored results.
