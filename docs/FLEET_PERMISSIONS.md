# Single tolerance of park

Working paper: `~/.local/share/explorer3/configs/fleet.json`.
`configs/fleet.json` in the repository is a sample of the decision taken.
does not open the devices: launch remains a clear user action, TTL,
STOP, lock-down of occupied ports and measurement checks are maintained.

`fleet_config.robot_allowed(robot)` is the total source of control clearance,
Cameras, Leader and remote clients. Missing/damaged file prohibits
The old workflow /stage/hardware-enabled does not give flags
The approval of a specific test may be used to determine the number of permits and cannot interrupt a new solution.
The policy remains a separate confirmation of the launch of a specific plan.

SO-101 is left for `legacy_8020` when it moves: no service stops.
The transfer of the owner is performed by a separate user button (R4 pack).
The change of owner to JSON does not replace the release of the devices.

Migration: `.venv/bin/python scripts/migrate_permissions.py`.
First, the `archive/permissions-<UTC>-<id>/` archive with the original files is created,
SHA256 and README.json. Created fleet.json; the previous tolerances are removed only
The re-call saves the current decisions.
Migration is prohibited by blocking during active control or recording.

Reverse: Same script from `--rollback <полный путь архива>`.
He checks the checks and refuses to wipe the change after the migration.
fleet.json or old file. Incident history and reports are saved. Keys,
The services do not participate in migration.
