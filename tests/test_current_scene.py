"""
测试当前场景管理器 - 单例模式和图片内存管理
"""

import pytest
from analysis.current_scene import (
    CurrentSceneManager,
    get_current_scene,
    set_current_scene,
    get_cache_stats,
)
from analysis.scene_classes import SceneFactory, SceneLevel, SceneState


class TestCurrentSceneManager:
    """测试当前场景管理器"""

    def setup_method(self):
        """每个测试前重置单例"""
        CurrentSceneManager.reset_instance()

    def teardown_method(self):
        """每个测试后清理"""
        CurrentSceneManager.reset_instance()

    def test_singleton_instance(self):
        """测试单例模式 - 多次获取同一实例"""
        instance1 = CurrentSceneManager.get_instance()
        instance2 = CurrentSceneManager.get_instance()
        instance3 = CurrentSceneManager()

        assert instance1 is instance2
        assert instance2 is instance3

    def test_set_and_get_current_scene(self):
        """测试设置和获取当前场景"""
        manager = CurrentSceneManager.get_instance()
        scene = SceneFactory.create(
            SceneLevel.BATTLE,
            scene_key="test_battle",
            dhash="abcdef1234567890",
            ahash="1234567890abcdef",
        )

        manager.set_current_scene(scene)
        current = manager.get_current_scene()

        assert current is not None
        assert current.scene_key == "test_battle"
        assert current.LEVEL == SceneLevel.BATTLE

    def test_scene_history(self):
        """测试场景历史记录"""
        manager = CurrentSceneManager.get_instance()

        scene1 = SceneFactory.create(SceneLevel.MAIN_MENU, scene_key="menu1", dhash="1", ahash="1")
        scene2 = SceneFactory.create(SceneLevel.GAME_PLAY, scene_key="game1", dhash="2", ahash="2")
        scene3 = SceneFactory.create(SceneLevel.BATTLE, scene_key="battle1", dhash="3", ahash="3")

        manager.set_current_scene(scene1)
        manager.set_current_scene(scene2)
        manager.set_current_scene(scene3)

        history = manager.get_scene_history()
        assert len(history) == 2
        assert history[0].scene_key == "menu1"
        assert history[1].scene_key == "game1"

        previous = manager.get_previous_scene()
        assert previous.scene_key == "game1"

    def test_history_size_limit(self):
        """测试历史记录大小限制"""
        manager = CurrentSceneManager.get_instance()

        for i in range(15):
            scene = SceneFactory.create(
                SceneLevel.GAME_PLAY,
                scene_key=f"scene_{i}",
                dhash=str(i),
                ahash=str(i)
            )
            manager.set_current_scene(scene)

        history = manager.get_scene_history()
        assert len(history) == 10

    def test_image_cache(self):
        """测试图片缓存功能"""
        manager = CurrentSceneManager.get_instance()

        scene = SceneFactory.create(
            SceneLevel.BATTLE,
            scene_key="cached_scene",
            dhash="abc",
            ahash="def",
            image_path="tests/test_image.png"
        )

        manager.set_current_scene(scene)

        cache_info = manager.get_cache_info()
        assert cache_info['cache_size'] >= 0

    def test_cache_info(self):
        """测试缓存信息获取"""
        manager = CurrentSceneManager.get_instance()
        info = manager.get_cache_info()

        assert 'cache_size' in info
        assert 'total_memory_bytes' in info
        assert 'total_memory_mb' in info
        assert 'max_cache_size' in info
        assert 'max_memory_mb' in info
        assert 'current_scene' in info
        assert 'history_size' in info

    def test_clear_cache(self):
        """测试清空缓存"""
        manager = CurrentSceneManager.get_instance()

        scene = SceneFactory.create(
            SceneLevel.BATTLE,
            scene_key="test_clear",
            dhash="test",
            ahash="test",
        )
        manager.set_current_scene(scene)

        manager.clear_image_cache()
        info = manager.get_cache_info()
        assert info['cache_size'] == 0

    def test_clear_history(self):
        """测试清空历史"""
        manager = CurrentSceneManager.get_instance()

        for i in range(3):
            scene = SceneFactory.create(
                SceneLevel.GAME_PLAY,
                scene_key=f"hist_{i}",
                dhash=str(i),
                ahash=str(i)
            )
            manager.set_current_scene(scene)

        assert len(manager.get_scene_history()) == 2

        manager.clear_history()
        assert len(manager.get_scene_history()) == 0

    def test_convenience_functions(self):
        """测试便捷函数"""
        scene = SceneFactory.create(
            SceneLevel.SHOP,
            scene_key="convenience_test",
            dhash="conv",
            ahash="conv",
        )

        set_current_scene(scene)
        current = get_current_scene()
        stats = get_cache_stats()

        assert current.scene_key == "convenience_test"
        assert stats['current_scene'] == "convenience_test"

    def test_listener_notification(self):
        """测试监听器通知机制"""
        manager = CurrentSceneManager.get_instance()
        events = []

        def callback(event_type, data):
            events.append((event_type, data))

        manager.add_listener(callback)

        scene = SceneFactory.create(
            SceneLevel.BATTLE,
            scene_key="listener_test",
            dhash="listen",
            ahash="listen",
        )

        manager.set_current_scene(scene)

        assert len(events) >= 1
        assert events[-1][0] == 'scene_changed'
        assert events[-1][1]['current'].scene_key == "listener_test"

    def test_create_from_dict(self):
        """测试从字典创建场景"""
        manager = CurrentSceneManager.get_instance()

        scene_data = {
            "scene_key": "dict_scene",
            "level": "battle",
            "dhash": "1234",
            "ahash": "5678",
        }

        scene = manager.create_scene_from_dict(scene_data)

        assert scene.scene_key == "dict_scene"
        assert scene.LEVEL == SceneLevel.BATTLE
        assert manager.get_current_scene() == scene

    def test_reset_instance(self):
        """测试重置单例实例"""
        manager1 = CurrentSceneManager.get_instance()
        scene = SceneFactory.create(SceneLevel.MAIN_MENU, scene_key="test", dhash="1", ahash="1")
        manager1.set_current_scene(scene)

        CurrentSceneManager.reset_instance()

        manager2 = CurrentSceneManager.get_instance()
        assert manager1 is not manager2
        assert manager2.get_current_scene() is None
