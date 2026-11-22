# Homebrain vision and comparison of solutions

## Image analysis without training

`/sim/vision`: The frame of a single/total scene or a loaded image \\\\\YOLOE or SAM 3 \\ mask/frame/account. The calculation is going through a total line, SAM 3 awaits GPU. The source and result is saved; no engine commands and automatic addition of masks to the learning.

- YOLOE-26s-seg: Ultralytics 8.4.14, MobileCLIP2. Established weights for official accessories releasing v8.4.0; CLP fork revision is specified in `configs/vision-assets.json`. [Documentation YOLOE](https://docs.ultralytics.com/models/yoloe/).
- SAM 3: Official `facebook/sam3`, revision `3c879f39826c281e95690f02c7821c4de09afae7`, local Transformers 5.5.4. [Official integration](https://huggingface.co/docs/transformers/model_doc/sam3), [Repository and license](https://github.com/facebookresearch/sam3).
- Each file used checks on SHA-256 before analysis. The network is not needed for inference. In Git only manifest and code, not weight. `python -m scripts.cache_vision yoloe|sam3` checks cache; `--download` clearly fills it. SAM requires permission to access and comply with its license; there is no automatic bypass.
- The browser check on one wrist frame: YOLOE missed the Orange cube (0); SAM 3 selected 1. This is a result of a particular frame, not accuracy benchmark. SAM on GPU about 1.76 s after loading, YOLOE CPU about 0.68 s; loading about 12.56 /3.06 separately with this run. Not to consider this as a frequency of the complete control cycle.

## Comparable branches R5

`/sim/branches`: Select Tank /SO-101, diagnostic retention or existing kheckpoint compatible model; set the warmup, delay, budget correction and overall horizon: compare: open the saved report. The training is not started.

This is `R5_protocol_adaptation_v1` on Section 7 of the correction assignment. Do not reproduce the RESCUE /Kintsugi-VLA. Author code.

1. The image contains the regular MuJoCo INTEGRATION state, the redomization parameters, the task state, the controller's delay/filtration, sensor que, RNG and external frozen policy. The policy has checkpoint fingerprint, observation/action sequences, time line if available, Torch /CUDA RNG. The regulation is fixed by the sheckpoint files. The serialization is typed by JSON, without a piccle.
2. Before every branch, the images are read from the disk and recovered. Its full hash must be repeated. Then a comparison is made between the continuation, waiting without help and waiting for the same + limited geometric expert.
3. The waiting control holds the position at the entire delay and correction interval. Both intervenation options drop policy quoes at one line of delay+control; the continuation retains the initial line.
4. Each branch is repeated twice. The /qpos/qvel and the output must be reproduced with absolute error ≤ 1e-9. All retorts/tweets have one lineage /session/split group. This is one independent point, not six independent observations.
5. Inference stops simulation clocks in all branches in the same way; its wall time is recorded separately. Aid constraints are simulation seconds, the real cost of the human being is unknown. When reaching the common horizon, the unfinished task is encapsulated; it is not turned into a reale or calculated the difference in the binary success through it.
6. The expert has a simulator truth. His success does not value the benefit of a person. The hand budget may not be sufficient to complete her full trajectory; this is an honest outcome, not an excuse to extend the assistance without being noticed.

Tested for nytive Tank: one state, six branches, exact replay PASS. When the two branches were diagnosed, the two branches did not complete in 15 s; 5 with a delay of 0.5 c resulted in success in 6.4 s. The policy in this experience was untrained. A separate test checks the re-establishment of the stochastic line of action, not just a fixed controller.

For the existing ACT /SmolVLA/Diffusion, there is a real PolicyClient, but no new physicist chesspoint is available. Old versions are not being used; mechanical acceptance is not given for the result of a lightned-policy experiment. The overall multi-bot scheduler /R3 is not yet included in this individual protocol.

## Checked correction

Only a limited segment of control is kept separate: without waiting and acting policy. If the result of the branch is successful, UI shows the beginning/mid/end and requires a clear view. After this, the source files and lineage are checked, the segment is recorded by the regular LeRobot writer, checked by the official readback. This is the source=control, domain=sim, source=scripted_ext, not human./censored segment not allowed by this route. Re-maintainment is impotent.

Browser intake in a separate DATA: 100 frames at 20 Hz, readback PASS, episode `84ceebb30d5b48e38c4d1a4c2074ec2c`. This is a software test outside the main data catalogue; the training was not performed.

## Diffusion without optimization

The official diffuses 0.38.0 corresponding to the dependency ring LeRobot 0.6.1. `python -m scripts.check_diffusion_inference` Creates reduced upstream Diffusion with random weights, stores model and preprocessors, downloads in a separate process, restores turns/RNG And repeats 10 actions across the new chunk. PASS, CPU Cold Action about 0.123 s. No backward or optimizer. This is a test of a contract, not the quality/speed of a full recipe; the facts are not registered as a trained model.

## Reproduction of checks

- `.venv-sim/bin/python -m pytest -q tests/test_sim_branching.py tests/test_branch_corrections.py` with `OPENBLAS_NUM_THREADS=1 MUJOCO_GL=egl`: 5 PASS.
- `.venv/bin/python -m pytest -q tests/test_policy_recipes.py tests/test_sim_dataset_revision.py tests/test_branch_corrections.py tests/test_local_workflows.py tests/test_contracts.py`: 12 PASS.
- `scripts/check_vision_browser.py`, `scripts/check_branches_browser.py`: isolated UI 8035, real Chromium; external queries and errors no page.
- Both environments are `pip check` PASS. All tests of this re-engineering without the physical robots and without training.
