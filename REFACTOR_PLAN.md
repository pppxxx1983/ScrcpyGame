# Refactor Status

Updated: 2026-05-12

This pass completed the structural refactor: the oversized `MainWindow` and the first generation of large mixins were split by responsibility while preserving the current behavior and UI surface.

## Current Boundaries

### UI

Panel and dialog orchestration lives under `ui/panels/`.

- `event_list_panel.py`: event list, search, and event statistics.
- `event_detail_panel.py`: event detail tabs and rule debug entry.
- `event_video_panel.py`: event-local video controls.
- `tab_manager_panel.py`: tab reuse and close handling.
- `video_replay_panel.py`: video replay dialog entry.
- `execution_panel.py`: execution buttons, task list, scene preview.
- `rules_panel.py`: runtime rule list, rule create/edit/toggle/delete UI.
- `audit_list_panel.py`: audit filters, scene/YOLO audit list, batch actions.
- `scene_audit_panel.py`: scene review tab and save flow.
- `yolo_audit_panel.py`: YOLO review tab.
- `reanalyze_history_panel.py`: reanalyze history dialog.
- `status_panel.py`: status bar, log flush, runtime overlay text.

### Management

Application and device management lives under `services/`.

- `device_connection.py`: ADB refresh/connect/disconnect, IP detection, device resolution.
- `frame_capture.py`: scrcpy frame flushing, screenshots, async frame saves.
- `touch_mapping.py`: frame/device/raw touch coordinate mapping wrappers.
- `getevent_listener.py`: physical touch device discovery and getevent loop.
- `projection_input.py`: scrcpy touch/scroll handling and physical touch recording.
- `recording_event_service.py`: recording context and JSONL event append.
- `maintenance_service.py`: clear database/data directories and restart background processors.
- `execution_engine.py`: session execution, video recording, scene recognition loop.

### Analysis

Model and image analysis lives under `analysis/`.

- `click_target_pipeline.py`: runtime rule -> YOLO -> hash -> LLM click target pipeline.
- `click_image_helpers.py` and `image_metrics.py`: click bbox and image-difference helpers.
- `yolo_detection.py`: YOLO model detection and click-object selection.
- `llm_click_description.py`: LLM click target fallback.
- `gpt_yolo_annotation.py`: GPT YOLO object annotation.
- `event_unknown_queue.py`, `event_unknown_processor.py`, `touch_index_writer.py`: background unknown-event flow.
- `reanalyze_prompt.py`, `reanalyze_response.py`, `reanalyze_providers.py`, `scene_reclassification.py`: reanalysis flow.
- `yolo_annotation_files.py`, `yolo_review_actions.py`, `yolo_training.py`, `runtime_index_compile.py`, `yolo_class_utils.py`: YOLO review/training/runtime-index flow.

### Data

The existing data layer remains in:

- `agent_data.py`: current data manager facade.
- `data/agent_schema.py`: game data directories and database schema initialization.
- `data/event_store.py`: recording event JSONL construction and append.
- `domain/coordinate_mapper.py`: pure coordinate mapping helpers.
- `repositories/`: repository methods for events, runtime rules, sessions, stats, and UI elements.
- `scene_index.py`: scene index database and fingerprint/classification utilities.

`agent_data.py` is now a small compatibility facade. The remaining data work is mostly inside repository modules and `scene_index.py`.

## Size After Refactor

- `main.py`: about 590 lines, down from 5600+.
- Largest remaining focused modules:
  - `ui/panels/yolo_audit_panel.py`: about 430 lines.
  - `analysis/reanalyze_providers.py`: about 293 lines.
  - `ui/panels/rules_setup_panel.py`: about 214 lines.
  - `analysis/click_target_pipeline.py`: about 280 lines.

Service and analysis modules are now below 300 lines. Most UI modules are below 300 lines except the YOLO audit tab builder, which still contains tightly coupled widget state and callback closures.

These are now separated by function area rather than mixed inside one window class.

## Verification

Required checks:

```text
venv\Scripts\python.exe -m compileall -q .
venv\Scripts\python.exe -c "import main; print('main import ok')"
```

Both checks pass after the split.

## Remaining Follow-Up

The next quality pass should convert the mixins into dependency-injected service objects where it makes sense:

- turn the most stable mixins into dependency-injected service objects;
- convert `ui/panels/yolo_audit_panel.py` from nested callback closures to a small context/presenter object before splitting it further;
- continue breaking SQL-heavy repository methods where needed;
- add small tests for coordinate conversion, event JSON building, response normalization, and repository mutations.
