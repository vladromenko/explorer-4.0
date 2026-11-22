# Tank: collection of the reason for the re-pick

On November 14, 2026, MentorPi T1 Advanced, Raspberry Pi 5 Model B Rev.1 No movement or training was launched.

## What I saw

When the Wi-Fi /SSH was briefly activated, it appeared on the rapberrypi.local / 192.168.036. Pi reported throttled=0x0; this is the state of power supply Pi, not measuring the motor battery. /dev/ttyACM0 was present, the regular MentorPi and start_node.service were working. The ROS had a battery and set_buzzer. The voltage measurement could not be obtained before physical shut-down; the reason for the bead was not confirmed. The USB incident of the previous session remained open.

The state-owned startup_check.py publishes one signal 1900Hz /0.2 with /repeat1 after 5c and completes ROS. This does not explain the endless repetition without checking the re-start of the process or the MCU self-alert. Previously copied actual send_machine_type sets 6.9B (0x1af4). The general comment SDK "11V (Tank)" contradicts the code and does not justify changing the threshold.

## Automatic collection of next activation

Homebrain is running a temporary user service `explorer3-tank-startup-probe.service`: waits for SSH, then completes three observation windows. It works until the next connection until Homebrain is rebooted; after completion/rebooting, it is clearly restarted. Restarting with active service is not necessary.

Launch command: `systemd-run --user --unit=explorer3-tank-startup-probe --property=Restart=no --property=UMask=0077 /home/jetsonnx/Projects/explorer-4.0/.venv/bin/python /home/jetsonnx/Projects/explorer-4.0/scripts/watch_tank_startup.py`.

Script `agents/tank/startup_probe.py` The SSH is stored, not installed as a service. Once connected, a separate process with a limit of 120 seconds is started; the breakage of the SSCH does not interrupt it. The only record on Tank is the diagnostic log in the system. `/home/pi/.local/state/explorer3/diagnostics/` (0600) which can be read after re-established. Homebrain repeats reading to 180c; re-launch uses a saved path and does not duplicate the collector. Only reading: model/memorial/boot-id, powering Pi, core/USB, the owners of the serial, the regular services and containers, the heshes/thresholds of the installed SDK, subscriptions to the battery and set_buzzer. The users of the ROS, the opening of the serial, service stops, network settings and engine/toummer commands are not available. The unrecoverable voltage remains unavailable, never as a healthy battery. Parts of the data are not available until SSH is available.

Results: `/home/jetsonnx/.local/share/explorer3/validation/corrective-c/startup-watcher.json` and `startup-<boot-id>/` sub-post. The collector does not himself read: at the next user message read these files. The sign of Captured means the measured non-removed cause. If voltage is missing, you cannot lower the threshold or draw a charge.

The reason for the power is first removed at low measured voltage. At normal voltage, the real SDK/winds and the ROS Zummer command are compared, and the re-start of the startup_check is checked. The absence of ROS teams does not prove no alarm on MCU. The movement block after the USB-incident is not removed by the assembler.

## Instructions

All 14 chapters and Appendix from the current English menu are saved.](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/resources_download.html): TML and text in `~/.local/share/explorer3/cache/references/mentorpi-t1-complete/`, URL/Hesh in `docs/tank-reference-manifest.json`No missing pages on the current menu. One outdated cross-reference11-.machine_learning.html returns 404; the existing chapter 10.machine_learning.html is retained./Drive-archives remain referenced; the sources of documentation were not maintained.

[The official](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/1.getting_ready.html) manual describes a single start signal, a charger with a powered charger and a green indicator after the charge is over. It does not establish that any re-weep is mandatory. The full image/source manufacturer offers support with the order number; the letter was not sent, the embroidery was not changed.


## Last activation after green charge indicator

Boot73e0ba5f-1253-48df-bc70-0cd3a9076071: The first entry is received at uptime13.72c; USB1a86:55d4 is present, Pi throttled=0x0, MentorPi only2 is run. During the early picture of the serial is still unoccupied. SSH has been torn to the end of the subscription. Through ~2 the mines were able to read the BOOT-id again, then the connections were completed again timeout. Neither battery voltage nor the source of the re-pick is measured. The absence of the owner for the 14th second does not prove the constant failure of the driver.

The previous assembler was dependent on SSH; the process was corrected for a separate from SSCH with the log on Tank 7loc test, including a real start-up of a separate test process, a retention of the result after the start-up command and a prohibition of re-starting with the same file. The correction has not yet been checked on the checked. The `collection_incomplete` clearly distinguishes the collection break from full observation without voltage. When the next application is checked, the ringtime status of the service should be checked; the clearance of the pen is not promised until measurements are made.


## Measured after correction of charge wire

The operator reported a malfunctioning charge, a non-notice after correction and then turned off Tank for charging.

The collection was found to be double-twinkled: the `/home/pi/explorer3` catalogue belongs to the zoot (new route: the user's own `.local/state/explorer3`); the ROS subscriber from the viewer but has not received the data. The same subscriber received the subuntu battery /IMU/ camera. The call was made to `docker exec -u ubuntu` without a change of name. ROS. Oldcaptured_without_voltage remains a story; the corrected result is `validation/corrective-c/power-correct-user.jsonl` and `factory-telemetry.json`.

`agents/tank/telemetry_probe.py` is a limited 15c subscriber-only image of the camera, internistics, IMU, batteries and lidar. Wheel speed is not being matched by the command; odomintegrated is excluded. When the operator turns off the tank, the next one is not going to perform the new test; the next one is waiting to be rebogged.
