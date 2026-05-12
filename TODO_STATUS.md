# Project Status

Updated: 2026-05-11

This file is the current engineering status, not a completed-feature claim list.

## Current State

- The repository was left in a merge state. `main.py` and `requirements.txt` have now been marked resolved in Git.
- The code compiles with `venv\Scripts\python.exe -m compileall -q .`.
- `main.py` has been split by responsibility and now mainly wires the application together.
- UI panel behavior lives under `ui/panels/`.
- Device/input/application management behavior lives under `services/`.
- Analysis and model-assisted review behavior lives under `analysis/`.
- Pure coordinate and event JSON helpers live under `domain/` and `data/`.
- `agent_data.py` is now a small compatibility facade; schema setup lives in `data/agent_schema.py`.
- Experimental features that were not exposed in the current UI were removed.
- Old generated cache files under `__pycache__` exist in the working tree and should not be treated as source.

## Priority

1. Verify the core loop:
   device connection -> recording -> event capture -> database write -> audit -> rule generation -> replay.
2. Keep the current UI surface small until the core loop is stable.
3. Continue reducing SQL-heavy repository methods where practical.
4. Add smoke tests for import, database initialization, and basic non-GUI services.
5. Replace this file with a shorter release checklist once the core loop is verified.

## Known Risks

- `TODO_STATUS.md` previously contained mojibake and contradicted Git state.
- The split currently uses mixins to preserve behavior; future passes should turn stable seams into service objects.
- The largest remaining UI method is the YOLO audit tab builder; split it further only when changing that UI.

## Next Check

Run the app, confirm whether the main window opens, then test one real recording session with a connected Android device.
