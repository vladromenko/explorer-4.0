# ROSMASTER is a separate direction (on course) result

The task is: docs /handoffs/ROSMASTER_NEXT_DIALOG.md (to be used for the main dialogue). Global page=A, hardware_contections=false; hardware sessions without user confirmation were not opened.

## 2026-11-13 16:50 (reading only, SSH)
- ROSMASTER extlorer 192.168.0.177, uptime 4 hours 22 minutes; battery 12.2 B.
- Owner of the seral /dev/ttyUSB0: old rosmaster-bridge (PID 2507); explorer-control /watchdog/camera active; explor3-rosmaster-agent and -camera active; rosmaster-console (8090) active.
- Through the previous /arm_servo_state bridge: all 6 final values (NaN no), ~390 joint/s; position folded [92.7, 193.2, -43.2, 15.7, 89.4, 33.0].
- The developed agent matched the repository (runtime 64217e53, lost_core 9C50830c, control_adapter 227b5b7e, agent 3c0a0329).

## 2026-11-13 17:05 – Controller Re-oriented ARM: EXPIRED Crash
~/explorer3/logs/control-sessions.jsonl (session 185 s, 5522 command): 29 rescission of hand by controller with an unmodified hand held at the lower elbow limit (target 0°, measured -0.2°), then ARM was rejected as EXPIRED  \LeasedCore shut down the session (only NOT_READY goodbye).
Corrected (without weakening STOP /watchdog):
- The objectives of the arms are kept within 1° (NateIO.move_arm, position, mirror leveling);
- EXPIRED on ARM /ARM_ENABLE is considered to be the same transitional state of cancellation as NOT_READY; time (1.5 s) and frequency (30 /10 c) are still limited, other refusals (RANG, etc.) are shutting off the session.
- New test test test_arm_expire_requisition_is_transient_lake_not_ready; scripts /rosmaster_robot_tests.sh is a reproducible test run of an agent on a robot (FakeBoard, no record): 27 PASS.
- Set at ~/explorer3 (agent not launched), reservemintenance /backup-20261113-165119.

## 2026-11-13 17:20 - Recording: causes of termination and origin (§8, §9)
The main dialog has already been corrected and checked: the timeout test   ♪ failure /task_deadline; unknown measured_response_kind ♪nknown; for ROSMASTER (action_time_kind=command_in_force_at_next_agent_snapshot) send_latecy = null rather than 0 (explor3 /timing.py).
Added to the extlorer3 /rosmaster_session.py: termination_reason distinguish between operator_access /operator_failure/operator_abort, operator_stop (STOP, hidden tab, loss of heatbeat), robot_stop (agent himself stopped), hardware_or_network_error, erergency (not rewritten by subsequent break), task_deadline; in the design of each segment of the domain=real, source=human\policy, agent_code_sha256 four agent files. Test test test test /test_rosmaster_recording.py checks these fields (fake agent, 7 PASS together with test_rosmaster_operator).
ROSMASTER is only a research record that is performed by its own agent (/sample.jpg); explor3 /leader8090.py is a separate compatibility with Consol 8090, and rosmaster_session does not import it.

## 2026-11-13 17:45 - Simulation parameters (only reading through the previous bridge)
Completely: Docs /handoffs/rosmaster_measured_params.json (diversified / published / suggested).
- Orbbec camera: 640×480 rgb8, 13.9 k/s; fx=fy=480.71, cx=322.3, cy=245.6; field of vision 53.06° vertical / 67.4° horizontal. models.py and mobile.py (ROSMASTER only), test test test_rosmaster_sim_contacts 2/2 PASS.
- The arm camera (arm4, DCW2_ON_ARM4) is a sim that matches the CubeBot camera; the chassis manufacturer's URDF camera is not used by this robot.
- /odom_raw 49.7 Hz: Speed is the measured encoder (only when encoder_measurement_valid); position is the integral of the measured speed (drife), not integrated command.
- IMU 100 Hz, battery 2 Hz (122 V), lidars 2×6.1 Hz (666 points, 12 metres), ~65 Hz arm feedback to joint, all 6 endpoints.
- The joints limits 1 - 5 URDF = controller calibration; the capture is described in different scales (URDF finger -88.2...0°, controller 30.170°).
Not measured (required traffic recording): drive and capture dynamics, mecanum dynamics, command delay \wheel/drum.

## 2026-11-13 1800 – ROSMASTER phase tolerance
Found: The ROSMASTER panel did not check the global tolerance (stage=A, hardware_constances=false) and could take the robot/activate control. The correction: the action of the acquire /enable/prepare/mirror_on/leader/record_start/trial_start/preset/pair_capture checks the local_work.hardware_allowed('rosmaster'); in phase A, understandable failure, STOP and state reading are not blocked. The exception for ROSMASTER only: configs /rosmaster-hardware-enabled.json {"enable": trie} (Tank /SO-101 does not open; tests /test_rosmaster_gating.py). The live after reset of UI (without active tasks/management): "Insert" \\\tthe failure of phase A, the robot agent remained active. The exception was not created; the user consent is pending.

## 2026-11-13 18:20 - Browser (fixture, no robot)
Scripts /check_rosmaster_browser.py: real Chromium (Playwright of.venv-sim), isolated Explorer at 127.0.1:8036 with temporary EXPLORER3_DATA, fake Scripts /fake_rosmaster_agent.py at 8041 (recorded every request). Real robot and Leader are not activated. The result of the docs /handoffs/rosmaster-browser-acceptance.json, screen shot rosmaster-panel.png:
Acceptance passed for inert startup, acquisition after enabling control, nonzero motion only while W was held, STOP when the tab was hidden, saving a successful 42-frame `rosmaster_pick_place` episode, and the STOP button. No page errors were seen.
Found and corrected as a result: Phase A closed ROSMASTER in three other places (connection(), enabled(), monitor.fetch) without exception, now everywhere local_work.hardware_allowed('rosmaster'). Without exception, the previous behaviour (stage A is closed; local-only is closed).
Not checked by this test: Leader mirror (which would use the real Leader), physical STOP /feedback only with the user.

## 2026-11-13 18:45 - Data chain ♪ plan ♪ kheckpoint ♪ test (without training and without robot)

`scripts/check_rosmaster_flow.py` on isolated data `pipeline-check/20261112-190255` 3 demonstrations for task ready smoke-cheskpoint. `docs/handoffs/rosmaster-flow-report.json`.

- Reading back, order of "surveillance ♪ command", video: PASS for all 6 demonstrations (`rosmaster_dock`, `rosmaster_pick_place`).
- Unchangeable plan of the dataset: Refreezing gives the same sha256 identifier (doc `ffd9c2e9…`, pick_place `d67012a3…`).
- The test plan checkpoint: cha weights are fixed, channel order matches profile, state of `prepared_requires_physical_block`, label "smoke is not skill."
- The policy is loaded on the CUDA and has one action on the recorded frame: final values, dimension = number of channels (3 and 6) The command has not been sent.
- The re-recording plan (61 frames) has been prepared.
- Start: in phase A closed; with the exception of ROSMASTER but without the permission of the plan closed ("Secret physical block"); with the exception and authorization open (check only; temporary files deleted).
- Limit: smoke-checked synthetic tract constants, so policy gives a constant effect -- it's a test of compatibility, not quality.

## 2026-11-13 19:20 - Policy test and browser help pilot (agent simulation)

`scripts/check_rosmaster_pilot_browser.py`:Short Explorer :8037 + Fake-agent :8043, smoke-chescpoint pick_place is copied into temporary DATA, politics thinks on CUDA, action goes only to fake-agent. `docs/handoffs/rosmaster-pilot-browser-acceptance.json`.

- The panel displays the plan and pilot. Start hands control to the policy.
- The branch "help is assigned": the holding banner 1 with : "WAS A CORRECTION... remains 4 s"; there is no policy intervention during the adjustment; "Correction is ready" : policy again./human/policy with general treal_id. Events: request, operator_notified, human_start, human_end, financial.
- The "without help" branch: politics to the end, one segment.
- **Found and corrected:** In the "Armed Intervention", STOP ripped the cycle before the mark was set and the pilot's decision was retained from `emergency=false`. Now `mark_emergency()` is called to STOP: decision and all segments are `emergency`.
- Fake-agent is led to the behavior of the present: the command source is set by the session, the package without `source` does not change it.
- Previous browser check 6 /6 PASS repeated; ROSMASTER tests PASS.

## 2026-11-13 19:50 - Response identification for simulation (prepared for real data)

`explorer4/sim/rosmaster_sysid.py`, `scripts/rosmaster_sysid.py`, `tests/test_rosmaster_sysid.py` (3 PASS) tests.
- Base identification compares commanded velocity with encoder velocity (vx, vy, wz) to estimate delay, time constant and gain, represented as slip in simulation.
- Hand: Target:. readback servo (j1 - j5): lateness, constant time, speed limit.
- Early recording, delayed only estimation; nominal sim, simulation shape and full shape are compared; indistinguishable parameter ranges are specified.
- Synthetic records as real are rejected; the candidate file `DATA/sysid/…` is not automatically applied.
- Fixture: Re-established exact (base delay 0.08 /tau 0.146 /gain 0.80; hand delay 0.06 /tau 0.11 /vmax 90°/s).
- Real catalogue: ROSMASTER traffic records do not yet have a "no 2 traffic records required." Normal receipt shows are sufficient; special "incentive" traffic is not required and, if desired, only agreed.

## 2026-11-13 20:30 - Analysis of Transfer to ROSMASTER: Value of Aid Rules

- `explorer4/research_value.py` (new) + box in `research.analyze`: For each target `<target>-decision-rules` - IPW success evaluation if aid were selected by a fixed rule, on postponed re-delayed episodes: Never / always / threshold of trade_error (threshold only chosen for tran) / risk / G of each option (transfer 0 /10/20, only ROSMASTER, physical and non-physical). The share of aid = proxie human costs, CI for whole groups session/set. Previously, only Brier/calibration reported, not "is G better than the threshold" (§7 general assignment).
- The evaluator is consistent with the analytical truth for 20,000 episodes ( `tests/test_research_value.py` PASS; old research/pilot/trial tests PASS.
- `scripts/check_rosmaster_research_fixture.py`: The entire SO-101+Tank \ROSMASTER analysis is performed on the Fixture Decisions in the Temporary DATA (`rosmaster-research-fixture-400x40.json`; this is not the result of the study).
- **The important conclusion for data collection:** breakup postpones 10% of groups session/position for all robots at once. Even with 400 robot decisions in 40 groups, only 3 groups / 30 episodes were tested, CI very wide. A pilot with ~40 will give 1 postponed group a task and will not distinguish between rules; this is a pilot for the assessment of dispersion, as described in the protocol. The setting (scene) should be changed frequently: one general location/session will bind the entries into one group.
