> 14.11.2026, R2: Locked off by explicit user decision.
> retained in the permit/installation archives, history not removed below.
> Speed/dispersion limits, Pi-protection and USB re-establishment with confirmation
> No spontaneous renewal.
> declared implemented; the new physical inspection is performed by the operator.

## History before transition to R2

> 14 November 201226: The operator discovered a defective charge line; after the re-editing, the beam disappeared. The battery was measured with charging 7.012-70331B; the new USBdiscontect is not present in a short static observation. This does not close the previous USB /STOP incident. Tank is off charge, the incedent-block is retained.

> Current failure in the second present display. USB 186:55d4 has been disabled; serial write EIO, zero commands have not been delivered; operator has turned off power. Current lock is on Homebrain and Tank. Details: `tank-usb-incident-20261113.json`, `STATE.md`. The history of previous checks is retained below; it does not mean current traffic readiness.

# Tank: failure of first physical inspection

The user reported an uncontrolled movement after the command to move forward and the non-working STOP; stopped the power. The physical intake of FAIL. The subsequent successful HTTP /stop is not a rebuttal of the user's observation.

The server received STOP 2026-11-12 01:08:04.736 MSK and closed the 216-test cycle. The agent responded /stop 200 at 01:08:05.849. UART's teleop session was not maintained; there was no measured confirmation of the engine stop. Both nodes' logs were kept locally. The preliminary zero command test confirmed only the program response, not the braking of the chassis. The verification on the floor was premature.

The partial adapter did not perform the regular send_matchine_type and complete launch of the board node. The actual SDK plant and its copy matched the SHA256. The cause of the whole incident, especially the absence of physical STOP, has not yet been proven.

The partial adapter is replaced by a full chain of copies of controller and ros_robot_controller at the user's request. Original design, initialization of the engine type/existing power threshold /offsets, restrictions, kinematics, ROS delivery and SDK are stored outside Git, only the ways to copied Confiscations have been changed. No new learning/movement of the old backkend.

In the new layer only: lifecrycle, private HTTP, control of recording seral, log, local latch STOP /TTL. Restarts not armed. After non-suspension, physical stop cannot be removed from PID/port closure. The MCU hardware confirmation is not available.

Checked for Tank without hardware: real copied ROS points and HTTP processing machines with a serial.Serial, replaced memory before initialization. Separately STOP after a non-zero package and time out after a non-zero package: formed zeros, next command rejected. Full initial batch of packages retained. 15 local PASS tests. These results do not provide a physical PASS.

The security markers are stored on Homebrain and Tank. The agent is inert, starting the session 409. The plant services after the user reboot are active; the code of the previous control has not been corrected.

The next physical check is possible only after charging, without charging cable, on a steady stand with both caterpillars in the air and an accessible switch. Until such preparation is confirmed, the traffic ban remains. Three shows/trainings and the transition to ROSMASTER are postponed until the successful STOP and communications check is completed.

## Reset 2026-11-13

The Wi-Fi session recorded the real UART teams of two automatic pulses 0.03m/s. STOP and the stop of the commands gave zero bags; the last non-zero:91.53ms and 351.13ms respectively. The food 8.11B, camera 640×400. The operator did not observe these pulses; the physical PASS was not displayed. In a manual follow-up, the operator reported no rotation and buzzing. The first session ended with an added cut-off of 0.7c, next being a network RedTimeout. The reason for the buzzing is not proven.

The normal speed limits 0.2 m/s and 0.5rad/s have been restored; cut-off 0.7c has been removed. The check is performed only by the UI user on the support. STOP, TTL350ms, power/cam and self-start prohibition are maintained. Temporary boot-bound `bench-authorized.json` allows a manual verification of a maximum 15 min with `incident-block.json` stored; the display is prohibited. Extension of the permit is only for the current confirmed physical check. This is not an incident withdrawal or a floor traffic permit.

In the in-house layer, the following corrections are made: bypassing the session via the copied ROS 409 (now STOP latch), completing the ROS /serial in the lifespan before the repeat of SIGTERM uvicorn, maintaining the first cause of stop and transmitting the cause of HTTP409 to UI. The checks without the motor port were performed at ROS_DOMAIN_ID211 with the substitute serial. The latest local checks are:11 PASS; noative STOP /TTL PASS. The evidence is `runtime/validation/tank-20261113` outside Git. Physical verification of normal speed, release, STOP, loss of browser, return of telephone and 3-points remain open.


## Border of the stop

[Official instruction T1, §3.4](https://wiki.hiwonder.com/projects/MentorPi-T1/en/latest/docs/3.motion_control_courses.html) warns: shutting down software may not stop the syssi itself; the required command. The installed SDK does not contain the found structure MCUcommand-timeout. Linuxwatchdog does not eliminate loss. Documentation RRC charges and Bluetooth example stimeout are not evidence of RRC Lite USBprotocol.

[The response of the employee, Hiwonder 9 November 2026](https://forum.hiwonder.com/t/mentor-pi-mechanum-chasis-motors-dont-stop-spinning/312), contains a reference to a factoryfirmware for another set of components.MentorPi. The composition of the Drivearchive and the compatibility of the specific payment are not verified; the embroidery has not been downloaded/used. This is a source of verification with the manufacturer, not permission to request a blinding Tank.

The next block is only a loaded Tank non-charged stand-up with a switch switch. Until independent stop is independently confirmed, no normal driving/self-test is allowed. Useful displays and old successful stencil checks are maintained, but do not cancel later refusals.
