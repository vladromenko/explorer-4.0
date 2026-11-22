# Explorer 4.0 Protocol, Version 1

Date of lockdown: 2026-11-11. Before physical pilot. No public statements.

## Question and value estimated
Working title: "Transfer of assessment of the utility of human intervention between different robots with limited operator time".
The added value of a short history of measured physical response is being tested to transfer the valuer from SO-101 and Tank to ROSMASTER with delay of assistance.
G(h,d)=P(s) = assigned correction after d,h) to P(s) without correction,h.
It's a conditional effect for a group of tests, not known for the counterfactual mark of one attempt.
Priority: max(0,G)/(expected switch + correction). Comparisons are the same turn rules and value accounting.

## Policies and data
Four independent ACTs: so101_pick_place, Tank_doc, rosmaster_doc, rosmaster_pick_place.
Individual actions /state schemas, dataset, train statistics and kheckpoints.
On ROSMASTER, the arms and bases are separated. No unconfirmed channels/synthetic odometers.
Start: 3 real demonstrations, reading batch ~ 50 steps smoke ~ save ~ new process reload /inference without command.
Primary benchmark: 50 quality displays/ Profiles; this is not a promise of sustainable skills.
Split ~80/10/10 for the entire session /scene groups, freeze before training; statistics only train.
When there are few groups, the limitation is clearly shown.
SmolVLA is an additional SO-101 profile on the same splits, after the real forward /backward/reload.

## Diagnostic pilot
Record the checksum of politics, scene settings, acceptable safe points and waiting behaviour (first, Hold).
One random choice for an episode independent of the future: correction / no correction, probability of 0.5.
Direction: ≥20 episodes in each branch per profile for diagnosis and variance estimation, not for power validation.
Retrofit restriction ≤ 10 seconds to specify physically by profile; secure delays to be recorded in advance after pilot.
Maintain destination, probability, real intervention, assignment irregularities, emergency intervention separately.
Record /request/human_control_start/end/deadline, network, line, human response separate; switch, resets, complete cycle and output.
Do not continue the dangerous movement for re-domination. Emergency assistance has priority.
A repeat scene doesn't create exactly a couple of counter-fact states.

## Signs and model
Two small scikit-learn models of success for intervention branches; the difference in projections is the G estimate.
Entrances: Past changes in normalized commands, measured response and residual error where available, sensor age, delay components, available online progress.
The lack of measurement to encode the mask, not by command instead of the Feedback. Command evaluation does not confirm the physical response.
The standard is only for train, source and budget is clearly recorded, compatibility in physical sense, not the motor index.
One frozen ResNet-18 is allowed as a general visual baseline, progress is an estimate, not a true label.
No future footage, episode output or external assessment camera at the online model entrances.

## Transfer
Source: SO-101 + Tank. All ROSMASTER episodes of both modes are excluded from the source of the evaluator's training.
Target: 0, then fixed 10 and 20 episodes of ROSMASTER; compare the Target-only to the same 10 /20.
ROSMASTER is taught separately in its own shows; zero-shot refers only to the evaluator.
To count the total source /target data, the standard and the available sensors. The equal target budget is not equal to the total budget.

## Comparisons
Random/priority choice; risk/progress; G without physical signs; G with them; transfer versus Target-only.
A separate comparison of all robots is made between the sensor set, and delete the explanation of Robot ID/cam/additional data.
For the sceduler-comparison, control policies are frozen.
For learning, each method starts with the same checkpoint, gets equal seconds of help, interaction, and trainer updates. Adjustments between groups are not mixed.
The main outcome of the training is self-contained success in new tests without human beings; assisted access separately.
Three independently trained ACTs as unceertainty baseline are only after value measurement. Repeating the determinized ACT is not uncertainty.

## Report and limitations
Profiles and macro-overage results; human minutes, switching, waiting, resettles, full time; probability calibration; bootstrap CI session/epizodes.
The size of the validation experiment is determined by pilot and recorded to test. Do not change the hypothesis by test result.
Do not claim motor skills or "roman intelligence" for the transfer of the valuer.

Close work: [Fleet-Dagger]](https://proceedings.mlr.press/v205/hoque23a.html), [ThriftyDAgger](https://proceedings.mlr.press/v164/hoque22a.html), [Sirius-Fleet](https://arxiv.org/abs/2410.22689), [ARMADA](https://arxiv.org/abs/2510.02298), [ASA](https://proceedings.mlr.press/v270/akcin25a.html).
RESCUE arXiv:2610.13516: The original and comparison of the novel is not verified; this limits the publication statements, not engineering training.


## Local analysis programme implementation (2026-11-12)

Explor3 module/research.pypage /research. The pilot project is created with a hesh of the chosen policy, but safe delays and decision points require separate physical verification; the project is not allowed to be saved by research or movement. SQLite allows one appointment for an episode and streamlined monotonic event Homebrain. Reset is allowed after the end result point. Foreign monotonic timeamps are not accepted for Homebrain hours.

The signs only use the last three seconds of telemetry already received before the decision. Command/measure changes are normalized to the physical scale of the channels and time so that 20 /30 Hz is not a sign of design per se. The residual error compares the current measurement only to the previous command sent. Command position estimation does not create a measured physical response. Each missing item has a separate mask. The default progress is missing; visual progress or true success is not made.

Two logical responses with StandardScaler are trained by the assigned branch, taking into account the likelihood of a mission. The Emergency /deviations is retained; for the final outcomes, the assignment is not renamed by intervention. Aborted/unknown outcomes are shown as attribution, not hidden by a failure. This is an introduction-to-treat analysis, not a guarantee of causal identification in the event of a failure to release/disruption of protocol.

The initial training excludes both ROSMASTER modes./target-only the same selected 10/20 target episodes; number of source/target If branches/classes are not sufficient, the option is marked as inofficient_data, not replaced by constant probability. The only rule is that each option is tran. Holding-out does not overlap with tran for episode, session or location, including transit links. Bootstrap uses such independent groups. Robot ID is not used./tracking and corresponding masks, is a common sensor set.

The report keeps calibration baskets, Brier on the assigned branch, success on /macro-average profiles, group intervals, actually recorded lengths and number of observations for each time. The missing timeting is null, not zero. As long as there are no actual random episodes, UI explains the lack of data and does not train G at regular demonstrations.

Random /FIFO/risk/G devices are implemented as clean functions with equal switching/correction costs; they do not start robots. Physical comparison of sceduler and subsequent autonomous learning is not complete. Test records are not included in the physical data catalogue.

## Agent assistance: AG2 protocol prepared

- M0: fixed plan without model/interapine memory.
- M1: Local model without interepisode memory.
- M2: Memory with the recipient's compatibility filter disabled.
- M3: memory with accurate testing of skills, cameras, calibration, scenes and domain.

All modes have the same admission, boardship, freshness, cancellation, fixed
Purpose and limits: 4 steps of decision, 1 format correction, maximum 2 re-plannings
In the current complete S1 replanning, no need is needed:
After an error, the gold/undo is performed.

experiment.json: version of the valuer and skills,
scene /model hashes, exact model/configration, seed, frozen memory image,
The diagnostic re-runs have split=diagnostic and clear updates
For the scientific gold-out series, memory must be frozen and the upgrade disabled;
The current `/team` button does not start this series and does not calculate the causal effect.

In S1, the old case changes the acceptable choice of assistant: direct, verified perspective
This still requires a new RGB surveillance.
Help /recipient/task is separated. Target monitoring does not prove the continuation of policy;
Fixed_outcome_verifier estimates actual stop after approach.
is retained as contracted, the recipient is not started./unavailable
The probability of being replaced by a model text is not replaced by a suitable trained artifact.

The current DockExpert is a previleged scripted tagter.
Orchestras and memory, untrained, not transferable VLA, not scientific superiority.
Training, fine-tuning and updating weights are prohibited until a separate permit is granted.
