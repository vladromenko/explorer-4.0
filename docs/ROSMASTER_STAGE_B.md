# ROSMASTER: Phase B and ROS liaison

It's 2026-11-14: authorized by ROSMASTER, and is being physically adopted by B.
Operator confirmed manual control of hand and chassis, STOP and base stop.
And then you show both the problems and the readback without learning.
The mirror is not a condition of the stage. Full acceptance B is not complete.
Synopsis of corrections and limitations in STATE.md; first
The connection is below historical.
[ROSMASTER_OFFLINE_PREPARATION.md](ROSMASTER_OFFLINE_PREPARATION.md).

The branch of the next-door dialogue is already part of the main; re-copying of the old
No shot taken. On the robot, SHA agent /runtime/control_adapter/ checked
Leased_core /observer: Five files match the repository. Corrections taken into account
EXPIRED, initial positions at limits, design of records, pilot's tempency and
Preparation of identification for individual real lobes.

## Actual architecture

- Homebrain: browser Explorer ♪ operator/record/frozen policy ♪ HTTP
  The policy and datasets of LeRobot live on Homebrain.
- Agent in peace: only ROS 2 subscriptions `/arm_servo_state`, `/odom_raw`
  `/battery`, `/camera/color/image_raw`. No engine commands are available;
  The watch doesn't check the controller's readiness.
- When explicitly activated: handoff retains previous service, stops the old service
  The owners are opening up the only seral and their camera.
  Copyed full-time protocol and local lease /watchdog. Hand measurements,
  The speed and the batteries are taken directly from the controller;
  So ROS topics of the old bridge is not
  are considered active during the ownership of the Explorer.
- MuJoCo: selected models/physics on Homebrain, same channel contract
  Direct total ROS
  There is no new new new new line for "sim ~ robot" and Gazebo in the current chain.
  You can't go to the physical motor without the transfer of possession.
- Relationship of the model to the actual device: geometry/cam/acting unit,
  recorded trajectory, sysid and separate transfer verification.
  It's not yet a fully identified digital double.

## Initial check without movement

2026-11-13: Agent launched inert, former rosmaster-brige remained owner
`/dev/ttyUSB0` (PID2507). Agent `hardware_open=false`, `armed=false`.
5 s surveillance: camera 640×480 /14.9 Hz, odom50Hz, battery2Hz, armmes
380.7Hz summation; all 6 drive units gave the final values.
measured speed[0.0.0] This voltage is not transferred to the percentage charge.
Shoulder/locoal outside the model operating range: arm folded. Existing code
automatically starts the rise after the distinct activation of the arm /manual, therefore
The first physical inspection shall take into account movement immediately after activation.

Runtime workflow is translated into B with `allowed_robots=[rosmaster]`; local-only
Saved for other devices.
The old Tank /SO flags do not open these machines.
SO /Wristlab:8020 was not affected. No training was started.

In the copied panel, a choice has been added "only with the hand / only with the chassis / hand
The profile is applied to the agent,
The writing is still separate from the writing of the buttons.
The old Console8090 hasn't been changed.

Then there's the physical check of the operator: free space,
Unset charger, empty hold; hand-only profile, activation and STOP
Then separate arm direction, release/loss of tabs,
The chassis and three real displays of each task.
No assistant sent to the unit; no actual stop has yet been confirmed.
Artifacts are the ringtime `validation/corrective-b/`.
