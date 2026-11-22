# Simulation calculation budget (M0, 14.11.2026)

Homebrain: Jetson Orin NX 16 GB, MuJoCo 4.0.1, mujoco_warp 4.0.1, warp 1.18.
Scripts: `scripts/sim_benchmark.py` (CPU and Warp without graphs),
`scripts/sim_benchmark_warp_graph.py` (Warp with CUDA graft) Raw numbers:
`~/.local/share/explorer3/validation/sim-benchmark-2026-11-14.json`.

| Objective| Physics, step| Control pads| CPU, 1 process| Warp without graph, 64 worlds| Warp + CUDA graph |
|---|---|---|---|---|---|
| Tank dock | 2 ms| 25 (20 Hz)| 976 hp/s (49× real time)| 3.7 thousand physical/s| 2.11 million physical/s in 4,096 worlds (about 84,000 ap/s)|
| ROSMASTER dock | 2 ms| 25 (20 Hz)| 744 hrs/s| 3.7 thousand physical/s| like Tank.|
| SO-101 pick-place | 0.5 ms| 67 (30 Hz)| 338 a.m./s.| 44,000 physicals/s| 0.46 million physicals/s in 1,024 worlds (about 6.9 thousand ap/s)|
| ROSMASTER pick-place | 0.5 ms| 100 (20 Hz)| 177 a.m./s.| 3.0 thousand physicals/s| order of SO-101 expected|

## Conclusions
- Without CUDA graft warp on Orin, it is held back and slower
  The first one is the CPU.
- Decision: PPO teacher is a vector medium that is fully on GPU (Warp + Torch through
  `wp.to_torch`, a step of physics captured in the graph), without copies via CPU.
  The CPU media remain for evaluation, shadow mode, rendezvous and tests.
- The first compilation of Warp kernels is a minute (chash in `~/.cache/warp`).
- :: Volume orientation: Base 100 million control steps in about 20-30 minutes
  Physics; hand: 50 million steps of control for about 2 hours of physics (without network accounting)
  and environmental logic; specify in M6.
