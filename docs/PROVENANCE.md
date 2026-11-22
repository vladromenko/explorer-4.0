# Origin

Only the low-level SO-101 I /O of `/home/jetsonnx/Projects/so101_ai_learning/src/so101_lab/hardware.py` is copied.
SHA256 Source: `c1bb47ffe68f994717a28d25a8bde2670dbc999c20429311d31ad7f630486075`.
Explorer’s hardware adapter is in [hardware.py](../explorer4/hardware.py). The source is stored locally outside Git.
Authorship: existing user project so101_ai_learning; no separate licence detected; public distribution is not permitted by this document.
Changes: own data catalogue/calibration, wrist-only, own resource release./UI/trainer/No data were copied.
Original unchanged. This is a copy of the I /O service used; the physical functionality of the copy has been checked at stage B (three present displays; previous controls have been restored).
LeRobot is installed from PyPI as a topstream dependency, Apache 2.0; not copied from the old venv.
Calibration: own files outside Git, robot ID and motors retained, hashs and sources in local calibration /manifest.json.
PyTorch /torchvision: New installations of the same versions 2.11.0+cu130 /0.26.0 +cu130, without modification of the system CUDA.

Public SmolVLA base: revision 5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6.
SmolVLM2-500M-Video-Instruct: revision 7b375e1b73b11138ff12fe22c8f2822d8fe03467.
The ones taken from the standard local Hub Cash (not from old projects) are developed by the regular files in their own cache.
Heshes of all snapshot files and ResNet18 are stored in local cache /manifest.json.


Tank: installed by Hiwonder ROS2 driver/controller and ros_robot_controller studied read-only; selected Board SDK and Aurora930 exectuable/library Copyed inside /home/ubuntu/explorer3/vendor. The authors are Hiwonder / Deptrum; SDK distribution license is not established (package.xml contains TODO), and the bin bags in Git are not included./safety/HTTP files are in agents/tank. Originals were not corrected. Manifest with reference routes and SHA256 with local ringtime/provenance/tank-vendor-manifest.json. Geometry/signs/limites are reproduced from a real controller, corrections read from robot_correction_factors.yaml New namespace. /explorer3/tankNew venv uses unchangeable systems ROS/OpenCVThe source of the documentation and the restrictions are docs./TANK.md.

After the first physical check failed, the complete low-level controller chain was further copied/ros_robot_controller With the necessary seizures, only 12 files./copy SHA256: runtime/provenance/tank-native-chain/native-manifest.json. Copyed originals outside Git; the copyrights are saved. Only the ways of confiscation are changed to their own. native_driver.py Performs original classes/constructions/ROS Callbacks; old own kinetic function deleted. The ROS messages are used as unchangeable established libraries; the old webbackend is not used. Two memory tests instead of a serial are not considered physical.


### Local adapter of the selected Console8090 (2026-11-12)

agents/rosmaster/control_adapter.py contains two methods `_manual_step` and `_mirror_step`copied without change from the mirror-fix 20261112/candidate/cubebot/web/server.pyThe original SHA256 and selected heches of methods - control-adapter-provenance.json. Native CartesianJog, MirrorMapper, ArmModel and configuration are re-used from their own native/cubebotThe wrapping only separates the database/hand profiles, checks the entry and end of the commands. No change in the signs/zero/limite, smooth ghost or rejected partial-feedback patches. start-agent.sh 2026-11-12: Domain30, own DDS file/vendorThe asset is only launched for observation, without a serial./publisher. The live motor ringtime and handoff remain separate uncompleted hardware integration.

A precise copy of six low-level bridge modules is available on Homebrain, hashs in /rosmaster/bridge-provenance.json; the source and actual configurations are stored in a private ringime /provenance/rosmaster-bridge-current.; the first five are similar to the previous robot version; the fake_board is added for future software tests. The detected fallback to the old calibration catalogue is still required to be isolated before launching its own bridge; the current read-only Observer does not import these modules.


ROSMASTER: Runtime uses a copy of BaseIO/VelocityShaper/ObstacleGuard/CartesianJog/MirrorMapper, transport copy of the native BridgeCore+Link and unchanged nominal coefficients from its own config. bridge_ros.py The same is true of the same thing as the other one./gamepad Set-up in rosmaster_control.py adapted from selected cubebot/web/page.py: same axles and hand buttons, no mission/preset The own chamber starts a copied camera-rgbd.launch.py and the established separate Orbbec1.5.22 with the old arguments. Handoff only changes the active state of the services during the tenure, the original unit./source/config It doesn't edit.
