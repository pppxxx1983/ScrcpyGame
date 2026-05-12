from __future__ import annotations

import shutil
import subprocess
import threading


from log_manager import LogManager




class YoloTrainingMixin:
    def _start_yolo_training_async(self):
        def _train():
            try:
                from agent_data import GAME_DATA_DIR
                from ultralytics import YOLO

                yolo_dir = GAME_DATA_DIR / "yolo_events"
                data_yaml = yolo_dir / "data.yaml"
                if not data_yaml.exists():
                    LogManager().append("[YOLO] skip train: data.yaml missing")
                    return
                label_count = len(list((yolo_dir / "labels" / "train").glob("*.txt")))
                if label_count <= 0:
                    LogManager().append("[YOLO] skip train: no approved labels")
                    return

                best = yolo_dir / "runs" / "train" / "weights" / "best.pt"
                model_path = str(best) if best.exists() else "yolo11n.pt"
                LogManager().append(f"[YOLO] train start labels={label_count} model={model_path}")
                model = YOLO(model_path)
                model.train(
                    data=str(data_yaml),
                    epochs=20,
                    imgsz=640,
                    project=str(yolo_dir / "runs"),
                    name="train",
                    exist_ok=True,
                )
                LogManager().append("[YOLO] train done")
            except ImportError:
                LogManager().append("[YOLO] ultralytics not installed; run: pip install ultralytics")
            except Exception as e:
                LogManager().append(f"[YOLO] train failed: {e}")

        threading.Thread(target=_train, daemon=True).start()

    def _train_yolo_incremental(self):
        def _run():
            try:
                import shutil
                import subprocess
                from agent_data import GAME_DATA_DIR

                data_yaml = (GAME_DATA_DIR / "yolo_events" / "data.yaml").resolve()
                if not data_yaml.exists():
                    self._bridge.status_changed.emit("YOLO train: data.yaml missing", "#f44747")
                    return
                yolo_cmd = shutil.which("yolo")
                if not yolo_cmd:
                    self._bridge.status_changed.emit("YOLO train: install ultralytics first", "#f44747")
                    return
                weights_dir = (GAME_DATA_DIR / "yolo_events" / "runs" / "detect" / "train" / "weights").resolve()
                last_model = weights_dir / "last.pt"
                model = str(last_model if last_model.exists() else "yolov8n.pt")
                project = (GAME_DATA_DIR / "yolo_events" / "runs").resolve()
                cmd = [
                    yolo_cmd,
                    "detect",
                    "train",
                    f"data={data_yaml}",
                    f"model={model}",
                    "epochs=20",
                    "imgsz=640",
                    f"project={project}",
                    "exist_ok=True",
                ]
                LogManager().append(f"[YOLO] train command: {' '.join(map(str, cmd))}")
                self._bridge.status_changed.emit("YOLO train: running...", "#9cdcfe")
                proc = subprocess.run(
                    cmd,
                    cwd=str((GAME_DATA_DIR / "yolo_events").resolve()),
                    capture_output=True,
                    text=True,
                )
                if proc.stdout:
                    LogManager().append(proc.stdout[-4000:])
                if proc.stderr:
                    LogManager().append(proc.stderr[-4000:])
                if proc.returncode == 0:
                    self._bridge.status_changed.emit("YOLO train: completed", "#4ec9b0")
                else:
                    self._bridge.status_changed.emit(f"YOLO train failed: {proc.returncode}", "#f44747")
            except Exception as e:
                LogManager().append(f"[YOLO] train failed: {e}")
                self._bridge.status_changed.emit(f"YOLO train failed: {e}", "#f44747")

        threading.Thread(target=_run, daemon=True).start()

