# Project Status

Updated: 2026-05-11

This file is the current engineering status, not a completed-feature claim list.

## Current State

- The repository was left in a merge state. `main.py` and `requirements.txt` have now been marked resolved in Git.
- The code compiles with `venv\Scripts\python.exe -m compileall -q .`.
- `main.py` is still too large and owns too many responsibilities through `MainWindow`.
- Low-risk TODO tool dialogs have been moved from `main.py` to `ui/dialogs/todo_tools.py`.
- Several new modules exist for dialogs, repositories, fast feature extraction, migration, cloud sync, and RL optimization. They should be treated as unverified until the core flow is run end to end.
- Old generated cache files under `__pycache__` exist in the working tree and should not be treated as source.

## Priority

1. Verify the core loop:
   device connection -> recording -> event capture -> database write -> audit -> rule generation -> replay.
2. Keep experimental features behind existing menu entries and avoid expanding them until the core loop is stable.
3. Split `main.py` by responsibility:
   recording/session control, audit/review, runtime rules, replay, scene recognition, and diagnostics.
4. Add smoke tests for import, database initialization, and basic non-GUI services.
5. Replace this file with a shorter release checklist once the core loop is verified.

## Known Risks

- `TODO_STATUS.md` previously contained mojibake and contradicted Git state.
- `main.py` is hard to review because unrelated UI and business logic are still mixed together.
- New optional dependencies in `requirements.txt` may make setup heavier and should be checked against actual feature usage.
- Data migration, cloud sync, and RL optimization have a wider blast radius than the current core workflow.

## Next Check

Run the app, confirm whether the main window opens, then test one real recording session with a connected Android device.
