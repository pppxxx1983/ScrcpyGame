"""
媒体状态管理器 - 处理视频播放和投屏的互斥状态
确保视频播放和投屏只能执行一种状态，并将图片喂给当前场景
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, Callable, Dict, Any
import threading
from datetime import datetime

from analysis.current_scene import CurrentSceneManager
from analysis.scene_classes import SceneFactory, SceneLevel


class MediaState(Enum):
    """媒体状态枚举 - 视频播放和投屏互斥"""
    IDLE = "idle"              # 空闲状态
    VIDEO_PLAYING = "video_playing"  # 视频播放中
    SCREEN_CASTING = "screen_casting" # 投屏中


class MediaMode(Enum):
    """媒体模式枚举"""
    LOCAL_VIDEO = "local_video"    # 本地视频文件
    RTSP_STREAM = "rtsp_stream"    # RTSP流
    USB_SCREEN = "usb_screen"      # USB投屏
    WIFI_SCREEN = "wifi_screen"    # WiFi投屏


class MediaStateManager:
    """
    媒体状态管理器 - 单例模式
    负责：
    1. 管理视频播放和投屏的互斥状态
    2. 将图片帧传递给当前场景管理器
    3. 提供状态切换的事件通知
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
        self._current_state = MediaState.IDLE
        self._current_mode: Optional[MediaMode] = None
        self._is_running = False
        self._frame_count = 0
        self._last_frame_time = datetime.now()
        self._listeners = []
        self._lock = threading.RLock()
        self._scene_manager = CurrentSceneManager.get_instance()

    @classmethod
    def get_instance(cls) -> 'MediaStateManager':
        """获取单例实例"""
        return cls()

    @classmethod
    def reset_instance(cls):
        """重置单例实例（用于测试）"""
        with cls._lock:
            cls._instance = None

    def start_video_playback(self, mode: MediaMode, source: str) -> bool:
        """
        开始视频播放
        :param mode: 视频模式
        :param source: 视频源（文件路径或RTSP URL）
        :return: 是否成功启动
        """
        with self._lock:
            if self._current_state != MediaState.IDLE:
                if self._current_state == MediaState.SCREEN_CASTING:
                    self.stop_screen_casting()
                else:
                    return False

            self._current_state = MediaState.VIDEO_PLAYING
            self._current_mode = mode
            self._is_running = True
            self._frame_count = 0

            self._notify_listeners('video_started', {
                'mode': mode.value,
                'source': source,
                'timestamp': datetime.now()
            })

            return True

    def stop_video_playback(self):
        """停止视频播放"""
        with self._lock:
            if self._current_state == MediaState.VIDEO_PLAYING:
                self._current_state = MediaState.IDLE
                self._is_running = False

                self._notify_listeners('video_stopped', {
                    'mode': self._current_mode.value if self._current_mode else None,
                    'frame_count': self._frame_count,
                    'timestamp': datetime.now()
                })

                self._current_mode = None

    def start_screen_casting(self, mode: MediaMode, device: str = "") -> bool:
        """
        开始投屏
        :param mode: 投屏模式
        :param device: 设备标识
        :return: 是否成功启动
        """
        with self._lock:
            if self._current_state != MediaState.IDLE:
                if self._current_state == MediaState.VIDEO_PLAYING:
                    self.stop_video_playback()
                else:
                    return False

            self._current_state = MediaState.SCREEN_CASTING
            self._current_mode = mode
            self._is_running = True
            self._frame_count = 0

            self._notify_listeners('casting_started', {
                'mode': mode.value,
                'device': device,
                'timestamp': datetime.now()
            })

            return True

    def stop_screen_casting(self):
        """停止投屏"""
        with self._lock:
            if self._current_state == MediaState.SCREEN_CASTING:
                self._current_state = MediaState.IDLE
                self._is_running = False

                self._notify_listeners('casting_stopped', {
                    'mode': self._current_mode.value if self._current_mode else None,
                    'frame_count': self._frame_count,
                    'timestamp': datetime.now()
                })

                self._current_mode = None

    def process_frame(self, frame_data: bytes, dhash: str, ahash: str, phash: Optional[str] = None):
        """
        处理图片帧 - 将帧传递给当前场景管理器
        :param frame_data: 图片数据（字节）
        :param dhash: 差分哈希
        :param ahash: 平均哈希
        :param phash: 感知哈希（可选）
        """
        with self._lock:
            if not self._is_running:
                return

            self._frame_count += 1
            self._last_frame_time = datetime.now()

            scene_key = f"live_frame_{self._frame_count}"
            scene_level = self._infer_scene_level(dhash)

            scene = SceneFactory.create(
                level=scene_level,
                scene_key=scene_key,
                dhash=dhash,
                ahash=ahash,
                phash=phash,
            )

            self._scene_manager.set_current_scene(scene)

            self._notify_listeners('frame_processed', {
                'frame_count': self._frame_count,
                'scene_level': scene_level.value,
                'dhash': dhash,
                'timestamp': datetime.now()
            })

    def _infer_scene_level(self, dhash: str) -> SceneLevel:
        """根据hash值推断场景层级"""
        if not dhash or len(dhash) < 8:
            return SceneLevel.UNKNOWN
        try:
            hash_int = int(dhash[:8], 16)
            if hash_int % 3 == 0:
                return SceneLevel.GAME_PLAY
            elif hash_int % 3 == 1:
                return SceneLevel.BATTLE
            else:
                return SceneLevel.DESKTOP
        except ValueError:
            return SceneLevel.UNKNOWN

    def get_state(self) -> MediaState:
        """获取当前状态"""
        with self._lock:
            return self._current_state

    def get_mode(self) -> Optional[MediaMode]:
        """获取当前模式"""
        with self._lock:
            return self._current_mode

    def is_running(self) -> bool:
        """是否正在运行"""
        with self._lock:
            return self._is_running

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                'state': self._current_state.value,
                'mode': self._current_mode.value if self._current_mode else None,
                'is_running': self._is_running,
                'frame_count': self._frame_count,
                'last_frame_time': self._last_frame_time.isoformat() if self._last_frame_time else None,
                'current_scene': self._scene_manager.get_current_scene().scene_key if self._scene_manager.get_current_scene() else None,
            }

    def add_listener(self, callback: Callable[[str, Dict[str, Any]], None]):
        """添加状态变化监听器"""
        with self._lock:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str, Dict[str, Any]], None]):
        """移除状态变化监听器"""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify_listeners(self, event_type: str, data: Dict[str, Any]):
        """通知所有监听器"""
        with self._lock:
            for callback in self._listeners[:]:
                try:
                    callback(event_type, data)
                except Exception:
                    pass

    def switch_to_video(self, mode: MediaMode, source: str) -> bool:
        """切换到视频模式（强制切换）"""
        with self._lock:
            if self._current_state == MediaState.SCREEN_CASTING:
                self.stop_screen_casting()
            return self.start_video_playback(mode, source)

    def switch_to_casting(self, mode: MediaMode, device: str = "") -> bool:
        """切换到投屏模式（强制切换）"""
        with self._lock:
            if self._current_state == MediaState.VIDEO_PLAYING:
                self.stop_video_playback()
            return self.start_screen_casting(mode, device)

    def toggle_state(self) -> bool:
        """切换状态（空闲->视频->投屏->空闲）"""
        with self._lock:
            if self._current_state == MediaState.IDLE:
                return self.start_video_playback(MediaMode.LOCAL_VIDEO, "")
            elif self._current_state == MediaState.VIDEO_PLAYING:
                return self.start_screen_casting(MediaMode.USB_SCREEN)
            else:
                self.stop_screen_casting()
                return True

    def __del__(self):
        """析构函数"""
        self.stop_video_playback()
        self.stop_screen_casting()

    def __repr__(self):
        stats = self.get_stats()
        return f"<MediaStateManager: {stats['state']}, frames={stats['frame_count']}>"


def get_media_state() -> MediaState:
    """便捷函数：获取当前媒体状态"""
    return MediaStateManager.get_instance().get_state()


def start_video(mode: MediaMode, source: str) -> bool:
    """便捷函数：开始视频播放"""
    return MediaStateManager.get_instance().start_video_playback(mode, source)


def start_casting(mode: MediaMode, device: str = "") -> bool:
    """便捷函数：开始投屏"""
    return MediaStateManager.get_instance().start_screen_casting(mode, device)


def process_frame_to_scene(frame_data: bytes, dhash: str, ahash: str, phash: Optional[str] = None):
    """便捷函数：处理帧并传递给场景"""
    MediaStateManager.get_instance().process_frame(frame_data, dhash, ahash, phash)


def get_media_stats() -> Dict[str, Any]:
    """便捷函数：获取媒体统计信息"""
    return MediaStateManager.get_instance().get_stats()
