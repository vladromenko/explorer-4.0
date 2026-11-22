# ROSMASTER conditioned grasp in MuJoCo

A frozen RGB localizer and a target-conditioned trajectory planner lifted the cube and held it in the carry pose for one second. This experiment covers one stationary manipulation skill on one simulated robot. Physical pick success and cooperation require separate trials.

| Planner | Development, 8 scenes | Fresh confirmation, 20 | Historical confirmation, 20 |
| --- | ---: | ---: | ---: |
| LeRobot ACT, projected trajectory | 7 | 15 | 19 |
| LeRobot Diffusion, projected trajectory | 8 | 18 | 20 |
| SciPy radial basis interpolation | 8 | 20 | 20 |
| Vendor inverse kinematics | 8 | 18 | 20 |
| Constant target, ACT | 0 | 2 | 2 |
| Constant target, Diffusion | 0 | 2 | 1 |
| Constant target, radial basis | 0 | 2 | 1 |
| Archived direct-RGB ACT, 25-step action execution | — | — | 6 |
| Archived direct-RGB Diffusion, 10-step action execution | — | — | 1 |

All seven new arms shared the exact reset state, initial camera look, rate limits, and terminal scorer in each scene. The two neural planners learned eight principal-component scores from 32 simulated motor demonstrations (original split 32/4/4, batch 32, optimizer seed 1000). A shared training-only decoder reconstructed 220 native six-servo targets. ACT used 1,000 optimizer updates and Diffusion used 2,000. Both used a previously trained ResNet localizer supervised by 1,024 simulated RGB/XY pairs. The two archived raw-image policies lacked the deliberate look, the extra localization supervision, and the compressed action representation. Their archived initial robot and cube coordinates and physics hash matched. The historical comparison estimates the combined pipeline change.

On the fresh block, the Diffusion planner made bilateral finger contact in all 20 trials and held the cube at the terminal pose in 18. Substituting the mean training target succeeded twice. Sixteen paired outcomes improved and none declined (two-sided exact matched-pair test, unadjusted p = 0.00003052). The frozen simulation observation is a single open-loop look. No physical action was executed. The two permitted real development recordings lacked sufficient camera calibration and a suitable view. The three physical test recordings stayed sealed. [Per-trial CSV](trials.csv) · [Development](development.json) · [Fresh confirmation](fresh.json) · [Historical confirmation](historical_confirmation.json) · [Real archive audit](physical-shadow.json).

## Reproduction on Homebrain

Use the project learning and MuJoCo environments. The [protocol](../../../scripts/grasp_study/protocol.json) declares scene order, observations, controls and fixed training budgets. The [job entry point](../../../scripts/grasp_study/run.py) resolves each stage's interpreter and writes optimizer, decoder, environment, model-byte and RGB hashes. The operator can start the independently identified seed-1001 job from the workspace when ready. The command below targets its own result directories. An interrupted run resumes verified checkpoints and completed trials. A negative development screen completes the job before either confirmation block opens.

```sh
study_data="${EXPLORER4_DATA:-$HOME/.local/share/explorer3}"
.venv/bin/python -m scripts.grasp_study.run --seed 1001 \
  --checkpoint-dir "$study_data/checkpoints/conditioned-grasp-seed-1001" \
  --report-dir "$study_data/simlab/reports/conditioned-grasp-seed-1001" \
  --reference-observations "$study_data/simlab/reports/conditioned-grasp-v1" \
  --workers 2
```

To score existing weights, invoke `scripts.grasp_study.evaluate` with stages `observe`, `plan`, `score`, and `summarize` in that order for each block. Use `.venv-sim/bin/python` for `observe` and `score`, and `.venv/bin/python` for `plan` and `summarize`. Supply `--checkpoint-dir`, `--report-dir`, and `--reference-observations` to each stage. The original raw-RGB comparison uses the two frozen confirmation reports in `simlab/reports/recorded-start-night`. [Original ACT trials](http://192.168.0.168:8030/simlab-media/reports/recorded-start-night/improvement-confirmation-25-trials.json) · [Original Diffusion trials](http://192.168.0.168:8030/simlab-media/reports/recorded-start-night/improvement-confirmation-diffusion-trials.json).

The LAN bundle contains the motor bank, localizer, decoder, policy weights, 48 policy input images, planned actions, paired outcomes, one simulation video and an internal SHA256 manifest. Archive SHA256 is `85e26da30e59836440a11eec75822238344f1dd271879ae4c6a97836bd2cfff2`. [Bundle](http://192.168.0.168:8030/simlab-media/reports/conditioned-grasp-v1/simulation-grasp-bundle.zip) · [Diffusion rollout, seed 940200](http://192.168.0.168:8030/simlab-media/reports/conditioned-grasp-v1/diffusion-940200.mp4) · [Model and protocol hashes](study.json) · [Stationary physical camera check](http://192.168.0.168:8030/rosmaster/grasp-calibration).
