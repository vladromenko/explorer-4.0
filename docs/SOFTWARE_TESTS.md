# Program checks before recording

From the root of the project: `./scripts/run_all_tests.sh`. One group can be started:
`--group main`, `--group sim`, `--group browser`.

All `tests/test_*.py` are distributed in groups in `conftest.py`. Number of files
is calculated from the current tree, not from the old number in the task.
The main tests are `.venv`; simulation regressions are `.venv-sim`, EGL
Training and model generation
Not started: the relevant existing tests have a clear skip with cause.
The number of passes is being isolated, not a successful check.

The browser environment is placed once:

```sh
python3 -m venv .venv-browser
.venv-browser/bin/pip install -r configs/browser-test-requirements.txt
.venv-browser/bin/python -m playwright install chromium
```

Brouser only opens temporary app on `127.0.0.1:8037`; occupied
Port means error, someone's server is not complete.
robots, background performer and automatic model start-up.
Service:8030 does not restart. Each launch uses a separate launch
`EXPLORER3_DATA`; magazines and JUNIT XML are retained in `validation/tests-<UTC>/`,
consolidated JSON - `validation/tests-<UTC>.json` The data catalogue is available in the Exceler.

Hardware is not part of these results. The program PASS does not mean,
I'm sure the robot has physically stopped or the sensor is measuring the distance correctly.
