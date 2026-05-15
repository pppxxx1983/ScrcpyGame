"""
场景线程基类
每个继承 BaseScene 的场景类都会拥有一个独立的 SceneThread 实例。
"""
import threading
import time

from log_manager import LogManager


class SceneThread(threading.Thread):
    """场景线程 - 默认空跑，被激活时执行场景任务。"""

    def __init__(self, scene_level: str, display_name: str):
        super().__init__(name=f"Scene-{display_name}", daemon=True)
        self.scene_level = scene_level
        self.display_name = display_name
        self._running = False
        self._active = False
        self._lock = threading.Lock()
        self._fps_counter = 0
        self._fps = 0.0
        self._fps_last_time = time.time()
        self._fps_lock = threading.Lock()

    def run(self):
        self._running = True
        while self._running:
            with self._lock:
                active = self._active
            if active:
                LogManager().append(f"[SceneThread] {self.display_name} 线程激活执行")
                self._count_fps()
                # TODO: 在这里扩展场景特定的执行逻辑
                with self._lock:
                    self._active = False
            else:
                # 空跑：短暂休眠后继续检查
                time.sleep(0.1)

    def _count_fps(self):
        with self._fps_lock:
            self._fps_counter += 1
            now = time.time()
            if now - self._fps_last_time >= 1.0:
                self._fps = self._fps_counter / (now - self._fps_last_time)
                self._fps_counter = 0
                self._fps_last_time = now

    def get_fps(self) -> float:
        with self._fps_lock:
            now = time.time()
            if now - self._fps_last_time >= 1.0:
                self._fps = 0.0
                self._fps_counter = 0
                self._fps_last_time = now
            return self._fps

    def activate(self):
        with self._lock:
            self._active = True

    def stop(self):
        self._running = False
