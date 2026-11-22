# Simulation scene measurements (15 minutes, roll and kitchen balance)

The values are recorded in `configs/scene_measurements.yaml`. After measurement, change y
Section `status: assumed` as at `status: measured`The politicians keep the hash of this file:
After the revision simulation and learning use new sizes and old policy
Shows they're trained on the old stage.

## Purpose of the approach (common for Tank and ROSMASTER)
1. Print out the tag ArUco `DICT_4X4_50`, id 0, **side not less than 15 cm**
   (less than 1.5 m of camera confused by corner) Generator:
   `.venv/bin/python -c "import cv2;cv2.imwrite('marker.png',cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),0,800))"`.
2. Put it on a rigid shield. Measure the width and height of the shield.
   (`board_size_wh`), side of the black square of the mark (`marker.side`) and height
   ) The centre of the mark from the floor (`center_height`).
3. Mark the round stop zone in front of the shield. Measure the distance from the shield to the plane.
   (a) The main area of the zone`standoff`) and its radius (`zone_radius`).

## Gender and room
- `free_area_xy` is the length and width of the free rectangle where the bases travel.
- `material` is a laminated, tile, carpet, or linoleum.

## Tank
- Tuck is a full-scale test with Pi and the battery (`mass_kg`).
- Distance from the center of the hull forward to the camera lens and its height above the floor
  (`camera.forward`, `camera.height`).
- Same for lidar. If the lidar is turned, put `yaw_offset_rad` and
  `direction` (1 counterclockwise, -1 clockwise)
  Shadow mode script: in the panel entry, the minimum range is straight ahead
  The need to be in the front sectors.

## ROSMASTER
- Base size (`footprint_lw`), camera position and height, lidar position -
  Like Tank.

## Table SO-101
- The height of the table, the side of the cube, the weight of the cube.
- Internal dimensions of the box and its centre position relative to the base of the arm
  (up and down, in metres).
- If the top camera is above the table, its position and inclination.
  The perception on the robot gave the position of the cube at the same coordinates as the simulation.
