"""
测试媒体状态管理器 - 视频播放和投屏互斥
"""

import pytest
from analysis.media_manager import (
    MediaStateManager,
    MediaState,
    MediaMode,
    get_media_state,
    start_video,
    start_casting,
    process_frame_to_scene,
    get_media_stats,
)


class TestMediaStateManager:
    """测试媒体状态管理器"""

    def setup_method(self):
        """每个测试前重置单例"""
        MediaStateManager.reset_instance()

    def teardown_method(self):
        """每个测试后清理"""
        MediaStateManager.reset_instance()

    def test_singleton_instance(self):
        """测试单例模式"""
        instance1 = MediaStateManager.get_instance()
        instance2 = MediaStateManager.get_instance()
        assert instance1 is instance2

    def test_initial_state(self):
        """测试初始状态"""
        manager = MediaStateManager.get_instance()
        assert manager.get_state() == MediaState.IDLE
        assert manager.get_mode() is None
        assert not manager.is_running()

    def test_video_playback_start(self):
        """测试启动视频播放"""
        manager = MediaStateManager.get_instance()
        result = manager.start_video_playback(MediaMode.LOCAL_VIDEO, "test.mp4")

        assert result is True
        assert manager.get_state() == MediaState.VIDEO_PLAYING
        assert manager.get_mode() == MediaMode.LOCAL_VIDEO
        assert manager.is_running()

    def test_screen_casting_start(self):
        """测试启动投屏"""
        manager = MediaStateManager.get_instance()
        result = manager.start_screen_casting(MediaMode.USB_SCREEN, "device_001")

        assert result is True
        assert manager.get_state() == MediaState.SCREEN_CASTING
        assert manager.get_mode() == MediaMode.USB_SCREEN
        assert manager.is_running()

    def test_video_while_casting(self):
        """测试投屏时启动视频 - 应自动停止投屏"""
        manager = MediaStateManager.get_instance()

        manager.start_screen_casting(MediaMode.USB_SCREEN, "device_001")
        assert manager.get_state() == MediaState.SCREEN_CASTING

        result = manager.start_video_playback(MediaMode.LOCAL_VIDEO, "test.mp4")
        assert result is True
        assert manager.get_state() == MediaState.VIDEO_PLAYING
        assert manager.get_mode() == MediaMode.LOCAL_VIDEO

    def test_casting_while_video(self):
        """测试视频播放时启动投屏 - 应自动停止视频"""
        manager = MediaStateManager.get_instance()

        manager.start_video_playback(MediaMode.LOCAL_VIDEO, "test.mp4")
        assert manager.get_state() == MediaState.VIDEO_PLAYING

        result = manager.start_screen_casting(MediaMode.USB_SCREEN, "device_001")
        assert result is True
        assert manager.get_state() == MediaState.SCREEN_CASTING
        assert manager.get_mode() == MediaMode.USB_SCREEN

    def test_duplicate_video_start(self):
        """测试重复启动视频 - 应返回False"""
        manager = MediaStateManager.get_instance()

        manager.start_video_playback(MediaMode.LOCAL_VIDEO, "test.mp4")
        result = manager.start_video_playback(MediaMode.RTSP_STREAM, "rtsp://test")

        assert result is False
        assert manager.get_state() == MediaState.VIDEO_PLAYING
        assert manager.get_mode() == MediaMode.LOCAL_VIDEO

    def test_duplicate_casting_start(self):
        """测试重复启动投屏 - 应返回False"""
        manager = MediaStateManager.get_instance()

        manager.start_screen_casting(MediaMode.USB_SCREEN, "device_001")
        result = manager.start_screen_casting(MediaMode.WIFI_SCREEN, "device_002")

        assert result is False
        assert manager.get_state() == MediaState.SCREEN_CASTING
        assert manager.get_mode() == MediaMode.USB_SCREEN

    def test_stop_video(self):
        """测试停止视频播放"""
        manager = MediaStateManager.get_instance()

        manager.start_video_playback(MediaMode.LOCAL_VIDEO, "test.mp4")
        manager.stop_video_playback()

        assert manager.get_state() == MediaState.IDLE
        assert manager.get_mode() is None
        assert not manager.is_running()

    def test_stop_casting(self):
        """测试停止投屏"""
        manager = MediaStateManager.get_instance()

        manager.start_screen_casting(MediaMode.USB_SCREEN, "device_001")
        manager.stop_screen_casting()

        assert manager.get_state() == MediaState.IDLE
        assert manager.get_mode() is None
        assert not manager.is_running()

    def test_switch_to_video(self):
        """测试切换到视频模式"""
        manager = MediaStateManager.get_instance()

        manager.start_screen_casting(MediaMode.USB_SCREEN, "device_001")
        result = manager.switch_to_video(MediaMode.RTSP_STREAM, "rtsp://test")

        assert result is True
        assert manager.get_state() == MediaState.VIDEO_PLAYING
        assert manager.get_mode() == MediaMode.RTSP_STREAM

    def test_switch_to_casting(self):
        """测试切换到投屏模式"""
        manager = MediaStateManager.get_instance()

        manager.start_video_playback(MediaMode.LOCAL_VIDEO, "test.mp4")
        result = manager.switch_to_casting(MediaMode.WIFI_SCREEN, "device_002")

        assert result is True
        assert manager.get_state() == MediaState.SCREEN_CASTING
        assert manager.get_mode() == MediaMode.WIFI_SCREEN

    def test_toggle_state(self):
        """测试状态切换"""
        manager = MediaStateManager.get_instance()

        assert manager.get_state() == MediaState.IDLE

        manager.toggle_state()
        assert manager.get_state() == MediaState.VIDEO_PLAYING

        manager.toggle_state()
        assert manager.get_state() == MediaState.SCREEN_CASTING

        manager.toggle_state()
        assert manager.get_state() == MediaState.IDLE

    def test_process_frame(self):
        """测试处理帧并传递给场景"""
        manager = MediaStateManager.get_instance()

        manager.start_video_playback(MediaMode.LOCAL_VIDEO, "test.mp4")
        manager.process_frame(b"test_frame_data", "abcdef1234567890", "1234567890abcdef")

        stats = manager.get_stats()
        assert stats['frame_count'] == 1
        assert stats['current_scene'] is not None

    def test_process_frame_when_not_running(self):
        """测试未运行时处理帧"""
        manager = MediaStateManager.get_instance()

        manager.process_frame(b"test_frame_data", "abcdef", "123456")

        stats = manager.get_stats()
        assert stats['frame_count'] == 0

    def test_get_stats(self):
        """测试获取统计信息"""
        manager = MediaStateManager.get_instance()

        manager.start_video_playback(MediaMode.LOCAL_VIDEO, "test.mp4")
        manager.process_frame(b"frame1", "dhash1", "ahash1")
        manager.process_frame(b"frame2", "dhash2", "ahash2")

        stats = manager.get_stats()

        assert stats['state'] == 'video_playing'
        assert stats['mode'] == 'local_video'
        assert stats['is_running'] is True
        assert stats['frame_count'] == 2

    def test_convenience_functions(self):
        """测试便捷函数"""
        start_video(MediaMode.LOCAL_VIDEO, "test.mp4")
        assert get_media_state() == MediaState.VIDEO_PLAYING

        process_frame_to_scene(b"frame", "dhash", "ahash")
        stats = get_media_stats()
        assert stats['frame_count'] == 1

        start_casting(MediaMode.USB_SCREEN, "device_001")
        assert get_media_state() == MediaState.SCREEN_CASTING

    def test_listener_notification(self):
        """测试监听器通知"""
        manager = MediaStateManager.get_instance()
        events = []

        def callback(event_type, data):
            events.append((event_type, data))

        manager.add_listener(callback)

        manager.start_video_playback(MediaMode.LOCAL_VIDEO, "test.mp4")
        manager.process_frame(b"frame", "dhash", "ahash")
        manager.stop_video_playback()

        assert len(events) >= 3
        assert events[0][0] == 'video_started'
        assert events[1][0] == 'frame_processed'
        assert events[2][0] == 'video_stopped'
