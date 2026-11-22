# Common ROS 2 system on Homebrain

14 November 2026. Common **-stars are operational**.
Taking a joint autonomous movement and not a ready common map.
The training was not started.

## Component linkages

```text
Tank: ROS 2 Humble, default domain 0 ──┐
                                     ├─ authenticated read-only observers
ROSMASTER: ROS 2 Jazzy, domain 30 ─────┘           │ HTTP, source timestamps
                                                ▼
                          Homebrain: separate ROS 2 Jazzy hub, domain 73
                          /explorer3/robots/tank/*
                          /explorer3/robots/rosmaster/*
                          /explorer3/fleet/status
```

Page `/fleet/live` shows link, age of flow, estimate of alignment
It opens up the existing ones.
The general STOP uses existing controls and environmental pages.
Explorer controllers. Sensor tyres do not acquire the ownership of devices and
does not publish `/cmd_vel`, the purpose of the arm or the engine command.

Old ROS houses and programs have not changed.
own controller, validity of commands, STOP and physical clearance.
Connecting everything to one domain ID is not enough: it provides a discovery,
but not calibration, timing, ownership of executive devices
ROS 2 does not replace these mechanisms.

## Contracts implemented

- RGB and the numerical dept /IR  ♪ `sensor_msgs/Image` ♪; CameraInfo Saves K /P/R/D.
- Front/Reversal scans ♪ individual `LaserScan` ♪ IMU ♪ `Imu` ♪ Magnetometer ♪
  `MagneticField`, measured odometer ROSMASTER ♪ `Odometry`.
- Positions of servo-drives ROSMASTER ♪ `servo_feedback_rad` (`JointState`)
  These are converted from degrees **red angles of servo-drives**, not
  calibrated relative to the URDF point positions.
  Robot_state_publisher automatically.
- Manufacturer's cloud   ♪ `cloud_display` (`PointCloud2` ), with conservation
  cutting; voltage `BatteryState`, unknown percentage is NaN.
- Static TF manufacturers have the prefixes `tank/` and `rosmaster/`.
  Same `base_link` Two robots don't mix. `world→robot`
  The dynamic integrated map is not ready yet.
- Re- and outdated measurements are not re-published.
  Seen in status and not fully ready for observation.

## Time

Each observer returns the bound ROS time pair.
Boot ID and the measurement time. Homebrain measures HTTP root treep,
Selects a low-delay rating from the last 15 seconds and repeats measurement
The engineering reserve of 250 ppm is taken into account; this is **not
measured generator characteristic**. Reloading, clock jump >50 ms
and `use_sim_time` at the physical source, drop/distort alignment.

ROS header publishes the reference time of measurement translated to scale
Homebrain. Without a source header, a clearly defined time of arrival is used
The reference numbers and the frame IDs remain in the diagnostics.
The cameras are not synchronized.

The human resources matching selects the pair from the original RGB timetamps, expanding
The difference is both hours. The default is the sum ≤ 100 ms;
No suitable pair, no agreed observation.
Tank restarting both real platforms received simultaneously; comparison
Found a couple with an estimate of the discrepancy of about 64 ms. This is an ongoing measurement, not a guarantee.

## Start and check

Docker image is collected from `agents/ros2_hub/Dockerfile` on fixed digest
Official ROS Jazzy Base.
`explorer3-ros2-hub.service` is on Homebrain.
No capacilitations, with read-only root and source; entry only in its own
Status and time memory catalogues.
is not part of the image or Git.

`.local` is allowed via libns-mdns and the Avahi Homebrain,
The Docker did not allow the name Tank, although
The same host request was running. The IP is not artificially stored in the code.

DDS is limited to a loopback-interface Homebrain. `fastdds.xml` uses UDP
and a clear local unicast discovery to make a separate consumer container
worked without a common `/dev/shm`. `fastdds-hub.xml` adds unique
====Prepix ====The only hub is prefix; consumers use **fastdds.xml**, not hub file.

Verification by a separate, present ROS subscriber:

```sh
docker run --rm --network host --user 1000:1000 \
  -e FASTRTPS_DEFAULT_PROFILES_FILE=/workspace/agents/ros2_hub/fastdds.xml \
  --mount type=bind,src=/home/jetsonnx/Projects/explorer-4.0,dst=/workspace,readonly \
  explorer3-ros2-hub:jazzy python3 scripts/check_ros2_hub.py
```

Checked real RGB /depth, both scans, IMU, servo feedback and odomery
ROSMASTER; standard ROS serrification, different frame IDs, freshness and
No motor tops in Hub. Verification of synthetic messages not
The DDS is published and launched separately through `check_ros2_hub_contract.py`.
Chromium checked the ROSMASTER page, recording/repeating and general overview on the mobile.

## What remains

1. Check the stability of the flow at a future authorized physical session.
   Updated observers are already standing on both robots; simultaneously checked
   Real ROS subscriptions to 13 streams of two cars (without motor commands).
2. Measure sensor/base conversions, select common map and method
   Do not equate the command integration of Tank with the measured odometer.
3. After individual physical tolerances, connect joint execution
   The current process of physical verification of the requirements of the approved ownership mechanism and STOP is now a physical one.
   The autonomous coordinator is not included; the simulation is a separate component.
4. SO-101 is not required to be connected by its adapter after a separate application.
   Set the ROS on USB-servo drive; its node can live on Homebrain.

Grounds: [ROS 2 Clock and Time](https://design.ros2.org/articles/clock_and_time.html),
[Official example unicat discovery](https://github.com/ros2/ros2_dds_profiles_examples/blob/main/fastdds/unicast_discovery_from_another_host.xml),
[Fast DDS Initial Peers](https://fast-dds.docs.eprosima.com/en/2.x/fastdds/use_cases/wifi/initial_peers.html).

## Tank Memory Malfunction and ROS Dissociation

In the download of `f061ccd6-50b9-433c-bfa5-bd25c2b945df`, the core log confirmed
Exhaustion of memory and mass completion of the ROS processes. `joy_node` occupied
:: approximately 2.6 GB RSS, `hand_gesture` – about 3.8 GB; camera, MCU Bridge and lidar
Ping continued to operate with the unaffordable SSH /HTTP..

The Fast DDS /typesupport packages were installed on Tank.
[Defect of the interversial discovery Humble /Jazzy](https://github.com/ros2/rmw_fastrtps/issues/797),
The correction for Humble [in September 2025](https://github.com/ros2/rosidl_typesupport_fastrtps/pull/133)].
My early view of ROS-topics ROSMASTER without a clear domain ID could have caused
It's a possible explanation, not a proven router.
The root; the dangerous scenario on the robot was not repeated.

The personal observators now check ROS_DISTRO and clearly ask the domain:
Tank Humble /0, ROSMASTER Jazzy /30; Hub and its verifications require Jazzy /73 and
Localhost-only. Exchange between them is HTTP.
The stitch, power thresholds and the zummer have not changed.
The new download has recovered the regular sensors, available around 6 GB RAM,
This does not close a separate engine USB incident.

## General recording and viewing

`/fleet/live` has "Place Sensors" for 15 /30/60 seconds.
The container only signs on a fixed list of domain 73 tops,
No access to robot devices and seizures.
512 MIB seriated messages, 64 MIBs; before starting
1 GB of space required.
The missing machine is not replaced by synthetic data.

Upon completion of the official `rosbag2_py` read each file again and
Checks the number of messages by stream.
The number of cars, the source /receive timeamps, the frame IDs and the number of hours that are suitable.
`clock-status.json` maintains error and Boot IDs during the recording process.
Aurora numerical depth is published as the standard `16UC1` in millimeters;
The original `mono16` remains in the original diagnostic packages.

"Looking together" opens up cameras, depths and lidars of two robots on one.
This is a view from a stored MCAP, not a robotic approach.
And not ROS Playback.
Once per second; images above 1.5 seconds are hidden by the selected time.
The numerical reference points remain in MCAP. Prevew is not used for learning.

Catalogue: `~/.local/share/explorer3/fleet-captures/<id>/`. Archives marked
`diagnostic_rosbag`, `training_eligible=false`. Recording of observations without action
It is not a teaching show.
Tank /ROSMASTER profiles in LeRobot; they store the original sensors.

Update the service layer: Homebrain `cognitive.real_execution`
The current Session /ROSMASTER Operator and authorized triales.
The tractor remains the same API /SDK; read-only ROS 2 Hub is not transformed
To the general publisher of the motor team./STOP
on the device and insulation of the Humble /Jazzy. only offers a closed model
plan, reference sensors give an indication; uncalibrated common map
replaces by a fake world transform.
