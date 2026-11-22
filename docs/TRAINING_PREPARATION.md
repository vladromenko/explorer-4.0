# Hand-made training without automatic start-up

Supplement 14.11: The same design has been extended to physical profiles in
`/training/prepare`, instruction: `docs/DATASET_GUIDE.md` and `/datasets/guide`.
The basic physical set retains a minimum of 50 demonstrations and 3 independents
The standard is not mixed with the normal pre-education.
This new part is written but not started.
As instructed by the operator; the former PASS below refers to the simulation path before the change.
The reference amount now includes raw `.npz` sensors.
A plan with the previous hash may require re-training; it is not rewritten.

In `/sim/training`, the user selects the SO /Tank, ACT /SmolVLA/Diffusion, successful display/correction, final number of updates, package size, seed and CPU /GPU. "Preparation the plan" only checks the data and saves the unchangeable document. The control line does not complete the document. The saved document is open after reset; the complete plan is available for download. The form of creation is hidden when you view the plan that is ready so that its current values cannot be confused with the start-up parameters.

The plan captures dataset fingerprints, division of train /validation/test, profile and version of physics. The selected simulation data should give at least three independent groups; the absence of 50 demonstrations does not block a clearly defined small experiment. This is a technical minimum of correct split, not a promise of sufficient data to teach skills. The old physical profile requirements have not been changed.

Start is a separate button with a clear operator mark. Before and before the line is set, the initial data, plan and kheckpoint are rechecked. The recipe calls the official `lerobot_train`; budget and batch are fixed, OOM fallsback is not visible. This work has not pressed the launch: the real training /fine-tune has not yet been achieved.

## Retraining and retention of previous tasks

The selected completed checkpoint of the same profile/model \ new mmutable dataet plan, new optimizer. The reference weights and their preprocessors are fixed by the common file sheches. The old data are included with the new ones; the report shows the number of old and new tran frameworks. Sampling is evenly aligned, without hidden weights /oversampling. The norm is converted to a new tran parts only; this is the true behaviour of the official LeRobot 0.6.1 for non-resume (`lerobot_train.py`, testor states override).

Connected groups are listed by session or scene, transiting. Old groups retain roles: a scene where sheckpoint has already been trained does not become a new gold-out. If a new segment links the previous train to the validation /test, the mixture is rejected. The old control data are retained to check retention; test is not used in tran or choice by walida. Plans of different versions of physics/contracts do not come together silently: the transfer of sim\real remains a separate uncompleted protocol.

Resume is a separate action in a previous interrupted task; it retains the optimizer /scheduler and the same plan. Resume further education is now allowed only as a continuation of the same job ID, not as an invisible mixing of the new initial kheckpoint and the other's optimizer.

## Checked out without training

- 14 testes: roles of old/new groups, rejection of transitive leakage, fixation/change of sheckpoint, budget control, receps, existing workflow /revision checks.
- Browser, isolated DATA: three real simulations from official readback; ACT plan for 1,234 updates, one independent group train /validation/test; saved/swing/reopened. Jobs line pre- and post-op strictly the same, no confirmation of launch, page errors /external HTTP is missing.
- For the browser test, two final scripted Tank docks are recorded at seeds15 /16: 137 /130 frames. This is not learning; the data are in an isolated program application catalogue.

Next, we need a trained politician in the world, an online R3 and a separate sim\real fiine-tune /retention protocol.
