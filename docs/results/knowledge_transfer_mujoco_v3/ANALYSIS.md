# What a grasping robot needs from a helper

The MuJoCo experiment used 120 scenes with four conditions per scene. For the 82 scenes with a narrow object, the smaller horizontal dimension was at most 4.5 cm.

| Information available to the controller | Successful grasps |
| --- | ---: |
| Assumed a 32 mm cube | 60/82 |
| Object size from SO-101 | 58/82 |
| Size from SO-101 and estimated closing direction, with simulated angular error σ = 10° | 74/82 |
| Full geometry | 75/82 |

Adding the closing direction turned 21 failures into successes and five successes into failures. The two-sided exact McNemar test gave p = 0.0025. All four conditions succeeded on only one of the 38 scenes with wide objects. Those scenes exposed the limits of the gripper's opening.

Size and closing direction address different parts of grasping. SO-101 can provide dimensions, and ROSMASTER can estimate a closing axis from the principal axis of a segmented object. In this experiment, we used a scripted grasp, represented the objects with box geometry, and modelled the angular measurement error in simulation. Physical performance remains to be measured.

[Protocol](protocol.json) · [Per-scene results](results.jsonl) · [Summary](summary.json)
