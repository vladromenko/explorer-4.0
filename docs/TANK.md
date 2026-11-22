# Tank is ready to record, R0 - R9 (14.11.2026)

The user's gender-based drive is allowed.
The lockdowns are on Homebrain and Tank with control amounts.
On the admission, not the proof of the hardware removal of the USB incandescent.

The agent is installed with a backup and a check of the original hashs;
After the launch of `armed=false`, `hardware_open=false`. Training and real commands
The new program cycle requires physical verification
The operator in the R8 workshop; separate application on the support is not allowed.

Open: [](http://192.168.0.168:8030/recording/readiness) ♪ [](http://192.168.0.168:8030/recording/check/tank) physical master ♪ [](http://192.168.0.168:8030/recording/collect) collection. Basic profile = `tank_dock_rgbd_lidar`, 20 Hz. Real cameras can be slower: this shows readiness and checks readback.

## What the Programme provides

- Limit on Pi: manual 0.2 m/s and 0.5 rad/s; other sources not higher than
  0.3 m/s and 1rad/s, absolute ceiling 0.6 /2. The regular controller may
  further reduce command; record the actual speed.
- The acceleration is limited to 0.5 m/s2 and 2rad/s2. STOP/discharge/protection gives zeros
  Native TTL 350 ms is independent of Wi-Fi.
- Lidar ± 30° towards the direction of travel: 0.15 m and, when approaching slowly
  ≤ 0.1 m/s - 0.05 m. The free reverse direction is available.
  In the scanning plane, she sees no objects below/up the beam.
- The slope IMU > 20° and voltage < 6.9 V shall stop movement.
  Charging warning. IMU-old /scan prohibits non-zero commands.
- USB loss /EIO completes the loss. Remediation checks only three zeros
  The record; the continuation requires confirmation of "Tank is worth" and a new inclusion.
  The old team isn't repeating itself.
  The engine fee is not open.
- Gamepad /SBUS does not pass over the management of the regular publisher during the Explorer session.

If USB is not available, STOP software cannot physically reach the fee.
`neutral_written` confirms the entry in the serial, not the stop of the caterpillars.
The switch is still required, and this remains the hardware border.

## Sensors, measurement and calibration

RGB /depth/IR, skan, IMU, CameraInfo and accessible cloud retained by previous
The packages are supplemented by the buffer of the IMU /scan, with temporary markings;
This is not a promise to receive all published DDS messages.
The personnel clearly indicate the unit and time of the source.

`observation.state` Tank is still the previous command, not the encoders.
`yaw_rate_imu` and `forward_displacement_lidar` are separate fields.
Two fore-scans are rejected when turning, breaking and bad coincidences;
The moving object is not separated from its own motion.
Sizing odometer.

Read `odom_publisher_node.py`: `/odom_raw` integrates
`linear_x`, `angular_z`; Tank 0.52.
`scripts/tank_calibration_report.py` saves YAML and SHA only in runtime.
Reference and installed YAML are different; parameters were not rewritten.
The user passes the marked meter, the accumulated turn is estimated on IMU.
If the deviation > 10° requires physical calibration according to the official Chapter 3.2:
`ros2 launch calibration linear_calib.launch.py`,
`ros2 launch calibration angular_calib.launch.py`; IMU:
`ros2 run imu_calib do_calib --ros-args -r imu:=/ros_robot_controller/imu_raw --param output_file:=/home/ubuntu/ros2_ws/src/calibration/config/imu_calib.yaml`.
These teams can move robots/resets; the agent has not launched them.

`scripts/tank_health.py` reads CPU, temperature, throttled, flow rates,
HTTP RTT and the last known length of the seral record without sending a test
On the full-time floor, the camera is below 10 frames/s, the red spot,
Not disguised PASS. The loads include the regular joystick_control (~core);
The unusable nodes were not switched off.
The control transfer of the Explorer remains in R8.

## Transfer of management

The `~/.stop_ros.sh` is a public `kill -9` in line of ROS processes.
Instead of launching it, the SIGINT address of the checked bringup launch and
`wifi.service` also opens the Board via SDK, so
The Government has been able to provide the necessary assistance to the Government of the Republic of Korea.
NetworkManager /AP, manufacturing files and embroidery do not change.

---

Below are historical records; previous requirements of eternal lock-down/substitution
replaced by the current R0-R9.

# The & R2 & Setup History

The configuration model: MentorPi_Tank, Raspberry Pi 5, ROS 2 Humble in the MentorPi container. The front Aurora930 issues RGB 640×400: checked read-only via the regular web_video_server. The project does not use the old backend for recording or control. The new rclpy process has not detected the already started DDS-walls after the Wi-Fi switch; a separate camera of the project with a new receiver still requires verification when the resources are transferred.

LeROS2 is studied by committee c8ca08b550a34db1a4e87edaad468f4ad829224a: the factory components and src do not contain Twist adapter. Therefore, the small adapter for the SDK and the chassis formula are used. LeROS2 source code is not copied to the project.

The /home/ubuntu/explorer3 is a self-contained agent within the existing MentorPi. New Python 3.10 venv; Unchangeable System ROS /OpenCV dependencies are used through --system-site-packages, PYTHONNOUSSITE=1 The new Fastapi /uvicorn/serial and the relationships are fixed in configs /tank-agent-requirements.lock.txt. Camera Binarnic and SDK are only on the device and in closed local design, outside Git. Training data, recording decoding, LeRobotDataset, learning and inference are on Homebrain.

## Management and resources

- Port 8041; IP Homebrain restriction /loopback plus separate currents stored outside Git. explorer3-tank-agent.service is installed, active, not enabled. Launch inert.
- The opening requires the resolution of the physical block C, handoff marker of the current load, fresh camera/power. No automatic re-entry. Until the block C is allowed, POST /session returns 409.
- The transmission temporarily stops the flat-detected launch bringup factory via SIGINT, then previously active start_node.service/wifi.service. The state board node at SIGINT sends zeros. /dev/ttyACM0 The Wi-Fi connection is controlled by NetworkManager; the button manager stops wifi.py It's still to be confirmed in the physical unit.
- Helper is launched by a separate time system service: the return will continue at the break of the SSH during the Wi-Fi regular re-connect.
- Return: STOP copies, release of SDK/cams, removal of handoff marker, restoration of previously active services only. Old files are not edited. The conduct of normal launch and return of the phone requires physical verification.
- The command v, omega is limited to the regular ± 0.2 m /s, ±0.5rad /s. Primary Opener keys: ±0.1 m /s and ±0.3rad /s. Signals of the four engine channels, geometry and straight path correction are saved from the installed controller; read ft /right correction = 1.0.
- Local watchdog: TTL commands 350 ms, check every 20 ms; battery freshness 2 s, RGB freshness 500 ms. A new start gives 500 ms before first command. STOP, late, low-power, sensor errors disarm session. HTTP acceptance is not a confirmation of MCU.
- Browser: /WASD arrows or shielded held buttons; release - zero command, /STOP gap - closing; blur /hidden/pagehide/disconnect - Tank stop. SO-101 still allows blur visible tabs but stops at hidden. The robot changes the hold; active session closes first.
- ExecStoppost has limited fallsback zeros only after actual ownership of the current download, and also closes only its own copy of the camera. The emergency completion of the process has not yet been physically verified.

## Data and nutrition

The profile of the tank_doc: target cycle 20 Hz, from RGB 640×400, action=[forward_welcity,yaw_welcity], units=[m /s,rad /s]. Observation.state is the two previous sent commands, obviously command estimates. The encoders are present in the design but the SDK does not provide measured wheel speeds/positions. The plant odom integrates the commands; it is excluded from the measured response. The real IMU/age voltage is retained separately. Raw IMU is not yet approved.

Homebrain and Tank watch are separated. ROS camera stamp, time of receipt by agent, time of availability on Homebrain, both times of dispatch and fact of acceptance by agent. Midpoint /min-RTT is recorded with restriction; it does not make the clock a common scale. The repeat frame is noted. There is no fictional motor acknowledment.

[Hiwonder MentorPi T1](https://www.hiwonder.com/products/mentorpi-t1) indicates 7.4 V, 2200 mAh, 10C. [Getting Ready, 1.3](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/1.getting_ready.html) recommends charge below 6.4 V. In the actual ros_robot_controller_node.py Tank uses 0x1af4 = 6900 mV. Explorer stops below 6.9 V without changing the MCU thresholds or battery. The anti-generic SDK comment on 11 V is not used. The user label is not read; model configuration and measurement is consistent with documented normal power. The charging percentages are not calculated.

## Checked and left

Checked: Wi-Fi after Ethernet was removed; read-only plant chamber/voltage /IMU; copies of SDK and cameras with matching SHA256; inert restar of agent; prohibition of unauthorized session; HTTP UI; 13 software tests including restrictions, TTL, release/shift of robot; Visual browser verification is not available in the current environment.

The following actions by the user are not needed; the current chassis, STOP/loss of communications, three records and train /save/reload, return of the phone. These items cannot be replaced by software tests. The next action by the user is to prepare a free floor area and a visible target with a marked area, close the control on the phone and allow the C block. Other robots are not needed; Ethernet is already removed and not required.

## Historical post-crash recording (replaced R0-R9)

The first motion check was completed by physical FAIL: STOP did not stop Tank on user observation. The straight SDK-adapter described above is replaced by a complete normal circuit; the old description and neutral probe are a training history that does not confirm safety. The current device and restrictions are described in TANK_INCIDENT.md and STATE.md. The motion was blocked before the stand-by; this earlier decision was reversed by the current R0-R9 task.

## Current management (2026-11-13)

The operator confirmed the movement, the break stop and STOP at the normal speed. The stop mode is off, the history of the incident is saved. In the normal interface, Tank only needs "Stop Control", eight arrows and STOP. The connection is performed when the resources are clearly launched; the opening of the page does not move the robot. The return of the phone is in additional settings and is called "Return the Hiwonder application control".

♪/ ♪ They're going forward on the arc, ♪/ ♪ back to the chosen side of the arc, W+A /W +D /S +A /S +D give the same commands. When the video is delayed, the retention commands are dropped. Once the video returns, you have to release and press the arrow again. The loss of browser/communication/power closes the session; the policy and replay also end when the camera is lost.

The recording is available through the Record tab and the general LeRobotDataset. Tank has a replay /ACT via its own agent and the same regular restrictions; each test needs a separate plan resolution. The ACT is kept at zero speed during the calculation. The real three accesses, training, physical skills and return of the phone application are not yet accepted. Long zero checks on transport are not a demonstration of the task.

Checking the new manual conveyor: 1,300 zeros and 613 unique RGBs for 69.91s, without closing the session and failing to release the resources. The camera is not declared uninterrupted: the pause makes the motion zero and requires a new input.


## 2026-11-13: precise installation and official sources

The user confirmed **MentorPi T1 Advanced**, version `41789241655383` with its established Raspberry Pi. The first reference to Starter was replaced by the last clarification. The stored core log has been used by Tank to install **Raspberry Pi 5 Model B Rev 1.1, RAM 8 GB, 4 CPU**: `Memory: 7896288K/8384512K available`. This is a historical check of the set fee, not an evaluation of the free memory today. The indication of the store "Without Raspberry Pi 5" refers to the delivery package and does not limit the current machine. The load is determined by the set fee and subsequent measurements; simulation/training of /inference remains on Homebrain. The clean facts and their sources: `configs/tank-hardware-evidence.json`.

For the dept-camera model, the manufacturer indicates 278×195 x 182 mm, 1.88 kg, RRC Lite, Aurora930 Pro, battery 7.4 B 2200 mAh 10C. The mass of the kit does not replace the measurement of a specific machine with the addition of Pi. The rated voltage is not proven as a secondary shut-off threshold. The actual Aurora930 and RGB 640×400 have been checked previously; the marking of the fixed lidar has not yet been checked.

| What is needed when setting| Official material|
|---|---|
| Complica, power, assembly, connection, application| [T1](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/1.getting_ready.html) commenced work|
| Docker, camera configuration and robot version| [Container and configuration of](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/2.remote_tool_installation_and_container_access.html)|
| Kinematic caterpillars, IMU, linear/angular calibration, speed| [](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/3.motion_control_courses.html) traffic control|
| Lidar and flow checking| [](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/4.lidar_lesson.html) Lidar|
| Deep chamber| [](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/5.depth_camera_basics_course.html) Chamber|
| URDF, `tank.xacro`, SLAM | [](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/6.mapping_courses.html) model and mapping|
| Navigation| [navigation](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/7.navigation_lesson.html)|
| Wi-Fi AP and LAN| [Construction of](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/13.robot_network_configuration.html) network|
| Annexes, tools, getting a full image| [](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/resources_download.html) downloads|
| Public sources are exactly T1| [Hiwonder /MentorPi-ROS, the MentorPi-T1 branch](https://github.com/Hiwonder/MentorPi-ROS/tree/029f66e92eaa789335d3910280ab1963c1e67736)|

The text and the XML of these nine chapters from SHA-256: `~/.local/share/explorer3/cache/references/mentorpi-t1/manifest.json` are localized. This is a reference archive without command and offline copies of all external images/videos. The selected original controller files and model descriptions are couched separately in `cache/source/mentorpi-t1`; the old installed files are not replaced.

**Footnotes are found to be inconsistent:** Official GitHub redirected to `Hiwonder/MentorPi-ROS`; default Branch - M1, therefore it is not appropriate. Even the fixed T1-cloth `029f66e9` contains `ack.xacro` / `mecanum.xacro` but not `tank.xacro` and not `meshes/tank/base_chaais.STL` as described in T1. These models are not being used as a goose. In stage C, first copy the installed `mentorpi_description` package without changing the normal system. If it is not complete, the manufacturer offers a full image/source request with the order number; the letter was not sent on its own.

Documentation contains fragments transferred from other chassis (e.g. Ackermann near `MentorPi_Tank`). Therefore, the reference parameters are checked against the actual branch and model. The USB fall and the inability to deliver STOP remain a separate unclosed hardware incident; the instructions found do not prove it is removed and do not confirm the MCU monitor TTL.
