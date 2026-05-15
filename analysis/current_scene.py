"""
当前场景管理器 - 单例模式
负责管理当前场景状态和图片内存缓存
"""

from __future__ import annotations
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
import weakref
import threading
from datetime import datetime

from analysis.scene_classes import BaseScene, SceneLevel, SceneState, SceneFactory


class CurrentSceneManager:
    """
    当前场景管理器 - 单例模式
    负责：
    1. 管理当前活动场景
    2. 图片内存缓存与释放
    3. 场景切换事件通知
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        """初始化管理器"""
        self._current_scene: Optional[BaseScene] = None
        self._previous_scene: Optional[BaseScene] = None
        self._scene_history: list[BaseScene] = []
        self._max_history_size = 10

        self._image_cache: Dict[str, Tuple[any, datetime, int]] = {}
        self._max_cache_size = 100
        self._max_memory_usage = 500 * 1024 * 1024  # 500MB

        self._listeners = []
        self._lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> 'CurrentSceneManager':
        """获取单例实例"""
        return cls()

    @classmethod
    def reset_instance(cls):
        """重置单例实例（用于测试）"""
        with cls._lock:
            cls._instance = None

    def set_current_scene(self, scene: BaseScene):
        """设置当前场景"""
        with self._lock:
            if self._current_scene:
                self._previous_scene = self._current_scene
                self._scene_history.append(self._current_scene)
                if len(self._scene_history) > self._max_history_size:
                    oldest = self._scene_history.pop(0)
                    self._release_scene_images(oldest)

            self._current_scene = scene

            if scene.image_path:
                self._cache_image(scene.scene_key, scene.image_path)

            self._notify_listeners('scene_changed', {
                'current': scene,
                'previous': self._previous_scene,
                'timestamp': datetime.now()
            })

    def get_current_scene(self) -> Optional[BaseScene]:
        """获取当前场景"""
        with self._lock:
            return self._current_scene

    def get_previous_scene(self) -> Optional[BaseScene]:
        """获取上一个场景"""
        with self._lock:
            return self._previous_scene

    def get_scene_history(self) -> list[BaseScene]:
        """获取场景历史记录"""
        with self._lock:
            return list(self._scene_history)

    def clear_history(self):
        """清除场景历史"""
        with self._lock:
            for scene in self._scene_history:
                self._release_scene_images(scene)
            self._scene_history.clear()

    def get_image(self, scene_key: str) -> Optional[any]:
        """获取场景图片（从缓存）"""
        with self._lock:
            if scene_key in self._image_cache:
                image, timestamp, size = self._image_cache[scene_key]
                self._image_cache[scene_key] = (image, datetime.now(), size)
                return image
        return None

    def _cache_image(self, scene_key: str, image_path: str):
        """缓存图片到内存"""
        if not image_path or not Path(image_path).exists():
            return

        with self._lock:
            if scene_key in self._image_cache:
                return

            try:
                image_data = self._load_image(image_path)
                if image_data:
                    size = len(image_data) if isinstance(image_data, bytes) else 0
                    self._image_cache[scene_key] = (image_data, datetime.now(), size)
                    self._enforce_memory_limits()
            except Exception as e:
                pass

    def _load_image(self, image_path: str) -> Optional[bytes]:
        """加载图片文件"""
        try:
            with open(image_path, 'rb') as f:
                return f.read()
        except Exception:
            return None

    def _release_scene_images(self, scene: BaseScene):
        """释放场景相关的图片缓存"""
        with self._lock:
            if scene.scene_key in self._image_cache:
                del self._image_cache[scene.scene_key]

    def _enforce_memory_limits(self):
        """强制执行内存限制"""
        with self._lock:
            total_size = sum(size for _, _, size in self._image_cache.values())

            while total_size > self._max_memory_usage and self._image_cache:
                oldest_key = min(
                    self._image_cache.keys(),
                    key=lambda k: self._image_cache[k][1]
                )
                size = self._image_cache[oldest_key][2]
                del self._image_cache[oldest_key]
                total_size -= size

            while len(self._image_cache) > self._max_cache_size:
                oldest_key = min(
                    self._image_cache.keys(),
                    key=lambda k: self._image_cache[k][1]
                )
                del self._image_cache[oldest_key]

    def clear_image_cache(self):
        """清空图片缓存"""
        with self._lock:
            self._image_cache.clear()

    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        with self._lock:
            total_size = sum(size for _, _, size in self._image_cache.values())
            return {
                'cache_size': len(self._image_cache),
                'total_memory_bytes': total_size,
                'total_memory_mb': round(total_size / (1024 * 1024), 2),
                'max_cache_size': self._max_cache_size,
                'max_memory_mb': round(self._max_memory_usage / (1024 * 1024), 2),
                'current_scene': self._current_scene.scene_key if self._current_scene else None,
                'history_size': len(self._scene_history)
            }

    def add_listener(self, callback):
        """添加场景变更监听器"""
        with self._lock:
            self._listeners.append(weakref.ref(callback))

    def remove_listener(self, callback):
        """移除场景变更监听器"""
        with self._lock:
            self._listeners = [
                ref for ref in self._listeners
                if ref() != callback
            ]

    def _notify_listeners(self, event_type: str, data: Dict[str, Any]):
        """通知所有监听器"""
        with self._lock:
            dead_refs = []
            for ref in self._listeners:
                callback = ref()
                if callback:
                    try:
                        callback(event_type, data)
                    except Exception:
                        pass
                else:
                    dead_refs.append(ref)

            for ref in dead_refs:
                self._listeners.remove(ref)

    def create_scene_from_dict(self, data: Dict[str, Any]) -> BaseScene:
        """从字典创建场景并设置为当前场景"""
        scene = SceneFactory.from_dict(data)
        self.set_current_scene(scene)
        return scene

    def update_scene_state(self, new_state: SceneState):
        """更新当前场景状态"""
        with self._lock:
            if self._current_scene:
                old_state = self._current_scene.classify_state()
                if old_state != new_state:
                    self._notify_listeners('state_changed', {
                        'scene': self._current_scene,
                        'old_state': old_state,
                        'new_state': new_state,
                        'timestamp': datetime.now()
                    })

    def __del__(self):
        """析构函数 - 清理资源"""
        self.clear_image_cache()
        self.clear_history()

    def __repr__(self):
        info = self.get_cache_info()
        return f"<CurrentSceneManager: {info['current_scene']}, cache={info['cache_size']}>"


def get_current_scene() -> Optional[BaseScene]:
    """便捷函数：获取当前场景"""
    return CurrentSceneManager.get_instance().get_current_scene()


def set_current_scene(scene: BaseScene):
    """便捷函数：设置当前场景"""
    CurrentSceneManager.get_instance().set_current_scene(scene)


def get_cache_stats() -> Dict[str, Any]:
    """便捷函数：获取缓存统计信息"""
    return CurrentSceneManager.get_instance().get_cache_info()
