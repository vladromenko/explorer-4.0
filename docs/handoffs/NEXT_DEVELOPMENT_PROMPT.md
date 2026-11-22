> ** The programme part is replaced by the document `SOFTWARE_AUTONOMY_PROMPT.md` (14.11.2026, the self-contained frame), and the formulas and statistical rules to which he refers remain.

# EXPLORER 4.0 is a detailed article-work assignment

Version 2, 14 November 2026 Founding: `docs/handoffs/RESEARCH_AUDIT_20261114.md`.
The perpetrator is a development agent on Homebrain (Codex /Claude Code).
Self-sufficient: to perform from top to bottom. Each package ends with a commite,
by testing and recording in `STATE.md`.

---

## Part A. How to work with this mission

### A.1. Before the first change (mandatory, ~15 mines)

1. `cd /home/jetsonnx/Projects/explorer-4.0 && git status --short && git log --oneline -5`.
   The uncomplicated files are recorded in the report and not touched.
2. `curl -s localhost:8030/api/health`   ♪ cross-check `process_build.git_head` with HEAD.
   If UI is working with the old version, it is no reason to restart it (see A.2).
3. Read: `docs/handoffs/RESEARCH_AUDIT_20261114.md`, `CURRENT_STATUS.md`
   `docs/RESEARCH_PROTOCOL.md`, last 150 lines `STATE.md`,
   `cat ~/.local/share/explorer3/configs/workflow.json`.
4. Run the basic set of tests (P0) and save the result as a point
   Any new fall after the change is your responsibility.

### A.2. Rigid restrictions (no package removed)

- **Old systems.** SO-101 /WristLab at:8020, Consol:8090, their code, services,
  The following information is available:
  You can't transfer to the old Consol.
- **Tank is a full participant in the study** (user decision)
  14.11.2026: Control corrected after USB 13.11, i.e. charger
  All program work under Tank is permitted: pilot, analysis, sim,
  Sysid, UI. Lock files (`incident-block.json`,
  `stage-c-authorization-suspended-incident.json` ) The agent does not remove:
  They take off step D0 (short check on the counter with the user next to them,
  Recording of USB-off and load voltages.
  U.S.B. - Tank is still in the program and user
  The proposed independent hardware stop (E4) is proposed.
- **Training.** Do not start motor policy training (real and sim), PPO,
  Fine-tune, optimization of hyperparameters and generation of Qwen without explicit authorization
  Allowed: Lock tests, reading
  data, inference already saved by the checkpoints without sending out commands,
  `fit` small G valuers on synthetics in tests.
- **Iron.** Do not open the /USB devices or send commands
  without a user-to-user and without a stage resolution file
  (`configs/rosmaster-hardware-enabled.json`, etc.)
- **General UI:8030.** Do not restart during manual control, recording, or
  Checks - in an isolated UI at a free port (8035-8039) with
  Temporary `EXPLORER3_DATA`I mean, only my own processes, without a broad range of `pkill`.
- **Git.** Commise only your complete changes with the tested `git diff`
  No force-push, no history rewrite.
  `GH=~/.local/share/explorer3/tools/gh_2.103.3_linux_arm64/bin/gh; GIT_TERMINAL_PROMPT=0 git -c credential.helper= -c credential.helper="!$GH auth git-credential" push -q origin main`.
- **Secrets and data.** Do not communicate currents, calibrations, weights, videos, vendor
  Accetes with an unclear license. Data not to be sent outside Homebrain without
  The user's explicit consent.
- **Stats.** IMPLEMENTED ♪ SOFTWARE_VERIFIDE ♪ SIM_VERIFIDE ♪
  HARDWARE_VERIFIDE; separately LEARNED_SKILL_VERIFIDE.
  This is SOFTWARE_VERIFIDE, not HARDWARE_VERIFIDE.

### A.3. Order and priorities

| Priority| Package| Do you need a user?| Evaluation|
|---|---|---|---|
| 1 | P0 Single Test Run| None| 1 h|
| 1 | P1 General pilot SO-101 + Tank (critical defect SO-101)| No, just for final physical inspection.| 1-2 days|
| 1 | P2 Randomization, sessions, counters| None| 0.5 days|
| 1 | P3 Pre-registration and power| To approve the text| 0.5 days|
| 1 | P4 Rewrite analysis (CATE, DR, cross-fitting, transport)| None| 2-3 days|
| 2 | P5 Simulation study on branches| Sim permission for start-up| 2 days of training|
| 2 | P6 Transport sim ~ real for G| None| 1 day|
| 2 | P7 Simulation Identification| Real records| 0.5 days + after recording|
| 3 | P8 Training budget calculation| GPU decision| 0.5 days|
| 3 | P9 Article: skeleton, drawings, data card| None| 1-2 days|
| 3 | P10 Health: disc, documents| None| 0.5 days|

Not to start P5 P9 until P0 P4 is commingled inside the package, small commies.

### A.4. What to do

- Do not add new subsystems, page "for beauty", libraries without a role in
  Agent layer (Qwen, TuskGraph, M0–M3 memory), DART, ROS 2-Shin
  *frozen: */ Defects only.
- Do not change the hypothesis, metric or N after seeing the real data.
- Not to turn aborted into a failure, not throw out uncomfortable episodes, not
  to replace human time with simulation.
- Not to write "first", "proved", "prepared for article" without
  The relevant status and data.

---

## Part B. Scientific design that implements packages

### B.1. Symbols
- Episode i: signs before decision X_i (8 values from `research.FEATURES` and masks),
  A_i \\\\\\\\\0.1} with known probability e = 0.5, output
  Y_i \ {0.1} (access=1, failure=0; aborted – separately, according to ITT, see B.5)
  The value of C_i in seconds measured (human + switch, A=1 only).
- μ_a(x) = P(Y=1 ) A=a, X=x) **G(x) = \(x) = μ_1(x) - μ_0(x)**
  The average effect of the intended assistance (CATE), not the individual mark.
- Decision rule π maps X to {0,1}. Its value is V(π) = E[Y under π].

### B.2. Hypotheses

**H1 is primary in MuJoCo (SIM).
Target ♪ {rosmaster_pick_place_sim, rosmaster_doc_sim}.
So101_pick_place_sim; source for base: Tank_doc_sim.
B \ {0, 10, 20, 50} The rule helps in the share of q = 0.3 of the most situations
Primary contrast:
Δ_H1 = V(π_{G-phys, transfer, B=20}) − V(π_{risk, target, B=20}),
where the risk is the threshold on `tracking_error` calibrated on the same 20 Target--
Secondary: G-phys v G-commands; transfer v. Target-only;
B curve.
In the simulation, each situation has a known outcome (winds continué and
The V(p) is calculated precisely, without IPW.

**H2 is a confirmation, on the iron (REAL), two pairs with a common tanget robot.**
H2a: SO-101 ♪ ROSMASTER Hand (manipulation) ♪ H2b: Tank ♪ ROSMASTER ♪ Base
(`tank_dock`   ♪ `rosmaster_dock` ♪ Mobile Access Original Air Date on October 2, 2013)
are recorded equally; the Hill amendment is two primary contrasts.
The formulas below are for H2a, and for H2b are the same with the replacement profiles.
SO-101 pair ROSMASTER hand.
(source-prior, B.4) on 20 real randomd episodes of ROSMASTER hands,
The original metric is the DR rating.
Δ_H2 = V \_DR(pi_{transfer}) - V\/DR(pi_{target-only}) with q = 0.5 on postponed
N postponed from P3. If power < 0.8,
The result is given as pre-registered pilot with CI, not as confirmation.

If one of the pairs is missing by the deadline, it's given as
pre-registered pilot, second is still supporting.
Why Tank is important: Two different sources (hand and goose base) allow
Show that transport doesn't work for one successful pair of robots, and check
Cross-change "Manipulation ♪ Mobility" (G from SO-101 to ROSMASTER and
G from Tank to hand) as negative control: expected weak or zero
The benefits, which confirms the role of physical proximity to profiles.

**Research (explorator)** cross-crossing between manipulation and
Iron mobility effects (3) "corrections improve subsequent
Autonomous learning" is only in sim, mobile couples, and probability calibration.

### B.3. Evaluations G (all in `explorer4/research_estimators.py`, P4)
1. **T-learner** (current baseline): two `LogisticRegression` in branches.
2. **S-learner**: one `LogisticRegression` on [X, A, A·X] with fixed
   C regularization = 1.0 (data pre-data); ≤(x) = p
3. **DR-learner**: Cross-fitting
   φ_i = μ̂_1(X_i) − μ̂_0(X_i) + A_i(Y_i − μ̂_1(X_i))/e − (1−A_i)(Y_i − μ̂_0(X_i))/(1−e),
   Then `Ridge(alpha=1.0)` ~ X;
4. **Source-prior**: S-learner target with fine
   ♪ ♪ - β_source ♪2 instead of ♪ ♪ ♪ ♪2 ♪ ♪ ♪ ♪ ♪ ♪ ♪ ♪ ♪ 1, 10} is fixed in ♪
   pre-registration; choice.. is the internal leve-one-group-out only for
   Target-training. Implement via `scipy.optimize.minimize` (L-BFGS)
   β is the same as the β.
   They were comparable; it's an artifact.
5. **Risk-baseline**: rule "help if trade_error > t", t selected
   If you're not available, you're not available.
   `command_change` (directly mark).

### B.4 Evaluation of the value of the regulations
- **REAL**: DR evaluation (
  V̂_DR(π) = mean_i[ π(X_i)·(μ̂_1 + A_i(Y_i−μ̂_1)/e) + (1−π(X_i))·(μ̂_0 + (1−A_i)(Y_i−μ̂_0)/(1−e)) ].
  It is also a standardised IPW (already available in `research_value.py`).
- **SIM**: V(pi) = mean_i Y_i(pi(X_i)) on known pairs.
- **Cost.** Report for each rule: aid share, person-second assessment
  ♪ = (% of aid) ♪ (average C y A=1), increase
  (V(pi) - V(never)) / ♪ The missing time is null, not zero.
- **CI.** Cluster buttstrup by contact group (session or scene), 2,000 reruns,
  If groups < 5 - CI do not publish, writing "groups" is not enough.

### B.5 Exceptions and outcomes
- ITT: Analysis of appointment rather than assistance.
  The flag is the flag of `deviation`, and the episode remains in the analysis.
- Aborted, technical cliff, emergency response, a separate table attrition.
  Primary analysis: complete-case on access /failure. Sensitivity: worst-case
  (aborted = failure in branches where it worsens the primary contrast).
- Pre-established criteria for technical exemption (disconnect to
  The decision points, the refusal of the record) are pre-registration. No other exceptions.

---

## Part C. Work packages

For each package: ♪ Why change ♪ ♪ Test ♪ ♪ Reception ♪ Commit ♪

### P0. Single test run

**For what reason.** The 92 PASS report covers 15 of the 56 test files.
Sim tests require `.venv-sim` and `MUJOCO_GL=egl`, otherwise fall on mujoko /GLFW.

♪ What to change ♪
1. `scripts/run_all_tests.sh`:
   - Identify sim-files: those that import `mujoco` or `explorer4.sim`
     (`grep -l` ) plus a clear list of deletions;
   - Main suite: `PYTHONPATH=. .venv/bin/python -m pytest -q -p no:cacheprovider --junitxml=$OUT/main.xml <files>`.
   - sim: `PYTHONPATH=. MUJOCO_GL=egl .venv-sim/bin/python -m pytest ... --junitxml=$OUT/sim.xml <files>`;
   - `$OUT=~/.local/share/explorer3/validation/tests-$(date +%Y%m%d-%H%M%S)`;
   - at the end is a summary of files, tests, pass /fail/error for each venv and
     The list of tests that did not fall into any group (should be empty).
2. Testes that look at iron or models, mark
   `@pytest.mark.hardware` / `@pytest.mark.model_forward` and delete
   default via `-m "not hardware and not model_forward"`, recording
   Markers in `pyproject.toml`.

**Reception.** `bash scripts/run_all_tests.sh`  \0 failed, 0 errors; all 56 files
The group was divided into one group; time ≤ 10 minutes.
**Comm:** `Run every test file in its proper environment`.

### P1. Randomized SO-101 pilot (CRITICAL Defect)

**For what.** SO-101 and Tank are two robot sources for H2a and H2b.
There is, but it has no measured response; it's impossible to have an SO-101 pilot:
- `tank_pilot.accepted_study` rejects any profile other than `tank_dock`, although
  `session.py:68` calls it for everyone;
- `TankPilot.tick` takes `profile('tank_dock')['feature_scales']` for any
  A robot;
- `TankPilot.observe` sets `state_valid=False`, so SO-101 does not
  measured response signs appear, although `hardware.py` gives
  `measured_joint_position`;
- in `session.py` phase `safety` provides `[0., 0.]` (two chassis axles), phase `human` -
  `control.base_action()` (Cyssile keyboard). For a hand, the current one must be retained.
  Positions and correction through Leader;
- in the `HardwareSource(teleoperate=not bool(provider))` test in general
  I don't read Leader.

♪ What to change ♪
1. New `explorer4/pilot.py` (Tank Model)
   Import compatibility):
   - `accepted_study(ident, plan)` checks `study['profile'] == plan['profile']`
     and `plan['kind'] == 'policy'` for profiles
     {so101_pick_place, Tank_doc, Tank_doc_rgbd_lidar}; other checks
     Save;
   - `class Pilot(study, trial_id, session_id, scene, profile_name, adapter)`,
     where `adapter` sets robotic behavior:
     `hold_action(observation)` and `human_action(observation)`;
   - `tick` uses `profile(profile_name)['feature_scales']`;
   - `observe(sample)` saves `state_valid` and `measured_response_kind`
     from sample as it is (Tank has a team of ratings left, and `research.features`
     She's not going to take it.
2. Adaptations:
   - `TankAdapter`: hold → `[0., 0.]`, human → `control.base_action()`
     (behavior as now), plus **measured response**: now Tank
     `state_valid=False`, and G-phys is not counted.
     Toppeaks (like `agents/tank/telemetry_probe.py`, subscription only):
     IMU (burrow) and change in the range of the lear in the front
     sector ± 10°   ♪ `measured_response_kind='imu_yaw_rate+lidar_range'`,
     `state_valid=True` only if both flows are fresh 0.2 s.
     The same signs are in the ROSMASTER base and in the
     `tank_dock_sim` / `rosmaster_dock_sim`, otherwise G-phys transfer between bases
     compares different values;
   - `So101Adapter`: Hold ♪ Last measured position
     (`observation['observation.state']`, hold not to change); human \act
     Leader via the existing `HardwareSource` tractor with phase `aligning`
     (limited team convergence from the follower position to the Leader position, threshold)
     2° /3 ° as in `hardware.py:489` ) The Leader is not in motion
     automatically: The operator himself fails while the follower is standing.
3. `session.py`: In a study-based policy test, open the Leader to read
   (`teleoperate=True`) but as long as the phase `policy` / `resumed`, the Leader teams are not
   The time is changed. `provider.reset()` (clean the ACT chunk);
   `resumed` is a new chunk from the current observation.
   `pilot_phase`, `command_source`.
4. Signal "operator started": for hand, change of position of Leader > 2° from moment to moment
   Notifications, not `abs(action) > 1e-6`.
5. UI SO-101 (test page): phase banner (policy / retention /
   "Your correction, left with N c" / "The politics continues", buttons
   "The Corporation is ready" and "Accident Intervention" like ROSMASTER.

**Texts** (`tests/test_pilot_generic.py`, fairy source /control, without iron):
- `accepted_study` takes so101_pick_place and rejects someone else's cocksum or
  Unconfirmed time-setting;
- SO-101: In the phase of the gold, the current measured position is sent (equality)
  The first phase of the human phase is the Leader team after the convergence, not the instantaneous phase.
  The jump (step ≤ limit);
- The decision elements contain not-none `response_change` and `tracking_error` if
  In the history of ≥ 2 measured frames;
- Tank: Old /human byte-wyte
  `test_tank_pilot.py` passes; the wait for `state_valid=False` in it is replaced;
  with fresh IMU and lidar `state_valid=True` and the signs of non-None response,
  The obsolete flow is `state_valid=False`;
- The segments of LeRobot are divided into `command_source` (policy /safety/human/policy).

**Reception.**
- Isolated UI + Fake SO-101 source: browser script as
  `scripts/check_rosmaster_pilot_browser.py`, both branches, page_errors empty.
- Physical verification is only with the user (Part D, step D2).

**Comm:** `Generic randomized correction pilot for SO-101 and Tank with measured response`.

### P2. Randomization, sessions and group counters

♪ What to change ♪
1. In `static/rosmaster-console.html`, extend `send({action:'trial_start', ...})`
   Add `collection:$('rcollection').value`; in `rosmaster_console.py`
   to be sent to the recorder `record_start`) Similarly, the page
   Test SO-101 /Tank (`collection_id` ).
2. `research.assign` block-redomization:
   - Table `assignment_blocks(study_id, block_key, sequence_json, used)`;
     `block_key = session|scene`; block - accidental conversion [0.0,1.1]
     (`secrets.SystemRandom().shuffle`);
   - `assigned` is taken from the next unused entry; `propensity`
     0.5 remains; add `randomization: 'permuted_block_4'` to the entry
     `block_id`, `block_position`;
   - The block sequence does not enter UI and API until the decision is reached.
3. Pilot page: "Episodes in branches A" counter = 0 /A = 1, independent groups
   (on `connected_groups`), completed and aborted" against target N
   Pre-registration (P3).

**Texts: ** in each of the 4 blocks, exactly two assignments 1; capacity 0.5; different
Session /scene is a different block; repeated assign of the same episode.. error;
`trial_start` without coalition

**Comm:** `Use permuted-block assignment and per-session pilot groups`.

### P3. Pre-registration and power calculation

♪ What to change ♪
1. Consolidate `scripts/research_power.py`    ♪ `explorer4/research_power.py` + CLI:
   - Parameters: N, Q aid percentage, maximum benefit, noise of the evaluator
     (coortion \\\\\\\\\\ with \: 1.0 / 0.7 / 0.05) value valuer (IPW / DR), block valuer
     Randomization;
   - SIM mode: pairs, N situations, determinated branches plus k
     Stochastic repetitions;
   - output: power table and minimum N for 0.8 at the given time
     Suspicions, JSON report from seed.
2. `docs/PREREGISTRATION.md` by Part B: hypotheses, primary
   contrasts, metrics and formulas, q, budgets, raters, grid, rules
   exemptions, attrition, N (from power), stop rule (fixed N,
   No intermediate views on test), list explorator.
   Change in dates.
3. Lock: `research.lock_preregistration()` writes `sha256(PREREGISTRATION.md)` and
   Time in `configs/preregistration.lock.json`. `research.assign` refuses
   if lock missing or hash file changed (need a new lock with entry to
   `analyze` writes hash in `result.json`.

**Texts: ** file change after lock blocks the assign; known power
== sync, corrected by elderman == @elder_man
**Accept:** User read and approved text only after the lock.
**Comm:** `Add preregistration lock and power analysis`.

### P4. Rewrite analysis

**For what.** Now: 10%-holdout total for all profiles (in Target about one)
T-learner on ~5 episodes in branches; silently disappearing options; no DR;
Transport - simple data integration; threshold-baseline is selected by others
robots.

♪ What to change ♪
1. `explorer4/datasets.py`:
   - `grouped_folds(episodes, k, seed)` — K Group Folds
     `connected_groups`, K = min(k), number of groups
   - `grouped_split_by_profile(episodes, test_fraction=.2, min_test_groups=2)` —
     separate final test for each profile; with limited groups
     To return status, not exception.
2. `explorer4/research_estimators.py` (new): `TLearner`, `SLearner`,
   `DRLearner`, `SourcePriorSLearner`, `RiskThreshold` with common interface
   `fit(rows, *, train_groups) / predict_tau(rows) / to_json() / from_json()`.
   Serialization is only JSON (coefficients, medium, scale), without pickle.
   The existing `research.fit` is left as a T-learner wrapper.
3. `explorer4/research_value.py`: add `dr_value(rows, decisions, mu0, mu1)`,
   `rule_top_q(tau, q)`, `cost_adjusted(...)`; group buttstrap since 2000
   I'm gonna go over it again.
4. `research.analyze` (new scheme, old `analyze_v1`):
   - Entry: source profiles /target, budgets B, raters, q from pre-registration;
   - cycle: for each target and B is a sub-sample of target-train fixed
     ♪ Sed by *groups* ♪ training all valuationrs ♪ ♪ Cross-fitting by ♪
     Target-training and final is on Target-test;
   - **Table of all planned cells** (estimator x signs × B ×
     transfer/target-only): status ∈ {completed, insufficient_data(reason),
     No_applicable}; no strings are missing;
   - Primary contrast is marked `primary: true`, the remaining `exploratory: true`;
   - characteristics: `physical`, `commands`, `shared` (overcoming available to
     Source and Target; masks, constant inside the robot, removed;
   - in `result.json`: Hesh pre-registration, hesh photo of decisions, versions
     sklearn/numpy, seed.
5. UI `/research`: First result tabs (one line with CI or
   "data" and "All cells" are not sufficient.

**Text** (`tests/test_research_estimators.py`, synthetics with known \(x)):
- DR- and S-learner restore the sign \ \ to 90% of the points at N=2000;
  A rank correlation with true ≥ 0.6;
- `dr_value` and the normalized IPW are aligned to analytical V(p) (x0.015 at N=2000);
- The source-prior estimate tends to β_source as λ → ∞ and to the target-only S-learner as λ → 0.
- Cross-fitting: No group is simultaneously enrolled in the training and evaluation process
  Its fold (direct check of intersection of session and scene);
- The cell table contains all planned combinations, even on empty data;
- Old `tests/test_research_value.py` and research tests in
  `tests/test_local_workflows.py` passes.

**Commise:** Series - `Add grouped cross-fitting`, `Add CATE estimators`,
`Add doubly robust rule values`, `Report every planned analysis cell`.

### P5. Simulation study on branches (H1)

There are only two outcomes in the sim and the number of situations.
One decision point to report, only `repeat==0` go to G, help is scripted
Previleged DockExpert, no political co-perpetrators.

**Change (preparation, no training).**
1. `explorer4/sim/situations.py`: Situation generator.
   - On every rollout frozen policy: M Decision Points
     Use decision times such as t ∈ {3, 6, 9} s, each with a `continue` and a `correction(d)` branch.
     For d: pre-registration delays; `hold_only`: diagnostics.
   - Struggling after branch: seeded sound
     (`sim.variation`, small amplitude from pre-registration), k = 5 re-entrys ♪
     P(access) of each branch with CI. For a determinized case
     The individual pairing result is retained separately (k = 1)
   - Group = (profile, scene seed, model hash); all points and re-syncs
     Rollout is a group.
   - The signs of a solution are only control-visible history; truth is stored
     The test does not include any particular data (`truth.json`) in the data.
2. Type of assistance in sim:
   - `scripted_expert` (current, previleged – mark);
   - `replayed_human_correction`: from real segments of correction
     (`command_source=human`) the same profile takes a relative trajectory
     The current position is a speed limit.
     No correction - status `waiting_for_real_corrections`;
   - In H1 reports, the type of help is a separate axis, not mix.
3. `sim/rosmaster_sysid.py` / `gain_preparation.sample`: Response Marks in sim
   individual kinds `simulated_joint_position` / `simulated_base_velocity` s
   The actual kinds in one place (`research.KIND_EQUIVALENCE`) are clearly consistent.
   Now, sim pick_place is marked as real `servo_position_readback`.
   `sim/capture.py` for `tank_dock_sim` writes
   `previous_command_estimate_no_wheel_feedback` replace by simulated
   IMU-swimming and lidar range (`simulated_imu_yaw_rate+lidar_range`),
   agreed with `TankAdapter` P1; same for `rosmaster_dock_sim`.
4. Policy choice rule for research (pre-registration): at
   On validation seeds, require a `continue` success rate of 30–70% at the decision point. Outside this range,
   The range is the pre-set stage of complexity (slots,
   The first is a series of tests, which are designed to be used by the user.
5. Status page `/sim/gain`: "Awaiting policy (Abduction permit required)
   "Required for real correction", "prepared".

**Texts:** Re-establishment gives the same result of continue (k=1) in tolerance;
The only difference between the branches of one situation and the assistance assigned is the assistance (diff action before the
Decision points = 0); truth does not enter X; groups do not cross
The whole line is going through the foldami; the political fiction (scripted with noise) is going through the entire conveyor.

**Launching on real policies** only after user permission
The procedure after authorization: ACT sim for 4
♪ ♪ check the success ♪ situation ♪ H1 analysis

**Comm:** `Generate paired simulation situations for intervention value`.

### P6. Transfer of G from sim to real

1. General contract of the characteristics of `FEATURE_CONTRACT_VERSION` (names, units,
   `feature_scales` of the profile, window 3c, is one for sim and real;
   Check when the artifact is loaded.
2. `SourcePriorSLearner` receives β_source from sim artefact (`gain_model`)
   JSON) or real-source.
3. Options for H2a /H2b: sim-only (B=0), sim-prior + 20 real, real-source
   (SO-101 for arm, Tank for base) + 20 real, Target-only 20; negative
   Control is a "legged" source (Tank for hand, SO-101 for base).
4. Test that changing the contract version or the order of the features causes loading to fail.

**Comm:** `Use simulation estimates as priors for real intervention value`.

### P7. Simulation identification

1. After the first real traffic records (Part D):
   Run `PYTHONPATH=. .venv/bin/python scripts/rosmaster_sysid.py` on real
   Catalogue; SO-101 – Playground sysid with a separate set of pathograms;
   Tank is a new `scripts/tank_sysid.py` by the same pattern: command delay,
   constant acceleration time, slip rate of caterpillars to IMU and
   The tank is not calibrated at this time.
2. Apply parameters (`apply_to_env`) only when improving RMSE on Hold-out
   If you do not, you will leave the nominal and write the negative result.
3. Randomization ranges: [P5, P95] by parameters identified
   Individual records extended by 20%; test conditions H1 - separate
   Seed set.

### P8. Calculation budget

1. `docs/COMPUTE_BUDGET.md`: Steps, batch, s/step on Jetson (0.8 for ACT batch 8)
   The watch per profile (E22 h per 100k), priority turn: ROSMASTER,
   SO-101, sim ×4.
2. Prepare, **not start**:
   - 30k steps + validation-loss every 5k, pre-stop
     "The following is the rule for the purpose of the rule:"
   - export setup and configuration for external GPU (`scripts/export_training_bundle.py`,
     The first is to use the user only by decision of the user.
3. Check that the trainer does not occupy the GPU during manual control (already there is).
   The test is the same as the one used for the test.

### P9. Article and data

1. `docs/paper/`: `main.tex` (IEEE /CoRL- template without external downloads),
   `related_work.md` with checked quotations: RESCUE 2610.13516, FARM 2609.11445,
   AutoIntervene 2608.07065, ARMADA 2510.02298, Fleet-DAgger, ThriftyDAgger,
   Sirius-Fleet; causal ML: Künzel et al. 2019 (meta-learners), Kennedy 2023
   (DR-learner), Dudík et al. 2011 (DR policy evaluation), Athey & Wager 2021
   (policy lightning), Bareinboim & Pearl (transportability). Each link to open
   and check the authors and the year; unverified mark `[unverified]`.
2. `scripts/paper_figures.py`: reads only `result.json` (with hashs), builds:
   value of rules against aid share (q-cripple), transfer against B, attrition,
   Time-setting distribution.
3. `docs/DATASET_CARD.md`: Composition, protocol, probability, blocks, timengs,
   The license is `TBD (решение пользователя)`.

### P10. Health

1. Disk (free ~32 GB of 233): `scripts/storage_report.py` - Dimensions
   `validation/`, `cache/`, `pipeline-check/`, `staging/`; proposal for
   - No need to delete anything without the user's consent.
2. Documents: `CURRENT_STATUS.md` rewrite by status A.2; outdated
   The `SYSTEM_HANDOVER.md` "92 PASS" is correct by the reference to P0.

---

## Part D. Physical part (user only)

Each step: create a file to solve... user in a row. short
The script chesslist in UI \ \ return the system to its original state of account \ \ report.

| Step| What| Interpretation| Operator time|
|---|---|---|---|
| D0 | Tank: test on the support (charged, without charger), 5-10 min of normal speed, ≥10 STOP, recording USB-off and voltage; PASS = 0 de-activation and each STOP < 0.4 with \\lock, then 3 short accesses on the floor| 1 session| 30 minutes|
| D1 | ROSMASTER: Re-entry (directions, release, STOP, hidden tab, communication loss)| 1 session| 30 minutes|
| D2 | SO-101 and Tank: acceptance of pilot P1 without policy (replay plan), transfer control (Leader / base remote)| 5 + 5 tests| 45 minutes|
| D3 | 3 test demonstrations for task, reading and checking, then Sysid (P7)| 3 x 4 tasks| 1 h|
| D4 | Main shows: ROSMASTER, ROSMASTER, SO-101, Tank - ≥50 successful, ≥10 series of different locations| 4 × 50+ | 4 x 2 - 3 h|
| D5 | (after training permit) ACT, policy validation at walliation-sets| — | 0 (machine time)|
| D6 | Selection of conditions to success 30-70% under P5.4| 20-30 tests| 1 h|
| D7 | Randomized source episodes (SO-101, Tank) for g-student learning| 2 x N_src from P3| 2 x 1 - 2 h|
| D8 | ROSMASTER and ROSMASTER (B=20) calibration randomized episodes| 2 × 20 | 2 h|
| D9 | Postponed Randomized episodes H2a and H2b (N from P3)| 2 × N | 2 × N x ~2 min|

Rules: Emergency assistance is always more important than re-domination; accident episode
is kept in flag data; new series is new session name; not installed
to name for independence.

---

## Part E. User decisions ( ask one message without blocking P0-P4)

1. Act training permit in MuJoCo for 4 profiles (required for H1).
2. Where to teach: Jetson (E22 h per profile) or external GPU (data leaving
   The number of vehicles is only one.
3. Approval of the scope of article: H1 (sim) + H2a (SO-101 ♪ ROSMASTER) +
   H2b (Tank  ♪ ROSMASTER-Base);
   The agent layer is not the primary analysis.
4. Tank: date of D0 check; if USB is again disabled, shall we put
   A computer independent stop (reel or radio on motor feed).
5. Publication of the data set and code: yes or no, license.

---

## Part F. Reporting and readiness

**After each package** - in `STATE.md` and in response to user:
- What changes (files), what tests are run and with what result(s);
- A.2 status;
- What has not been done and why;
- One more request for the user if you need it.

**Task accomplished when:**
- P0-P4, P6, P9, P10 Communicated; `scripts/run_all_tests.sh` – 0 Failed;
- The SO-101 pilot and Tank are undergoing a browser test on the fairy through the `Pilot` general; physical inspection D2
  Has been implemented or is the first on the list of requests;
- pre-registration approved and blocked by the hash until the first real
  A randomized episode;
- `analyze` on empty real data releases "no data", on synthetics--
  A table of all cells with a known correct answer;
- P5, P7, P8 are prepared, and their status is fair to show what they're waiting for.
