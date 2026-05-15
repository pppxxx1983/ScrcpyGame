from __future__ import annotations

import threading
from collections import deque
from typing import Optional


class LogManager:
    """Thread-safe singleton log manager."""

    _instance: Optional["LogManager"] = None
    _init_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "LogManager":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        self._deque: deque[str] = deque()
        self._deque_lock: threading.Lock = threading.Lock()

    def append(self, msg: str) -> None:
        with self._deque_lock:
            self._deque.append(msg)

    def get_and_clear(self) -> list[str]:
        with self._deque_lock:
            items = list(self._deque)
            self._deque.clear()
            return items

    def clear(self) -> None:
        with self._deque_lock:
            self._deque.clear()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (useful for testing)."""
        with cls._init_lock:
            if cls._instance is not None:
                cls._instance._deque.clear()
            cls._instance = None
