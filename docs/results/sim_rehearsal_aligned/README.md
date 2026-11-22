# Rehearsal of the MuJoCo task of repeating the recording blocks (15.11.2026)

The MuJoCo expert shows 58 SO-101 "transfer", 65 ROSMASTER "take off the floor", and severe re-domination of the appearance. Training via the "SmolVLA" line 5,000 steps, ACT 8,000, batch 8), followed by 20 new scenes by MuJoCo through the robot performer and "Absolution to the robot".

| Objective| Model| Success in MuJoCo| Tolerance| Time of calculation|
|---|---|---|---|---|
| SO-101 gear| SmolVLA | 1/20 (5%) | not allowed| 0.66 s out of 1.33|
| SO-101 gear| ACT | 6/20 (30%) | not allowed| 0.04 s|
| ROSMASTER from the floor| SmolVLA | 0/20 | not allowed| — |
| ROSMASTER from the floor| ACT | 0/20 | not allowed| — |

What does that mean?
- **The full pipeline works** on both arms and both policy families. It covers demonstration capture, training, MuJoCo evaluation through the robot runtime, and the deployment gate. All four policies use the expected robot input and output contracts.
- **Pilot budgets are not enough for these tasks.** ACT for ROSMASTER goes down to the cube (up to 3 cm) and closes the capture, but misses 2–3 cm, and the cube slides out. No mistakes in the conveyor, model unexplored. The primary recipe is 40,000 steps of ACT and 20,000 SmolVLA, plus actual displays.
- **The tolerance has not missed any model, and this is correct:** success in MuJoCo below 50%. For ROSMASTER, there are no real screenings yet. For SO-101, the real show is just an old box problem, so the comparison with them is not about that.
- SmolVLA is set up during the calculation with a reserve (0.76 s out of 1.33).
