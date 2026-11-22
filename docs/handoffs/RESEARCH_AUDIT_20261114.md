# Explorer 4.0 is a strict audit of research, methodology and readiness.

14 November 2026, Homebrain, verified by a repository `c56066b`
(in `7305589` interface), `~/.local/share/explorer3` data catalogue, code
`research.py` / `research_value.py` / `datasets.py` / `gain_model.py`, protocol
`docs/RESEARCH_PROTOCOL.md`, initial assignment and `SYSTEM_HANDOVER.md`. Tests
The literature is checked 14.11.2026, links at the end.
I'm not going to start the training.

## 0. Five-line verdict

1. **Theme is relevant, niche is not yet occupied.** No work has been found where the evaluation is being conducted.
   *Polia* Human intervention, i.e. conditional causal effect
   (CATE) on real robots with a radiation and where this valuer is moved between
   The next work closes the neighbouring questions: RESCUE
   (value of intervention, simulation only), FARM (delaying)
   Between robots, including SO-101, ARMADA /Fleet-DAgger (operator distribution).
2. **The programme database is strong but scientific, zero.** Randomized
   Episode 0, studies 0, trained politician 0 (smoke only, 50 steps).
   The real success of the show is five so-101 - three, ROSMASTER - one, Tank - one.
3. **Main methodological problem - statistical capacity.** Pilot on
   ≥20 episodes in branches (E40 by profile) gives about 10% chance to see
   The advantage of even the perfect rules of help.
   Randomized episodes per target profile (see §3.1) Comparison "s"
   The physical signs / without them" on the gland are almost impossible.
4. **Transfer plan based on blocked Tank.** Source SO-101
   + Tank ♪ ROSMASTER's target is not being implemented now: Tank is not closed
   STOP /USB. The pair of mobile platforms without Tank does not add up.
5. **The volume has grown.** Agents, Qwen-VL, M0-M3, DART, ROS 2-Shin,
   Fleet distribution is blurring one verified hypothesis.
   Scratch the volume and transfer the main causal part to the simulation where
   The branch of the exact state gives a pair of counterfacts.

## 1. What the study says

Question (`RESEARCH_PROTOCOL.md`): Does short story help *measured *
Response to teams to carry the intervention valuer
G(h,d) = P(s) after delay d, h) - P(s) without correction, h)
With SO-101 and Tank on ROSMASTER with limited operator time? Three effects
Divorced correctly: (1) correction helped in the current attempt; (2) rater
The change in the number of students in the country has been improved.

# What's done well and worth saving #
- Randomization at episode level, recorded probability of assignment 0.5,
  The analysis of the assigned branch (intence-to-treat) without the fiction of the second
  The outcome.
- Signs are only the past until the decision is made; masks of missing measurements;
  command not given for measured response; robot ID is not used.
  Basic version of `commands`, in which the response is hidden: it is shared by all
  A robot with a set of sensors.
- Session/position, standardisation only,
  The fixed hashs, aborted-based-based soils do not turn into failure.
- The value of fixed rules is assessed through IPW on the basis of the intended probability,
  Not just Brier.`research_value.py`).
- Attribution of borrowings (`RESEARCH_REUSE.md`) is honest: "adapted",
  DART-inspired, "not play."

## 2. Relevance and Innovation

| Work| What does| What's different from Explorer|
|---|---|---|
| [RESCUE, 2610.13516](https://www.emergentmind.com/papers/2610.13516) | VLA monitors judge by *value* of alarm rather than accuracy; 128 340 branches, LIBERO| Only simulation, scripted recovery, without human beings and without transfer between robots. **The main competition for "value rather than detective"** needs to be clearly referenced and distinguished by real randomized data.|
| [FARM, 2609.11445](https://arxiv.org/abs/2609.11445) | Redout failure over frozen world model; transfer between PIPER X, SO-101, Franka| He predicts a failure, not a use of help.|
| [AutoIntervene, 2608.07065](https://arxiv.org/abs/2608.07065) | Switching ACT \ Support Memory Operator, Quantile Thresholds| One robot, no code; in Explorer, adapted baseline|
| [ARMADA, 2510.02298](https://arxiv.org/abs/2510.02298) | FLOAT + 1 operator per multiple robot| Detective + distribution, not benefit evaluation; [](https://github.com/Virlus/armada) code|
| [Fleet-DAgger](https://proceedings.mlr.press/v205/hoque23a.html), [ThriftyDAgger](https://proceedings.mlr.press/v164/hoque22a.html), [Sirius-Fleet](https://arxiv.org/abs/2410.22689) | Attention of operator, Rick /novelty| Risk/new priority, not the causal effect of aid|

**Conclusion.** The narrow wording remains open: *and-to-be evaluated
The conditional benefit of real human intervention and its transfer between
"We have not found
The most powerful and rare contribution is the search for the first time.
** Open set of re-domized real interventions with probabilities
It's almost non-existent and it's useful regardless of the sign.
The results.

**What is missing in positioning.** G is CATE and two logistics
The strict reviewer will ask for standard methods:
Met-learners (Künzel et al., 2019, PNAS), Dr-learner (Kennedy, 2023),
Dudík et al., 2011, policy statement on policy
Athey & Weger, 2021, Economica, transportability
The work is done without this terminology.
Looks like an invention.

## 3. Critical methodological issues

### 3.1. Real experiment power (locking)

`scripts/research_power.py` simulates the pilot as: assistance is assigned with
The probability of 0.5 is compared to the target rule.
The real power will be lower **:
The valuer isn't wrong about the model.

| Max. Use of help.| N=40 | N=80 | N=160 | N=320 | N=640 |
|---|---|---|---|---|---|
| +0.2 | 0.06 | 0.06 | 0.11 | 0.21 | 0.30 |
| +0.3 | 0.14 | 0.12 | 0.24 | 0.29 | 0.56 |
| +0.4 | 0.10 | 0.20 | 0.35 | 0.56 | 0.86 |

Protocol ≥20 episodes in branches is a string N=40, about 10% power.
The absolute advantage of the rule is small (+3...+6 p.p.) because the rule and
random choice is the same half of the episode.
Physics" even less, and it needs thousands of episodes on profile.

**Follow-up.** Main causal comparisons (H1, transport, physical abbreviation
The duct is a precise state.
The two outcomes are the same situation, and the variance is lower.
The real experiment is calibration and testing sim-to-real with one in advance.
A second one is the first one that is registered by primary metrics and fairly wide intervals.
the possibility of increasing the number of real episodes by trying short and
The whole thing is a block rendezvous inside the stage.

### 3.2. The chain of preconditions is not fulfilled
- There's no trained policy.
  The decision point should be **intermediate success, approximately 30-70%.**
  0 or 95% benefit of almost constant help. Protocol does not contain a step
  "to select conditions so that success is within this range" and in advance
  The rules of selection are recorded.
- The ACT training on Homebrain is 0.8 s/step, which is an E22 hour over 100k steps and profile.
  Four politicians — about 90 hours. (3) requires more training for each
  The method is from one point, i.e. hundreds of hours.
  Impossible.
- Simulation training is prohibited by the operator.
  In the interim: PPO gives 0 /20, ACT after 50 steps - 0 /3. without such a
  It's a decision.
  user, not engineering.

### 3.3 Transport design
- Tank is blocked, so the source is actually one - SO-101.
  (a) SO-101 ♪ ROSMASTER Hand as the main real pair of manipulators;
  (b) Mobile transport of Tank  ♪ ROSMASTER-base only to simulation while Tank
  Not accepted.
- Sensor masks are a type of robot: Tank does not have encoders.
  `commands` is partially closing this. There is a need for a "one set" option.
  The main sign for the transfer is the source and the tanget.
- Transport now is just a combination of the source and the Target in one bit.
  ♪ strong and standard ♪ ♪ ♪ so the model is like a priori distribution ♪
  For Target: Bayesian or L2-regularization to source-coefficients.
  10–20 targeted episodes make a difference.
- In the "help" part, the "help" is a human being.
  The transfer of G from sim to real mixes the change of the domain and the change of the type of help.
  You need at least one version of help that looks like a human:
  recorded human corrections or teleop in sim.

### 3.4 Statistics in code (`research.py`, `datasets.py`)
1. `grouped_split` is a test 10% group.
   The pilot volumes in the target ROSMASTER are in the test of about one group, and the CI
   Not available. We need to break each profile separately and **cross-fitting
   (Lave-one-group-out)** for evaluation: for small data, it uses everything
   The episodes, not 10%.
2. Under budgets 10 /20 `fit(..., minimum_per_arm=2)` trains 16 entrances (8
   8 masks) ~5 The episode in the branch.
   The results, silently, become `insufficient_data`.
   A few options are selected.
   a polyped model with a "nomination × signs" (S-learner) or
   DR-learner and mandatory reporting on all planned options.
3. The value of the rules is now only estimated by the clean and normal IPW.
   Add **dubly Robus**: When redomined 0.5 it is not mixed and visible
   reduces dispersion.
4. Multiple comparisons: 2 sets of features x 3 budget x transfer /target-only x
   profiles x 5+ rules, and no one primary hypothesis.
   One primary metric, one primary contrast, the rest explorator.
5. The `threshold:tracking_error` threshold is built on the train, which is where the source--
   Robots with a different scale of error.
   Target calibration of the same budget.
6. Decision is taken at a fixed time (`decision_after_s`) rather than at a fixed time
   The evaluation is correct for "t-Search." When you open
   as a planner, requests come at other times, and distribution
   This restriction needs to be written down directly.
7. ROSMASTER (`trial_start` in `rosmaster-console.html` )
   `scene`, but ** does not transmit `collection` **.
   are placed in one automatic session, i.e. one group.
   The collection session field is already on display.

### 3.4a Pilots at SO-101 have not actually been implemented (detected in detail)
- `session.py:68` calls `tank_pilot.accepted_study` for any robot, and that one
  The only pilot receiving is `tank_dock`.
  The available source is rejected.
- `TankPilot.tick` takes `feature_scales` `tank_dock` for any robot;
  `TankPilot.observe` sets `state_valid=False`, so SO-101 won't have
  The response shall be measured.
- In the containment phase, `[0., 0.]` (two chassis axles) is applied, in the assistance phase,
  `control.base_action()` ( chassis keyboard); not in Leader test
  Read (`teleoperate=not bool(provider)`). No hand-to-hand correction through Leader.
- In sim `gain_preparation.sample` marks the manipulator's response with a real type
  `servo_position_readback`. This is a proxie simulation; a clear table is needed.
  The following table shows the number of types of sim- and real types.

### 3.5 Simulation
- ROSMASTER parameters not identified: no real traffic records,
  `sim/rosmaster_sysid.py` is waiting for data. For SO-101 sysid, it's worse.
  The delay error (0.00566 × 0.00595 rad) is not applied.
  No, any sim-to-real statement is a hypothesis.
- The range of re-domization is set by "assemblyd." They need to be narrowed down by real lobes.
  The main series.

## 4. System readiness

| Subsystem| Status| Commentary|
|---|---|---|
| Interface:8030, record, check, LeRobot format, freeze sets| SOFTWARE_VERIFIED | It works, `7305589`, cold start without control|
| Tests| Everyone goes through if everyone goes into their environment.| `.venv`: 199 passed; 9 sim files do not work without mujoko. `.venv-sim` + `MUJOCO_GL=egl`: sim tests (without EGL 3 falls on GLFW). There is no single run. The "92 PASS" supply report covers only 15 of the 56 test files: research, Branching, sim and gain are not included.|
| Randomized pilot (ROSMASTER, SO-101 /Tank via `tank_pilot` )| SOFTWARE_VERIFIDE ON A FEIGHT ASSISTANCE| No real test; `trial_start` without `collection`|
| G analysis, transfer, value of regulations| SOFTWARE_VERIFIDE ON FLISHINGS| Problems §3.4|
| ROSMASTER Iron| Hand-held control accepted earlier; re-update required| The operator's file and presence is required|
| Tank | **BLOKEER** STOP /USB| Need a hardware stop (see §5)|
| SO-101 | Shows are available (3), short replay is needed| — |
| Training| prohibited until authorized; ER22h/ Profile| Computation budget — project life|
| Sim policies with intermediate success| None| Sim is not allowed|
| Disk| 189 /233 GB, free 32 GB| Enough for first sets; `validation/` 4.8 GB and `cache/` 16 GB candidates for transport before mass collection|

## 5. What to do, download or buy

**Programmely, without iron and without training (may be immediately):**
1. Pre-registration document with hypotheses, primary metric, N calculated
   The paper is in every report.
2. Analysis: cross-grouping, profile break-up, DR valuation
   S-learner /DR-learner instead of naked T-learner, transfer through
   source-prior, mandatory table of all planned options.
3. Transfer `collection` to `trial_start`; block redomization inside the session; and
   scenes; independent group counter on the pilot's page.
4. Branch generator in sim for learning G, "Purpose for politics": multiple points
   Re-evaluation of probability, type of assistance "reproduction"
   "The human correction."
5. Power script based on actual pilot data: Recalculate N for
   The main series.

**To download (without infringement of licences):**
- ARMADA code /FLOAT (`Virlus/armada`) as external baseline detector first
  Check LICENSE: article under CC BY-NC.
- Public LeRobot software SO-101 Pick-place with HF Hub just as
  ♪ Opened ♪ ♪ Pre-educate or co-edite ♪ ♪ SO-101 ♪ so that it's faster ♪
  I'm not going to mix it with my own data.
- PDF RESCUE and FARM are for the exact section of Related Work.

**User decisions and costs:**
- Allowing policy training in sim, otherwise most research is not
  It's gonna start.
- Calculation: renting of GPU for ACT, approximately 1 to 3 hours instead of 22 hours per profile.
  This is the output of data outside Homebrain, the only solution that is left to the user.
  The option is a pre-recorded reduction of steps with a validation test.
- Tank: hardware independent stop, e.g. radio or relay-off
  It's more reliable than any other engine that works without Pi and USB.
  Python correction.

## 6. Recommended redrafting of article

**Working title:** "Transferring interference-value estimates across robot
embodiments: randomized real-robot evidence with simulation pre-training».

- **H1 (sim, primary).**G with measured response indicators trained in
  Source-flashes, on a target with a budget of 0 /10/20 is of great value
  rules of assistance per second of person than risk threshold (a) (b) G only
  Team, tanget-only, steam branches, hundreds of situations, CI on stage.
- **H2 (real, confirmer, one metric).** Sim-provided G + 20
  Real calibration episodes of ROSMASTER hands predict the benefits of aid
  Meter is the value of the rule on postponed regedomination.
  The previously declared power is honestly stated.
- **Contribution to data:** Open set of re-domized real interventions
  (3 robots, probabilities, timengs, outcomes).
- ** To remove the agent layer (Qwen, M0–M3, TuskGraff) from this article.
  DART, ROS 2-a-tyre, gland effect (3).
  infrastructure or for separate work.

## 7. Audit based tests

- `pytest tests` in `.venv`:199 passed; errors only in files that need mujoco.
  In `.venv-sim` with `MUJOCO_GL=egl` all sim tests are passed, including
  `test_fleet_execution`, `test_tank_camera_model` and `test_sim_operator`.
- `scripts/research_power.py` is a table of §3.1, reproduced as seed 0.
- Catalogue: 0 studies, 0 decisions, 5 real successes, 7 aborted, 14 sim esiosodes.
