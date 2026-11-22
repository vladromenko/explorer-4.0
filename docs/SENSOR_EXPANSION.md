# Extension of Data Explorer 4.0

Status as at 14 November 2026: implementation ongoing; training not started.
First, the unrolled part of Tank is completed, then ROSMASTER.

## What's already been received on Tank

The actual system is obtained from the following ROS 2 subscriptions:

- RGB, reference depth and infrared image of Aurora930, 640×400;
- CameraInfo: the projection, distortion and size of the images;
- Cloud of producer points in metres;
- Laser scan: distances, angles, tolerance range and time parameters;
- IMU: angle speed in rad/s and acceleration in m/s2;
- Battery voltage, time marks and static coordinate transformation.

The actual Lidar driver MS200 is used.
The store is not considered to be a confirmed model of the device installed.
Sensor monitor only reads: it does not open the engine port,
does not publish the ROS commands or initiate the movement of caterpillars.

## What's Additional

1. Environment screen: RGB, depth map, IC, laser view from above, interactive
   a cloud of dots, freshness of each flow, and food.
2. Recording of the background measurements without loss of depth, with enclosure parameters,
   The reference systems, the source time and the time of receipt on Homebrain.
   The diagnostic records of no action are kept separately from the demonstrations.
3. Supplementing lidar, depth and IMU data display.
   The data should be clear; existing RGB-dates and sheckpoints remain unchanged
   Asynchronous flows are compared by time and omissions and omissions are compared with the time flow.
   The outdated data have separate masks.
4. Signs of an environment for a politician: 36 sectors of lidar, 8×6 depth grid,
   IMU, shares of valid measurements and age of data.
   retained for subsequent application of other submissions/models.
   Support for the additional entry should be checked at each architecture:
   The presence of a VLA RGB input does not in itself mean the use of depth/lidar.
5. Overview of several robots after checking the conversion of coordinates and
   Individual clouds are not yet declared as a single map.
   Tank command odometer is not released for measured wheel movements.

## Following is ROSMASTER

User turned on ROSMASTER and requested testing of all actually available
capability: lidar, depth chamber, possible microphone, lower lighting and
First, an inventory of installed equipment and finished equipment
The main driver is the driver; then the confirmed stream and function are connected to the Explorer.
Availability and performance of microphone, display and lighting are not yet confirmed
Their support is not announced in advance.

Update: ROSMASTER observers are installed as separate services 8053 /8054.
RGB /depth 640×480 Orbbec DaBai DCW2, both scans of 666 measurements,
IMU, magnetometer, measured odometer, six angles of servo drive and battery.
`/rosmaster/sensors` screen checked, 6-pack diagnostic record checked and her
Rereading in Chromium, including a narrow screen. 3D surface is re-established
Homebrain from dept and real CameraInfo: not included in the regular publication.
The 265 features are connected to new profiles
`rosmaster_dock_rgbd_lidar` and `rosmaster_pick_place_rgbd_lidar`. Recording
Actions, RGB and basic packages of both lidars /depth/IMU/odom/mag; selected
The last package already received by the time of observation, without data from the future.
The Fixture LeRobot readback and four details of the current browser have passed.
Real shows with new profiles have not yet been accepted; the training has not been started.

USB C-Media audio frame detected, manual 5-second test available,
The light is supported by RGB opcode of current
MCU-protocol. An explorer unit has been added to the previous copied interface
Lights; it only sends RGB opcode through its own open
The controller and does not include the control/motors.
Physical light has not yet been checked. OLED is controlled by manufacturer
to STM32 PB10/PB11; there is no OLED team in the current copied protocol.
The display was not changed for the screen; the presence of `/dev/i2c-*` on Jetson does not confirm
OLED connection to Jetson. Both lidars are already coming through MCU: unidentified
USB 186:7522 is not declared lidar and the driver was not forced to be attached to it.

Total tyre of observations ROS 2, time difference measurement and human resources comparison
implemented on Homebrain: [](ROS2_COMMON_SYSTEM.md). Common map,
Camera hardware sync and coordinated physical movements so far
Not declared ready.

Old panels and systems are stored. The training will start after the user has
The test of the unrolled sensors does not close
Tank incident with USB loss and missing STOP; physical clearance remains
A separate check.

## Implemented in current update of Tank

- `/tank/sensors` screen: live RGB /depth/IR, lidar, cloud of points, freshness and power; checked by Chromium on computer and narrow screen.
- Short recordings of sensors up to 60 seconds, a record list and a re-view without a robot on it, diagnostics are not on the display dataset.
- Ports own surveillance services 8043/8044 The sensors return after restart, the engine agent remains `armed=false`, `hardware_open=false`.
- The profile of `tank_dock_rgbd_lidar`: RGB + 178 environmental features; the original dept /IR/scan/IMU and time tags are stored close to the actions, the re-packs are not duplicated. The missing and obsolete have masks. The flow gap of more than 2 seconds interrupts this profile.
- The real LeRobotDataset recorded and read a new contract for obviously synthetic nuxture. The ACT was straight-lined: changing the input environment changes output. The optimumizer, learning, downloading weights and sending results to the engines was not available.
- SmolVLA does not support this additional entry in the existing recipe: this choice is clearly rejected instead of silent loss of lidar/deep. Previous RGB profiles are retained.
- The installed `oradar_scan` with the regular MS200 launch parameters is overused for future control transfer. The second lidar owner is prohibited. The test on this device during the motor session remains part of the physical block.
- U.S.B.P. Audio Development with ALSA Capture. Added a separate 5-second record button; no automatic record or playback on Tank. The microphone's audition is not yet checked.

RGB is transferred to JPEG qualiity 85 for Wi-Fi; depth, IC, scan and IMU are preserved without loss of numerical values. The cloud for viewing is cut to 6,000 points; the full depth map is stored separately. Asynchronous packages, real source stamps, time of receipt and conservative age are saved. The common map and accurate external calibration of sensors are not declared ready.

In the last five readings, HTTP took about 0.10 to 0.34 seconds; this observation was not a guarantee of delay during traffic. Mandatory physical verification of STOP/USB loss was not replaced by these results. The Incident-block was not removed, the caterpillars were not launched.
