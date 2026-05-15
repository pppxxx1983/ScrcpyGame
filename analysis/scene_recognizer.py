"""
新场景识别系统 - 整合完整的场景层级
替代旧的场景索引
集成：
- scene_classes.py (场景类层级)
- scene_classifier.py (场景分类枚举)
- current_scene.py (当前场景管理)
- media_manager.py (媒体状态管理)
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import hashlib
from datetime import datetime

from PIL import Image

# 可选依赖 - imagehash
try:
    import imagehash
    _HAS_IMAGEHASH = True
except ImportError:
    _HAS_IMAGEHASH = False
    # 提供简单的备用hash计算
    import struct

from analysis.scene_classes import (
    BaseScene,
    SceneLevel,
    SceneState,
    SceneFactory,
    SceneManager,
)
from analysis.scene_classifier import (
    SCENE_LEVEL_DISPLAY,
    SCENE_STATE_DISPLAY,
    get_scene_full_name,
    parse_scene_type,
)
from analysis.current_scene import CurrentSceneManager
from analysis.media_manager import MediaStateManager, MediaState
from log_manager import LogManager


class SceneRecognizer:
    """
    场景识别器 - 整合新的场景层级系统
    """

    def __init__(self):
        self.scene_manager = SceneManager()
        self.current_scene_manager = CurrentSceneManager.get_instance()
        self.media_manager = MediaStateManager.get_instance()

    def compute_hashes(self, image_path: Path) -> Tuple[str, str, Optional[str]]:
        """
        计算图片的hash值
        :return: (dhash, ahash, phash)
        """
        try:
            if _HAS_IMAGEHASH:
                img = Image.open(image_path)
                dhash = str(imagehash.dhash(img))
                ahash = str(imagehash.average_hash(img))
                phash = str(imagehash.phash(img))
            else:
                # 备用方案 - 使用简单的MD5
                with open(image_path, 'rb') as f:
                    data = f.read()
                md5 = hashlib.md5(data).hexdigest()
                dhash = md5[:16]
                ahash = md5[16:]
                phash = None
            return dhash, ahash, phash
        except Exception as e:
            LogManager().append(f"[SceneRecognizer] 计算hash失败: {e}")
            return "", "", None

    def recognize_scene(
        self,
        image_path: Path,
        scene_key: Optional[str] = None,
        description: str = "",
    ) -> Optional[BaseScene]:
        """
        识别场景并创建场景对象
        :param image_path: 图片路径
        :param scene_key: 场景标识（可选，自动生成）
        :param description: 描述信息
        :return: 创建的场景对象
        """
        dhash, ahash, phash = self.compute_hashes(image_path)

        if not dhash or not ahash:
            LogManager().append("[SceneRecognizer] Hash计算失败，无法识别")
            return None

        # 自动生成scene_key
        if not scene_key:
            scene_key = self._generate_scene_key(dhash)

        # 根据hash推断场景层级
        scene_level = self._classify_level_by_hash(dhash)

        # 创建场景对象
        scene = SceneFactory.create(
            level=scene_level,
            scene_key=scene_key,
            dhash=dhash,
            ahash=ahash,
            phash=phash,
            image_path=str(image_path.absolute()),
            width=0,  # 可以补充实际尺寸
            height=0,
            description=description,
            model_name="new_system",
            recognize_cost=0.0,
            hits=1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # 注册到场景管理器
        self.scene_manager.register(scene)

        # 设置为当前场景
        self.current_scene_manager.set_current_scene(scene)

        LogManager().append(f"[SceneRecognizer] 识别场景: {scene_key} ({scene_level.value})")

        return scene

    def _generate_scene_key(self, dhash: str) -> str:
        """生成场景唯一标识"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_hash = dhash[:8]
        return f"scene_{timestamp}_{short_hash}"

    def _classify_level_by_hash(self, dhash: str) -> SceneLevel:
        """
        根据hash值分类场景层级
        (实际项目中可以训练模型或使用更复杂的规则)
        """
        if not dhash or len(dhash) < 8:
            return SceneLevel.UNKNOWN

        try:
            hash_value = int(dhash[:8], 16)
            mod_value = hash_value % 13

            level_mapping = {
                0: SceneLevel.MAIN_MENU,
                1: SceneLevel.GAME_PLAY,
                2: SceneLevel.DIALOG,
                3: SceneLevel.SETTINGS,
                4: SceneLevel.SHOP,
                5: SceneLevel.INVENTORY,
                6: SceneLevel.SOCIAL,
                7: SceneLevel.MAP,
                8: SceneLevel.BATTLE,
                9: SceneLevel.TUTORIAL,
                10: SceneLevel.LOADING,
                11: SceneLevel.TRANSITION,
                12: SceneLevel.DESKTOP,
            }

            return level_mapping.get(mod_value, SceneLevel.UNKNOWN)
        except Exception:
            return SceneLevel.UNKNOWN

    def find_similar_scene(
        self,
        dhash: str,
        threshold: float = 0.8,
    ) -> Optional[BaseScene]:
        """
        在已注册的场景中查找相似场景
        :param dhash: 待匹配的hash
        :param threshold: 相似度阈值
        :return: 找到的相似场景
        """
        return self.scene_manager.find_by_hash(dhash, threshold)

    def get_scenes_by_level(self, level: SceneLevel) -> list[BaseScene]:
        """获取指定层级的所有场景"""
        return self.scene_manager.get_all_by_level(level)

    def get_statistics(self) -> Dict[str, Any]:
        """获取识别统计信息"""
        scene_stats = self.scene_manager.count_by_level()
        current_scene = self.current_scene_manager.get_current_scene()
        media_stats = self.media_manager.get_stats()

        return {
            "registered_scenes": len(self.scene_manager),
            "by_level": scene_stats,
            "current_scene": {
                "scene_key": current_scene.scene_key if current_scene else None,
                "level": current_scene.LEVEL.value if current_scene else None,
                "state": current_scene.classify_state().value if current_scene else None,
            } if current_scene else None,
            "media_state": media_stats,
            "cache_info": self.current_scene_manager.get_cache_info(),
        }

    def clear_all(self):
        """清空所有场景数据"""
        self.scene_manager.clear()
        self.current_scene_manager.clear_history()
        self.current_scene_manager.clear_image_cache()


def recognize_scene_from_image(
    image_path: Path,
    scene_key: Optional[str] = None,
    description: str = "",
) -> Optional[BaseScene]:
    """
    便捷函数：从图片识别场景
    """
    recognizer = SceneRecognizer()
    return recognizer.recognize_scene(image_path, scene_key, description)


def get_recognition_statistics() -> Dict[str, Any]:
    """
    便捷函数：获取识别统计信息
    """
    recognizer = SceneRecognizer()
    return recognizer.get_statistics()
