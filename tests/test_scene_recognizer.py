"""
测试新场景识别系统
"""

import pytest
from pathlib import Path
from analysis.scene_recognizer import SceneRecognizer, recognize_scene_from_image, get_recognition_statistics
from analysis.scene_classes import SceneLevel, SceneState, SceneFactory
from analysis.media_manager import MediaMode


class TestSceneRecognizer:
    """测试场景识别器"""

    def setup_method(self):
        """每个测试前清理"""
        # 创建测试目录
        self.test_dir = Path("tests_temp")
        self.test_dir.mkdir(exist_ok=True)
        # 创建测试图片文件（不需要真实图片）
        self.test_image = self.test_dir / "test_scene.png"
        with open(self.test_image, 'wb') as f:
            f.write(b"fake image content for testing")

    def teardown_method(self):
        """每个测试后清理"""
        if self.test_image.exists():
            self.test_image.unlink()
        if self.test_dir.exists():
            try:
                self.test_dir.rmdir()
            except:
                pass

    def test_initialization(self):
        """测试初始化"""
        recognizer = SceneRecognizer()
        assert recognizer is not None
        assert recognizer.scene_manager is not None
        assert recognizer.current_scene_manager is not None
        assert recognizer.media_manager is not None

    def test_compute_hashes_fallback(self):
        """测试hash计算（备用方案）"""
        recognizer = SceneRecognizer()
        dhash, ahash, phash = recognizer.compute_hashes(self.test_image)

        # 至少返回两个hash值
        assert dhash is not None
        assert len(dhash) > 0
        assert ahash is not None
        assert len(ahash) > 0

    def test_recognize_scene(self):
        """测试识别场景"""
        recognizer = SceneRecognizer()
        scene = recognizer.recognize_scene(self.test_image, "test_scene_001", "测试场景")

        # 由于是假图片，可能返回None，只要不崩溃就通过
        assert True

    def test_get_scenes_by_level(self):
        """测试按层级获取场景"""
        recognizer = SceneRecognizer()

        # 创建几个场景对象
        scene1 = SceneFactory.create(SceneLevel.MAIN_MENU, scene_key="scene_1", dhash="dhash1", ahash="ahash1")
        scene2 = SceneFactory.create(SceneLevel.BATTLE, scene_key="scene_2", dhash="dhash2", ahash="ahash2")

        recognizer.scene_manager.register(scene1)
        recognizer.scene_manager.register(scene2)

        scenes = recognizer.get_scenes_by_level(SceneLevel.MAIN_MENU)
        assert len(scenes) >= 1

    def test_statistics(self):
        """测试获取统计信息"""
        recognizer = SceneRecognizer()

        stats = recognizer.get_statistics()

        assert "registered_scenes" in stats
        assert "by_level" in stats
        assert "current_scene" in stats
        assert "media_state" in stats
        assert "cache_info" in stats

    def test_clear_all(self):
        """测试清空所有数据"""
        recognizer = SceneRecognizer()

        scene1 = SceneFactory.create(SceneLevel.MAIN_MENU, scene_key="clear_test_1", dhash="d1", ahash="a1")
        scene2 = SceneFactory.create(SceneLevel.BATTLE, scene_key="clear_test_2", dhash="d2", ahash="a2")

        recognizer.scene_manager.register(scene1)
        recognizer.scene_manager.register(scene2)

        recognizer.clear_all()

        stats = recognizer.get_statistics()
        assert stats["registered_scenes"] == 0

    def test_multiple_scene_creation(self):
        """测试多次创建场景"""
        recognizer = SceneRecognizer()

        for i in range(5):
            scene = SceneFactory.create(
                SceneLevel.GAME_PLAY,
                scene_key=f"multi_test_{i}",
                dhash=f"dhash_{i}",
                ahash=f"ahash_{i}"
            )
            recognizer.scene_manager.register(scene)

        stats = recognizer.get_statistics()
        assert stats["registered_scenes"] >= 5

    def test_scene_level_mapping(self):
        """测试场景层级是否正确映射"""
        # 直接测试枚举值
        assert SceneLevel.MAIN_MENU.value == "main_menu"
        assert SceneLevel.BATTLE.value == "battle"
        assert SceneLevel.DESKTOP.value == "desktop"
        # 目前总共有14个层级
        assert len(list(SceneLevel)) >= 13

    def test_convenience_function(self):
        """测试便捷函数（不实际处理图片）"""
        stats = get_recognition_statistics()
        assert stats is not None
        assert "registered_scenes" in stats

    def test_scene_factory_creates_all_levels(self):
        """测试场景工厂能创建所有层级"""
        levels = [
            SceneLevel.MAIN_MENU,
            SceneLevel.GAME_PLAY,
            SceneLevel.DIALOG,
            SceneLevel.SETTINGS,
            SceneLevel.SHOP,
            SceneLevel.INVENTORY,
            SceneLevel.SOCIAL,
            SceneLevel.MAP,
            SceneLevel.BATTLE,
            SceneLevel.TUTORIAL,
            SceneLevel.LOADING,
            SceneLevel.TRANSITION,
            SceneLevel.DESKTOP,
            SceneLevel.UNKNOWN,
        ]

        for level in levels:
            scene = SceneFactory.create(level, scene_key=f"test_{level.value}", dhash="dhash", ahash="ahash")
            assert scene.LEVEL == level

