from __future__ import annotations







class YoloClassUtilsMixin:
    def _load_yolo_classes(self) -> list[str]:
        try:
            from agent_data import GAME_DATA_DIR

            path = GAME_DATA_DIR / "yolo_events" / "classes.txt"
            if not path.exists():
                return ["tap_target"]
            names = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            return names or ["tap_target"]
        except Exception:
            return ["tap_target"]

    def _ensure_yolo_class(self, class_name: str) -> int:
        from agent_data import GAME_DATA_DIR
        from yolo_class_manager import YoloClassManager

        mgr = YoloClassManager(GAME_DATA_DIR / "yolo_events" / "classes.txt")
        return mgr.ensure(class_name)

    def _yolo_classes_text(self) -> str:
        from agent_data import GAME_DATA_DIR
        from yolo_class_manager import YoloClassManager
        mgr = YoloClassManager(GAME_DATA_DIR / "yolo_events" / "classes.txt")
        return "\n".join(mgr.names) + "\n"

    def _yolo_data_yaml(self) -> str:
        from agent_data import GAME_DATA_DIR
        from yolo_class_manager import YoloClassManager
        mgr = YoloClassManager(GAME_DATA_DIR / "yolo_events" / "classes.txt")
        return mgr.to_data_yaml()

    def _safe_yolo_class_name(self, value: str) -> str:
        from yolo_class_manager import normalize_class_name
        return normalize_class_name(value)

