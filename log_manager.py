import threading
from collections import deque


class LogManager:
    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._deque = deque()
        self._deque_lock = threading.Lock()

    def append(self, msg: str):
        with self._deque_lock:
            self._deque.append(msg)

    def get_and_clear(self) -> list[str]:
        with self._deque_lock:
            items = list(self._deque)
            self._deque.clear()
            return items

    def clear(self):
        with self._deque_lock:
            self._deque.clear()
