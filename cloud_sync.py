"""Cloud sync module for agent.db / screenshots / videos (TODO #29).
Supports WebDAV / S3-compatible / local network folder sync.
"""
from __future__ import annotations

import os
import json
import hashlib
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Callable
from threading import Thread, Event

from log_manager import LogManager


@dataclass
class SyncConfig:
    enabled: bool = False
    provider: str = "local"  # local / webdav / s3
    endpoint: str = ""  # URL or local path
    bucket: str = ""
    access_key: str = ""
    secret_key: str = ""  # or password for WebDAV
    remote_prefix: str = "scrcpygame_sync"
    sync_interval_sec: int = 300
    sync_db: bool = True
    sync_screenshots: bool = True
    sync_videos: bool = False


class CloudSyncManager:
    """Manage cloud synchronization with conflict resolution (last-write-wins)."""

    def __init__(self, config: SyncConfig, local_root: Path):
        self.config = config
        self.local_root = local_root
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._callbacks: List[Callable[[str], None]] = []

    def register_callback(self, cb: Callable[[str], None]):
        self._callbacks.append(cb)

    def _notify(self, msg: str):
        LogManager().append(f"[CloudSync] {msg}")
        for cb in self._callbacks:
            try:
                cb(msg)
            except Exception:
                pass

    def start_auto_sync(self):
        if not self.config.enabled or self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._sync_loop, daemon=True)
        self._thread.start()
        self._notify("Auto sync started")

    def stop_auto_sync(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self._notify("Auto sync stopped")

    def _sync_loop(self):
        while not self._stop_event.wait(self.config.sync_interval_sec):
            try:
                self.sync_once()
            except Exception as e:
                self._notify(f"Sync error: {e}")

    def sync_once(self):
        if not self.config.enabled:
            return
        if self.config.provider == "local":
            self._sync_local()
        elif self.config.provider == "webdav":
            self._sync_webdav()
        elif self.config.provider == "s3":
            self._sync_s3()

    # ------------------------------------------------------------------
    # Local folder sync (network share / NAS / rsync target)
    # ------------------------------------------------------------------
    def _sync_local(self):
        remote = Path(self.config.endpoint)
        if not remote.exists():
            self._notify(f"Remote path does not exist: {remote}")
            return
        remote_root = remote / self.config.remote_prefix
        remote_root.mkdir(parents=True, exist_ok=True)

        # Sync DB
        if self.config.sync_db:
            db_file = self.local_root / "agent.db"
            if db_file.exists():
                self._copy_if_newer(db_file, remote_root / "agent.db")
                # Pull back newer remote DB
                self._copy_if_newer(remote_root / "agent.db", db_file)

        # Sync screenshots
        if self.config.sync_screenshots:
            local_shots = Path("screenshots")
            remote_shots = remote_root / "screenshots"
            self._mirror_folder(local_shots, remote_shots)

        # Sync videos
        if self.config.sync_videos:
            local_vids = self.local_root / "raw_videos"
            remote_vids = remote_root / "raw_videos"
            if local_vids.exists():
                self._mirror_folder(local_vids, remote_vids)

        self._notify("Local sync completed")

    def _mirror_folder(self, src: Path, dst: Path):
        """One-way mirror: copy new/changed files from src to dst."""
        if not src.exists():
            return
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.rglob("*"):
            if item.is_dir():
                continue
            rel = item.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            self._copy_if_newer(item, target)

    def _copy_if_newer(self, src: Path, dst: Path):
        if not dst.exists():
            shutil.copy2(str(src), str(dst))
            return True
        if src.stat().st_mtime > dst.stat().st_mtime:
            shutil.copy2(str(src), str(dst))
            return True
        return False

    # ------------------------------------------------------------------
    # WebDAV sync
    # ------------------------------------------------------------------
    def _sync_webdav(self):
        try:
            import requests
        except ImportError:
            self._notify("requests library required for WebDAV sync")
            return
        # Lightweight WebDAV PUT/GET
        base = self.config.endpoint.rstrip("/")
        prefix = self.config.remote_prefix.strip("/")
        auth = (self.config.access_key, self.config.secret_key) if self.config.access_key else None

        def _upload(local_path: Path, remote_url: str):
            with local_path.open("rb") as f:
                r = requests.put(remote_url, data=f, auth=auth, timeout=60)
                if r.status_code not in (200, 201, 204):
                    raise RuntimeError(f"WebDAV PUT failed: {r.status_code}")

        # Sync DB
        if self.config.sync_db:
            db_file = self.local_root / "agent.db"
            if db_file.exists():
                remote_db_url = f"{base}/{prefix}/agent.db"
                _upload(db_file, remote_db_url)

        self._notify("WebDAV sync stub completed")

    # ------------------------------------------------------------------
    # S3 sync
    # ------------------------------------------------------------------
    def _sync_s3(self):
        try:
            import boto3
        except ImportError:
            self._notify("boto3 library required for S3 sync")
            return
        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=self.config.endpoint or None,
                aws_access_key_id=self.config.access_key,
                aws_secret_access_key=self.config.secret_key,
            )
            prefix = self.config.remote_prefix.strip("/")
            bucket = self.config.bucket

            # Upload DB
            if self.config.sync_db:
                db_file = self.local_root / "agent.db"
                if db_file.exists():
                    s3.upload_file(str(db_file), bucket, f"{prefix}/agent.db")

            self._notify("S3 sync stub completed")
        except Exception as e:
            self._notify(f"S3 sync failed: {e}")

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------
    @classmethod
    def load_config(cls, path: Path) -> SyncConfig:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return SyncConfig(**data)
            except Exception:
                pass
        return SyncConfig()

    def save_config(self, path: Path):
        path.write_text(json.dumps(self.config.__dict__, indent=2, ensure_ascii=False), encoding="utf-8")


class CloudSyncDialog:
    """Placeholder for Qt dialog; actual UI integration lives in main.py."""
    pass
