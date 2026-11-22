# Transfer of work: root study of "knowledge gaps" (16.11.2026)

** New extension of Code 16.11: see last section `docs/TODO_NEXT.md`.**
Isolation of K0 /K2, MuJoCo collision boundaries, teacher trajectory and verification
The teacher pilot is 20 /20 on four.
Supported box approach; flat objects have not yet been resolved.
Record   ♪ Import ♪ split ♪ collection of TRADE with correct text checked for 3/4 Show.
The training has not yet started.
It will save and run the complete results, not run duplicates.

File for any next chat (Claude on Homebrain, Codex on Mac). Read the entire before work.

## Why?
The project owner re-defined the root of the study: **ROSMASTER understands what knowledge he lacks.
(Where is the object, how to take it, whether there is a NAVIC) and calls for the help of parts of the piano:**
- Tank (and ROSMASTER) seek the subject, the knowledge of GDE on the common map;
- SO-101 (white hand on table) studies/measures the object \ \ Knowledge as (size, height of capture);
- The language/visual model (local Qwen3-VL-2B) helps to assess what is missing and who is called;
  Her answer is checked by code, the rules remain the base line;
- The last person to be assisted is the man.
Everything that exists (Roy, agents, memory of help, MuJoCo, experiment A) is converted to this root.

## The Stir Rules of the Owner
- Wristlab (`~/Projects/so101_ai_learning`,:8020) and `~/Projects/so101_autonomous_pick_place` (:8010)
  The required mechanics are copied in `explorer3/` with an indication of origin.
- Console:8090 does not change. CubeBot does not change. Foreign uncompromised changes do not commiserate.
- Tank: No independent hardware stop; no freeway: 25 cm, no fresh lidar.
- Robots are on charge, moving them only after the owner removes them from the charger (he says when).
- Release the git as it moves (remember team: gh shortential helper, `git push -q origin main`).

## What has already been done
| Part| Files| Status|
|---|---|---|
| The knowledge warehouse on subjects, the gap assessment of who is /how/skill who can help| `explorer4/knowledge.py` | in git (7a99a95)|
| "Bring": an evaluation of gaps ♪ SO-101 is studying PARALLONO with a search for ♪ capture with this knowledge ♪ the result is recorded in knowledge (record_use)| `explorer4/swarm.py` (`_fetch`) | in git|
| Agents: Test notes, `knowledge` help memory| `fleet_agents.py`, `cognitive/schemas.py`, `cognitive/store.py` | in git|
| ROSMASTER takes the width/highness of knowledge into account| `rosmaster_arm.py` `pick(knowledge=…)` | in git|
| Virtual room: objects dimensions, SO-101 virtual bench| `swarm_sim.py`, `so101_station.SimSO101Station` | in git|
| K0-K3 experiment in virtual room| `scripts/knowledge_gap_experiment.py` | in git|
| **Copi of SO-101 measurement mechanics**: upper chamber C920 + SAM 3 + checked calibration of hand camera + 8 vertice cube/box| `explorer4/so101_vendor/` (`table_projection.py`, `cuboid_vision.py`, `measure.py`), `configs/so101_station/overview_calibration.json` | checked on frame: 30.1 mm cube (old 29.5 mm project)|
| SO-101 bar without HTTP: measurement   ♪ knowledge (access=Nene until confirmation by seizure of recipient)| `explorer4/so101_station.py` | Ready.|
| Qwen counselor: gaps and assistants, code check; condition K4| `explorer4/cognitive/gap_advisor.py`, `swarm.advisor='decide'` | Open offline, ~36 s|
| MuJoCo: objects of different sizes, expert without knowledge / with knowledge of SO-101 / with full information| `sim/aligned.py` (`vary_objects`, `ScriptedFloorPick(knowledge=…)`), `scripts/knowledge_transfer_mujoco.py` | Settle down (see below)|
| Tests| `tests/test_knowledge.py` (+ corrections test_swarm*, test_fleet_agents)| test_knowledge 3/3 |

## What remains (in sequence)
1. **Thes** `tests/test_knowledge.py tests/test_swarm.py tests/test_swarm_sim.py tests/test_fleet_agents.py tests/test_cognitive_contracts.py`: repair, commiserate and fire down.
2. **MuJoCo** (`scripts/knowledge_transfer_mujoco.py`): Even an expert with full information does not take socks
   (slips out with the object turned upside down). The check "saves" for different sizes has already been corrected.
   (Put above the floor by the capture) You need to turn the wrist around the narrow axis of the object if orientation is known;
   Then run 60 episodes ♪ `docs/results/knowledge_transfer_mujoco/`The size of the objects is a model assumption.
3. **Virtual room**: `.venv/bin/python scripts/knowledge_gap_experiment.py --rooms 10` (K0-K3; K4 separately,
   `--conditions K4`, long due to the model), the results of `docs/results/knowledge_gap_sim/`.
4. **Learning in the same algorithm**: SmolVLA for `rosmaster_floor_pick_sim` with `vary_objects=True` and knowledge in
   The problem is that the problem is not a problem, but that the problem is a problem.
   Starting the training only with the permission of the owner.
5. **"What to Do Today" country** (`explorer4/today_pages.py`): steps of root experiment (K-experiment, measurement)
   The SO-101 stand, robot test.
6. **Document** `docs/RESEARCH_ROOT.md`: Question, levels of evidence, experiments, what the owner does and where.
   Update `docs/ARTICLE_TASKS.md` and `CURRENT_STATUS.md`.
7. **Physics (with owner):**(a) The same object is placed on the SO-101 table as on the floor; "Roy" ) "breast cookies";
   The stand measures, ROSMASTER searches with Tank, takes this knowledge. (b) Test capture of SO-101 in Explorer is not yet available --
   The stand only measures, doesn't move its hand.
8. Audit balances: Recording of episodeWriter (to help / help / continue) runes trained by SO-101 in "bring" by an operator's assistant.

## When to take robots off charge
Not before paragraph 7... before that, all the work on the simulation and on the SO-101 table (cam, no movement of hand).

## Update 16.11.2026, ~02:45 (after iron check)
Done and fired (4a2c937), ROSMASTER's arm awaits the rest of the chassis; before re-entry, the hand
Release control; "bring" without showing the transmission points ends with "ROSMASTER holds the item";
SO-101 does not make up height when seen from the top; Tank has a deep chamber stop
(`agents/tank/limits.depth_obstacle`, jestered in the MentorPi container, `archive/backup-20261116-depthguard` backpack);
Local API piano `POST /api/swarm/command?text=…&robots=…`, `/api/swarm/stop`, `GET /api/swarm/status` (only 127.0.0.1).

Results on the iron: SO-101 measures a cube of 29.8 mm (the truth of ~29.5). ROSMASTER finds a cube and comes up,
But the geometric grab at the floor is missed (the aim is to reach 5 cm, the last descent into the blind, "empty capture".
Tank entered the chair: lidar (14 cm) does not see the legs ♪ added depth stop, **physical not yet checked**:
Session `mode=policy`, v=0.08 forward to obstruction, wait for `reason='Препятствие впереди'` at ≤ 0.25 m.

### Next steps (order)
1. Check the Tank stop to the depth (see above), owner adjacent to it.
2. MuJoCo learning with knowledge: add `rosmaster_floor_pick_knowledge_sim` profile =
   `RosmasterFloorPick(vary_objects=True)`, expert `ScriptedFloorPick(knowledge=<размер с шумом ±1.5 мм>)`,
   The size-based problem text ("pick up the cookie, 7.0 x 7.0 cm, 1.2 cm high") is a size-free version of control.
   To collect 200 demonstrations, train SmolVLA on both (at night), compare success by one seed. The owner authorized the launch of MuJoCo.
3. Calculate `scripts/knowledge_transfer_mujoco.py --episodes 60` (log `~/.local/share/explorer3/knowledge_transfer_mujoco.log` )
   and `scripts/knowledge_gap_experiment.py --rooms 10`; heavy runs one by one, through nohup + `systemd-run --user --scope -p MemoryMax=6G`.
4. The owner: Unit 3 (50 stripes of capture from the floor) is not secure without the capture of ROSMASTER; the SO-101 (10 minutes) transmission points.
5. Document `docs/RESEARCH_ROOT.md` page /today.
