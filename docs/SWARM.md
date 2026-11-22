# Roy Explorer 4.0: How to use and what to write

## Enable
1. Turn on the robots: ROSMASTER, Tank, SO-101 on the table.
2. Open Homebrain (`http://<homebrain>:8000`), launch Explorer 4.0 and press **"Roy".** Open `/swarm` page.
3. The top is set to go: lidars, agents, transmission locations, recognition, disk. Green is open.
4. Write a command or press a quick button. On the right you can see the cameras and the state of each robot, on the map are robots, their targets and paths, the items found and the SO-101 station.

Tank turns on the piano itself, you don't have to press "Super Control." STOP piano stops everyone.

## Try without robots.
The **-Simulation without robots** on the page "Roy" includes a virtual room with walls, furniture, doorways and objects, and it also features the same piano code: common map, division of sites, camera-cover search, "bring" with all stages and recording of episodes.
- Virtual only room, motion and odometer, lidars, cameras (the "species" are within 2.5 m and ± 35° without obstacles), ROSMASTER arm and SO-101 gear.
- Real robots don't move. The real map, the memory of objects, episodes and the location of the transmissions are postponed and then returned.
- The thick lines on the map show the real walls of the virtual room, the circles -- where the objects are actually lying.
- **"New Room"**creates another random room,**"To Real Robots"** shuts down simulation.
- **"Translate the object"** mimics a man who undetected the object, so it checks out help between robots.

## Agents and help between robots
The "Roy" page has "Agents", "Target Plan" and "Aid Memory." Agents are six roles from [AGENTIC_ADDENDUM.md](AGENTIC_ADDENDUM.md). These are parts of the program with their state and their decision log, not individual neuronets. They do not control motors: only the tested performers (research, approach, capture, transmission) and STOP and limits are always in place.

| Agent| What does|
|---|---|
| Task manager| Turns the command into a plan from registered skills. For each step, the performer is specified and the result checked. The impossible is rejected with cause: for example, "bring" cannot be delivered, and Tank has no hand.|
| Scene observer| Each discovery of an object is preserved as a witness: who saw when, where on the map, with what error. If the object has shifted by more than 0.5 m, the conflict is noted.|
| Choice of assistance| If ROSMASTER has not arrived or taken the subject, it chooses three options: "another robot will look again", "repeated", "call man." Recite from memory that is compatible with the recipient's current version; if not, use a fixed basic order. Not more than two times per task.|
| Help Memory| He writes down every case of a candidate's assistance. He gets "reconfirmed" status after two proven successes, "reversed" after a proven failure.|
| Results check| The results of the assistant, the recipient and the entire task are recorded separately.|
| Data and training| Shows how many shows are recorded about the standard, where the MuJoCo scene came from, and how many models went through the robot's access.|

An example (checked in a browser on a virtual room): a person moved a cookie, ROSMASTER didn't find it, the choice of help sent Tank to look again, Tank found, ROSMASTER took, SO-101 handed it over. An incident recorded: Assistant - success, recipient - success, task - success.

The memory is common to the research part of `explorer4/cognitive`. This is what checks out the article's hypothesis: aid aligned with the recipient's policy. The simulation and reality cases are kept separately in the `domain` field.

## Commands
| Command| What's going on?|
|---|---|
| "see the room"| Both robots go to unexplored sites and divide them between them. The `configs/inventory.yaml` cameras record the items found in the common memory.|
| "find the sock"| The first person to see it, they're both looking for it.|
| "get to the cube"| There's a robot coming that's closer to the memory.|
| "get me a cookie."| Search if not known. ROSMASTER comes, takes, takes to SO-101, puts it on the site and leaves. SO-101 takes it from the site and extends it to you. Then press "Pick" or wait for 20 seconds.|

The switch "Both robot / ROSMASTER / Tank only" is needed to compare the piano with the single robot in the article.

## Once before "bring"
Open the transmission "Messages" in Unit Roy:
1. ** The gearbox is a box or a stand that is reached by ROSMASTER (to ~25 cm from its center, low) and SO-101.
2. **ROSMASTER: The position of transmission.**
3. **ROSMASTER: Position "put."** In the full ROSMASTER panel, lower the closed grab over the site and press the button.
4. **SO-101.** Select SO-101, turn on the lead hand control and show the lines "upside", "take (take open), "cuff", "give to man", "baseline".

## How (for the article methodology)
- **Common map.** Grid map 5 cm on Homebrain is made of lidars from both robots.
  - ROSMASTER: Odometery plus cross-checking of the scanner with the map.
  - Tank, which has no encoders: global search for itself through the scan, then tracking from the scan to the scan.
  - Until Tank finds himself, he's building his own map. After two agreed recognitions, it's entering into the common one.
  - False recognition is thrown away if the points of the scan reach the already visible free place.
- The contribution of robots. How many scans each robot added to the map, you can see in the status of piano.
- **Navigation.** Search for A* on a grid of 10 cm with a reserve for the robot's turn-up, turn-in in the corners of the path, protection against collisions on a fresh scan.
- ** The sites are cut into areas by a metre, the site loses value near another robot's goal, and the area to which the other robot is clearly closer remains (Burgard et al., 2005).
- **Species.**Pocket between furniture and the wall where the robot doesn't pass is checked outside: the robot comes up to the nearest available place and turns the camera to the pocket.
- The card protection against the wrong stitch.** The recognition of the spot is denied if the lidar beams pass through known walls. Before stitching their robot cards into the general check all its scans, not one. If the card has gone off (Tank has no encoders), the robot enters the common map without it.
- The search for the camera covers. Like GoalSwarm and WildOS: The map stores which floor the cameras have already looked at. The search for the object is going to places that the cameras have not seen yet, not just where the lidar card ends. At the beginning of each search, this mark is dropped.
- **Reception.** SAM 3 text, several objects per passage: 6 items in about 2.3 s. The distance to the object is considered to be the point of contact with the floor.
- **ROSMASTER.** SAM 3 plus deep camera gives the point in the robot system through the manufacturer's arm model.
- **SO-101.** Positions are set by the lead hand. Turn to the object itself: the test shift shows how the object moves in the frame of the wrist camera.
- **Episodes.** Each task is written in `~/.local/share/explorer3/episodes/` and downloaded in CSV by reference to the main page:
  - The result, time, path, proportion of time with known position;
  - Bring the "bring" stages with the duration and success of each;
  - mode `team` / `solo`

## Restrictions to be tested in person
- The orientation of the ROSMASTER lidars is measured in a depth chamber (both scanned clockwise, `/scan1` rotated to 180). The URDF and CubeBot describe them differently.
- The capture of ROSMASTER is checked at geometry and depth, but not by movement.
- The SO-101 transmission is based on the accuracy of the map transmission (~5–10 cm) and the steering sub-set.
- Wi-Fi: For delays above 0.5 with Tank tracking without encoders, the deterioration occurs.
