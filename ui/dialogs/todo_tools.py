import json
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from log_manager import LogManager


def show_yolo_class_merge(parent=None):
    from agent_data import GAME_DATA_DIR
    from yolo_class_merge_dialog import YoloClassMergeDialog

    classes_txt = GAME_DATA_DIR / "yolo_events" / "classes.txt"
    labels_dir = GAME_DATA_DIR / "yolo_events" / "labels" / "train"
    dialog = YoloClassMergeDialog(classes_txt, labels_dir if labels_dir.exists() else None, parent)
    dialog.exec()


def show_batch_scene_register(parent=None):
    from scene_batch_register_dialog import SceneBatchRegisterDialog

    unknown_dir = Path("screenshots/unknown")
    dialog = SceneBatchRegisterDialog(unknown_dir, parent)
    dialog.exec()


def show_fast_feature(parent=None):
    from fast_feature import FastFeatureExtractor, build_full_ui_tree

    path, _ = QFileDialog.getOpenFileName(
        parent, "Select Screenshot", "screenshots", "Images (*.png *.jpg *.jpeg)"
    )
    if not path:
        return

    dialog = QDialog(parent)
    dialog.setWindowTitle("FastFeature Analysis")
    dialog.resize(800, 600)
    layout = QVBoxLayout(dialog)
    label = QLabel(f"Analyzing: {Path(path).name}")
    layout.addWidget(label)
    text = QTextEdit()
    text.setReadOnly(True)
    layout.addWidget(text)
    try:
        extractor = FastFeatureExtractor()
        result = extractor.extract(path)
        tree = build_full_ui_tree(result)
        text.setPlainText(json.dumps(tree, ensure_ascii=False, indent=2))
    except Exception as exc:
        text.setPlainText(f"Error: {exc}")
    dialog.exec()


def show_migration_tool(parent=None):
    from agent_data import GAME_DATA_DIR
    from migration_tool import HistoricalMigrationTool

    dialog = QDialog(parent)
    dialog.setWindowTitle("Historical Batch Migration")
    dialog.resize(700, 500)
    layout = QVBoxLayout(dialog)
    info = QLabel(f"Target DB: {GAME_DATA_DIR / 'agent.db'}")
    layout.addWidget(info)
    log = QTextEdit()
    log.setReadOnly(True)
    layout.addWidget(log)

    btn_jsonl = QPushButton("Migrate operations.jsonl")

    def _do_jsonl():
        fp, _ = QFileDialog.getOpenFileName(dialog, "Select JSONL", "", "JSONL (*.jsonl)")
        if fp:
            report = HistoricalMigrationTool(GAME_DATA_DIR / "agent.db", backup=True).migrate_from_legacy_jsonl(Path(fp))
            log.append(f"Events: {report.migrated_events}, Scenes: {report.migrated_scenes}, Errors: {len(report.errors)}")

    btn_jsonl.clicked.connect(_do_jsonl)
    layout.addWidget(btn_jsonl)

    btn_scenes = QPushButton("Migrate legacy scenes folder")

    def _do_scenes():
        dp = QFileDialog.getExistingDirectory(dialog, "Select Scenes Folder")
        if dp:
            report = HistoricalMigrationTool(GAME_DATA_DIR / "agent.db", backup=True).migrate_legacy_scenes_folder(Path(dp))
            log.append(f"Scenes: {report.migrated_scenes}, Errors: {len(report.errors)}")

    btn_scenes.clicked.connect(_do_scenes)
    layout.addWidget(btn_scenes)

    btn_close = QPushButton("Close")
    btn_close.clicked.connect(dialog.accept)
    layout.addWidget(btn_close)
    dialog.exec()


def show_cloud_sync(parent=None):
    from agent_data import GAME_DATA_DIR
    from cloud_sync import CloudSyncManager, SyncConfig

    config_path = GAME_DATA_DIR / "cloud_sync.json"
    config = CloudSyncManager.load_config(config_path)
    dialog = QDialog(parent)
    dialog.setWindowTitle("Cloud Sync Config")
    dialog.resize(600, 400)
    layout = QVBoxLayout(dialog)
    provider = QComboBox()
    provider.addItems(["local", "webdav", "s3"])
    provider.setCurrentText(config.provider)
    layout.addWidget(QLabel("Provider:"))
    layout.addWidget(provider)
    endpoint = QLineEdit(config.endpoint)
    endpoint.setPlaceholderText("Path or URL")
    layout.addWidget(QLabel("Endpoint:"))
    layout.addWidget(endpoint)
    key = QLineEdit(config.access_key)
    key.setPlaceholderText("Access Key / Username")
    layout.addWidget(key)
    secret = QLineEdit(config.secret_key)
    secret.setPlaceholderText("Secret Key / Password")
    layout.addWidget(secret)
    sync_db = QCheckBox("Sync DB")
    sync_db.setChecked(config.sync_db)
    layout.addWidget(sync_db)
    sync_shots = QCheckBox("Sync Screenshots")
    sync_shots.setChecked(config.sync_screenshots)
    layout.addWidget(sync_shots)
    log = QTextEdit()
    log.setReadOnly(True)
    log.setMaximumHeight(120)
    layout.addWidget(log)

    btn_save = QPushButton("Save & Sync Once")

    def _save():
        cfg = SyncConfig(
            enabled=True,
            provider=provider.currentText(),
            endpoint=endpoint.text().strip(),
            access_key=key.text().strip(),
            secret_key=secret.text().strip(),
            sync_db=sync_db.isChecked(),
            sync_screenshots=sync_shots.isChecked(),
        )
        mgr = CloudSyncManager(cfg, GAME_DATA_DIR)
        mgr.register_callback(lambda message: log.append(message))
        mgr.save_config(config_path)
        mgr.sync_once()

    btn_save.clicked.connect(_save)
    layout.addWidget(btn_save)
    btn_close = QPushButton("Close")
    btn_close.clicked.connect(dialog.accept)
    layout.addWidget(btn_close)
    dialog.exec()


def show_rl_stats(parent=None):
    from agent_data import GAME_DATA_DIR
    from rl_optimizer import RLOptimizer

    dialog = QDialog(parent)
    dialog.setWindowTitle("RL Optimizer Stats")
    dialog.resize(500, 400)
    layout = QVBoxLayout(dialog)
    rl = RLOptimizer(GAME_DATA_DIR / "rl_policy.json")
    stats = rl.report()
    info = QLabel(f"States: {stats['states']} | Actions: {stats['actions']} | Avg Q: {stats['avg_q']}")
    layout.addWidget(info)
    text = QTextEdit()
    text.setReadOnly(True)
    text.setPlainText(json.dumps(stats, ensure_ascii=False, indent=2))
    layout.addWidget(text)
    btn_close = QPushButton("Close")
    btn_close.clicked.connect(dialog.accept)
    layout.addWidget(btn_close)
    dialog.exec()


def switch_game(parent, execution_engine, set_status):
    games_dir = Path("game_agent_data/games")
    games = [d.name for d in games_dir.iterdir() if d.is_dir()] if games_dir.exists() else []
    if not games:
        games = ["my_game"]
    text, ok = QInputDialog.getItem(parent, "Switch Game", "Select game:", games, editable=True)
    if ok and text:
        from agent_data import AgentDataManager, set_game_data_dir

        set_game_data_dir(text)
        execution_engine.game_dir = AgentDataManager().game_dir
        set_status(f"Switched to game: {text}")
        LogManager().append(f"[GameSwitch] active game = {text}")
