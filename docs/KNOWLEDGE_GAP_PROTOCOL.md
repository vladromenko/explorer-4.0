# K0-K4 experiment: Conditions and preservation of result

Actor: `scripts/knowledge_gap_experiment.py`, version 2
This is a check of coordination in the two-dimensional room. The width-to-width function is set.
The result does not prove the quality of the physical capture or the trained policy.

| Condition| Mobile participants| Knowledge from SO-101| Selection of gaps|
|---|---|---|---|
| K0 | ROSMASTER | None| Rules|
| K1 | ROSMASTER, Tank | None| Rules|
| K2 | ROSMASTER | Measurement| Rules|
| K3 | ROSMASTER, Tank | Measurement| Rules|
| K4 | ROSMASTER, Tank | Measurement| local Qwen code tested|

The transmission of the virtual SO-101 to the person is the same under all conditions.
"without assistance in finding and knowing capture", not a complete single delivery.
The room coincides with the initial positions, object and location.
Tank doesn't give camera, lidar scans, and doesn't participate in the movement.
He could help K0 /K2 without being seen, even when he was not given orders.

A random error in measuring SO-101 and the estimation of capture has separate streams with seed,
Asynchronous simulation is real time: results
They don't promise a broken play and time depends on the burden of Homebrain.

Each episode is started by a separate process with a separate `EXPLORER3_DATA`.
Network connections are not permitted. Only local reading remains common.
Qwen cache and blocking its resource. The data of real robots are not used as
The memory of the experiment.
Agents, virtual truth and the log of the process, failures and timeouts remain in the denominator.
Successful delivery requires a simultaneous command and actual transmission
The Qwen malfunction with the rules back
is marked `advisor_fallback` to avoid being given the name of the model.

Normal run (one heavy process, after MuJoCo):

```sh
.venv/bin/python scripts/knowledge_gap_experiment.py --rooms 10 --conditions K0,K1,K2,K3
.venv/bin/python scripts/knowledge_gap_experiment.py --rooms 10 --conditions K4
```

By default, one episode is limited to 600 seconds. `--deadline` pre-start
The comparison and the same for all conditions. `protocol.json` stores parameters and hashs.
The originals. `results.jsonl` is written after each episode, `summary.json`
The series is updated immediately; the completed episodes are not counted:

```sh
.venv/bin/python scripts/knowledge_gap_experiment.py --rooms 10 --conditions K0,K1,K2,K3 --resume /absolute/path/to/run
```

The same parameters and code are needed for the continuation. The incomplete attempt is retained,
Re-uses the data. When the code changes, a new experiment begins.
The report has Wilson's success intervals and pairs against K0; mid-point of time.
Successful delivery is separated from the length of all attempts.
The advantage of the method is itself.
