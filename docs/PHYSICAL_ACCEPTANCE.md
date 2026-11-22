# Physical acceptance checks

Open [Fleet readiness](http://192.168.0.168:8030/recording/readiness) and select the movement check for the robot you are using. The check reads sensors while you move the robot from its existing control panel. A pass requires both your confirmation and the measured conditions. A failed step can be repeated after addressing the reason. Results and attempts are saved to `validation/physical/<robot>-<UTC>-<id>.json`. A saved check does not change approvals in `fleet.json` or start another movement.

| Platform | Checks |
| --- | --- |
| [Tank](http://192.168.0.168:8030/recording/check/tank) | Four directions for two seconds each, release, STOP, one metre straight ahead, lidar with a box in front, tab switch without resumption, RGB, depth, lidar, IMU and a short demonstration. |
| [ROSMASTER](http://192.168.0.168:8030/recording/check/rosmaster) | Clear area and unplugged charger, four base directions, release and base STOP, each arm joint and the gripper, arm STOP, tab switch, RGB, depth, both lidars, IMU and a short demonstration. |
| [SO-101](http://192.168.0.168:8030/recording/check/so101) | Hand over from port 8020, wait for the arms to align, check all five Leader-to-Follower joints and the gripper, STOP, tab switch without resumption and a short demonstration. |

**Tank.** Stay beside the power switch. If USB disconnects, a closed control session does not show that the robot has stopped. Once communication returns, verify the robot is stopped and explicitly enable control again. Confirm the charger is disconnected. A full battery can read above 8.3 V. The controller still checks fresh power telemetry and its minimum voltage. If the integrated IMU yaw changes by more than 10° over the straight one-metre check, the wizard recommends the manufacturer's calibration procedure.

**SO-101.** The handover stops the earlier service. Returning control releases Explorer's resources, starts the earlier service and checks its response. Secure the arm, camera, cube and box on the table.

**ROSMASTER.** Use the built-in panel with the port 8090 control service stopped. If using the optional Leader mirror, hand over the Leader first and check elbow direction, grip and smoothness visually. Lighting, microphone and display are outside the four-task acceptance checklist.

Record a short demonstration and wait for automatic readback. Review the video before recording the main series. The system keeps failures and aborts available for review. [Dataset collection](http://192.168.0.168:8030/recording/collect)

Shared mapping, external camera calibration and autonomous fleet tasks have separate acceptance tests.
