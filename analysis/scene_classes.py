"""
场景类层级体系

为每个场景层级创建独立的类，包含hash值和识别相关属性。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime
from enum import Enum

if TYPE_CHECKING:
    from analysis.scene.thread import SceneThread


class SceneLevel(Enum):
    """场景层级枚举"""
    MAIN_MENU = "main_menu"
    GAME_PLAY = "game_play"
    DIALOG = "dialog"
    SETTINGS = "settings"
    SHOP = "shop"
    INVENTORY = "inventory"
    SOCIAL = "social"
    MAP = "map"
    BATTLE = "battle"
    TUTORIAL = "tutorial"
    LOADING = "loading"
    TRANSITION = "transition"
    DESKTOP = "desktop"
    UNKNOWN = "unknown"


class SceneState(Enum):
    """场景状态枚举"""
    TITLE = "title"
    SERVER_SELECT = "server_select"
    CHARACTER_SELECT = "char_select"
    HOME = "home"
    EXPLORING = "exploring"
    QUEST_ACTIVE = "quest_active"
    QUEST_COMPLETE = "quest_done"
    DIALOG_TALKING = "talking"
    DIALOG_CHOICE = "choice"
    DIALOG_CUTSCENE = "cutscene"
    POPUP_REWARD = "reward"
    POPUP_ACHIEVEMENT = "achievement"
    POPUP_NOTICE = "notice"
    POPUP_ERROR = "error"
    POPUP_CONFIRM = "confirm"
    SETTINGS_AUDIO = "settings_audio"
    SETTINGS_VIDEO = "settings_video"
    SETTINGS_CONTROL = "settings_control"
    SHOP_MAIN = "shop_main"
    SHOP_ITEM_DETAIL = "shop_item"
    SHOP_PURCHASE_CONFIRM = "shop_buy"
    INV_MAIN = "inv_main"
    INV_ITEM_DETAIL = "inv_item"
    INV_EQUIP = "inv_equip"
    SOCIAL_FRIEND = "friend"
    SOCIAL_GUILD = "guild"
    SOCIAL_CHAT = "chat"
    MAP_WORLD = "world_map"
    MAP_DUNGEON = "dungeon_map"
    MAP_NAVI = "navigation"
    BATTLE_AUTO = "battle_auto"
    BATTLE_MANUAL = "battle_manual"
    BATTLE_PAUSED = "battle_paused"
    BATTLE_VICTORY = "victory"
    BATTLE_DEFEAT = "defeat"
    TUTORIAL_STEP_1 = "tut_step1"
    TUTORIAL_STEP_2 = "tut_step2"
    TUTORIAL_STEP_N = "tut_stepN"
    LOADING_GAME = "loading_game"
    LOADING_SCENE = "loading_scene"
    LOADING_RESOURCE = "loading_res"
    TRANSITION_STORY = "story"
    TRANSITION_CINEMATIC = "cinema"
    DESKTOP_MAIN = "desktop_main"
    DESKTOP_APP = "desktop_app"
    DESKTOP_WIDGET = "desktop_widget"


class BaseScene(ABC):
    """
    场景基类
    所有场景类的基础，包含hash值和核心属性。
    每个继承自 BaseScene 的子类都拥有独立的 SceneThread。
    """

    LEVEL: SceneLevel = SceneLevel.UNKNOWN
    DISPLAY_NAME: str = "未知场景"
    _THREAD: Optional['SceneThread'] = None

    def __init__(
        self,
        scene_key: str,
        dhash: str,
        ahash: str,
        phash: Optional[str] = None,
        image_path: Optional[str] = None,
        width: int = 0,
        height: int = 0,
        description: str = "",
        model_name: str = "",
        recognize_cost: float = 0.0,
        hits: int = 0,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.scene_key = scene_key
        self.dhash = dhash
        self.ahash = ahash
        self.phash = phash
        self.image_path = image_path
        self.width = width
        self.height = height
        self.description = description
        self.model_name = model_name
        self.recognize_cost = recognize_cost
        self.hits = hits
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    @abstractmethod
    def classify_state(self) -> SceneState:
        """根据hash和内容识别具体状态"""
        pass

    @abstractmethod
    def is_valid(self) -> bool:
        """验证场景数据有效性"""
        pass

    # ------------------------------------------------------------------
    # 类级别线程管理（每个子类独立一个线程）
    # ------------------------------------------------------------------
    @classmethod
    def start_thread(cls):
        """启动该场景类的专属线程（如果未运行）。"""
        from analysis.scene.thread import SceneThread
        if cls._THREAD is None or not cls._THREAD.is_alive():
            cls._THREAD = SceneThread(cls.LEVEL.value, cls.DISPLAY_NAME)
            cls._THREAD.start()

    @classmethod
    def stop_thread(cls):
        """停止该场景类的专属线程。"""
        if cls._THREAD is not None:
            cls._THREAD.stop()
            cls._THREAD = None

    @classmethod
    def activate_thread(cls):
        """激活该场景类的专属线程。"""
        if cls._THREAD is not None and cls._THREAD.is_alive():
            cls._THREAD.activate()

    @classmethod
    def get_thread_fps(cls) -> float:
        """获取该场景类线程的当前 FPS。"""
        if cls._THREAD is not None and cls._THREAD.is_alive():
            return cls._THREAD.get_fps()
        return 0.0

    def get_hash_similarity(self, other: 'BaseScene') -> float:
        """计算与另一个场景的hash相似度"""
        if not self.dhash or not other.dhash:
            return 0.0
        return self._hamming_distance(self.dhash, other.dhash)

    @staticmethod
    def _hamming_distance(hash1: str, hash2: str) -> float:
        """计算两个hash的汉明距离相似度"""
        if len(hash1) != len(hash2):
            return 0.0
        distance = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
        return 1.0 - (distance / len(hash1))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "scene_key": self.scene_key,
            "level": self.LEVEL.value,
            "level_display": self.DISPLAY_NAME,
            "dhash": self.dhash,
            "ahash": self.ahash,
            "phash": self.phash,
            "image_path": self.image_path,
            "width": self.width,
            "height": self.height,
            "description": self.description,
            "model_name": self.model_name,
            "recognize_cost": self.recognize_cost,
            "hits": self.hits,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseScene':
        """从字典创建实例"""
        return cls(
            scene_key=data.get("scene_key", ""),
            dhash=data.get("dhash", ""),
            ahash=data.get("ahash", ""),
            phash=data.get("phash"),
            image_path=data.get("image_path"),
            width=data.get("width", 0),
            height=data.get("height", 0),
            description=data.get("description", ""),
            model_name=data.get("model_name", ""),
            recognize_cost=data.get("recognize_cost", 0.0),
            hits=data.get("hits", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
        )

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.scene_key} (dhash={self.dhash[:8]}...)>"

    def __eq__(self, other):
        if not isinstance(other, BaseScene):
            return False
        return self.dhash == other.dhash and self.scene_key == other.scene_key

    def __hash__(self):
        return hash((self.scene_key, self.dhash))


class MainMenuScene(BaseScene):
    """主菜单场景"""
    LEVEL = SceneLevel.MAIN_MENU
    DISPLAY_NAME = "主菜单"

    def classify_state(self) -> SceneState:
        """根据hash特征识别主菜单状态"""
        hash_patterns = {
            "title": ["00000000", "ffffff00", "80808080"],
            "server_select": ["a0a0a0a0", "c0c0c0c0"],
            "char_select": ["60606060", "40404040"],
            "home": ["20202020", "30303030"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(state.upper())
        return SceneState.HOME

    def is_valid(self) -> bool:
        return bool(self.dhash) and len(self.dhash) >= 16


class GamePlayScene(BaseScene):
    """游戏进行场景"""
    LEVEL = SceneLevel.GAME_PLAY
    DISPLAY_NAME = "游戏进行"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "exploring": ["e0e0e0e0", "d0d0d0d0"],
            "quest_active": ["f0f0f0f0", "e8e8e8e8"],
            "quest_done": ["f8f8f8f8", "fff0f0f0"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(state.upper())
        return SceneState.EXPLORING

    def is_valid(self) -> bool:
        return bool(self.dhash) and self.width > 0 and self.height > 0


class DialogScene(BaseScene):
    """对话框场景"""
    LEVEL = SceneLevel.DIALOG
    DISPLAY_NAME = "对话框"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "talking": ["10101010", "18181818"],
            "choice": ["28282828", "30303030"],
            "cutscene": ["48484848", "50505050"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(f"DIALOG_{state.upper()}")
        return SceneState.DIALOG_TALKING

    def is_valid(self) -> bool:
        return bool(self.dhash)


class SettingsScene(BaseScene):
    """设置界面场景"""
    LEVEL = SceneLevel.SETTINGS
    DISPLAY_NAME = "设置"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "audio": ["68686868", "70707070"],
            "video": ["78787878", "80808080"],
            "control": ["88888888", "90909090"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(f"SETTINGS_{state.upper()}")
        return SceneState.SETTINGS_AUDIO

    def is_valid(self) -> bool:
        return bool(self.dhash)


class ShopScene(BaseScene):
    """商店场景"""
    LEVEL = SceneLevel.SHOP
    DISPLAY_NAME = "商店"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "shop_main": ["98989898", "a0a0a0a0"],
            "shop_item": ["a8a8a8a8", "b0b0b0b0"],
            "shop_buy": ["b8b8b8b8", "c0c0c0c0"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(state.upper())
        return SceneState.SHOP_MAIN

    def is_valid(self) -> bool:
        return bool(self.dhash)


class InventoryScene(BaseScene):
    """背包场景"""
    LEVEL = SceneLevel.INVENTORY
    DISPLAY_NAME = "背包"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "inv_main": ["c8c8c8c8", "d0d0d0d0"],
            "inv_item": ["d8d8d8d8", "e0e0e0e0"],
            "inv_equip": ["e8e8e8e8", "f0f0f0f0"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(state.upper())
        return SceneState.INV_MAIN

    def is_valid(self) -> bool:
        return bool(self.dhash)


class SocialScene(BaseScene):
    """社交场景"""
    LEVEL = SceneLevel.SOCIAL
    DISPLAY_NAME = "社交"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "friend": ["08080808", "10101010"],
            "guild": ["18181818", "20202020"],
            "chat": ["28282828", "30303030"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(f"SOCIAL_{state.upper()}")
        return SceneState.SOCIAL_FRIEND

    def is_valid(self) -> bool:
        return bool(self.dhash)


class MapScene(BaseScene):
    """地图场景"""
    LEVEL = SceneLevel.MAP
    DISPLAY_NAME = "地图"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "world_map": ["38383838", "40404040"],
            "dungeon_map": ["48484848", "50505050"],
            "navigation": ["58585858", "60606060"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(f"MAP_{state.upper()}")
        return SceneState.MAP_WORLD

    def is_valid(self) -> bool:
        return bool(self.dhash)


class BattleScene(BaseScene):
    """战斗场景"""
    LEVEL = SceneLevel.BATTLE
    DISPLAY_NAME = "战斗"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "battle_auto": ["68686868", "70707070"],
            "battle_manual": ["78787878", "80808080"],
            "battle_paused": ["88888888", "90909090"],
            "victory": ["98989898", "a0a0a0a0"],
            "defeat": ["a8a8a8a8", "b0b0b0b0"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(state.upper())
        return SceneState.BATTLE_AUTO

    def is_valid(self) -> bool:
        return bool(self.dhash)


class TutorialScene(BaseScene):
    """新手引导场景"""
    LEVEL = SceneLevel.TUTORIAL
    DISPLAY_NAME = "新手引导"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "tut_step1": ["b8b8b8b8", "c0c0c0c0"],
            "tut_step2": ["c8c8c8c8", "d0d0d0d0"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(state.upper())
        return SceneState.TUTORIAL_STEP_N

    def is_valid(self) -> bool:
        return bool(self.dhash)


class LoadingScene(BaseScene):
    """加载场景"""
    LEVEL = SceneLevel.LOADING
    DISPLAY_NAME = "加载"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "loading_game": ["d8d8d8d8", "e0e0e0e0"],
            "loading_scene": ["e8e8e8e8", "f0f0f0f0"],
            "loading_res": ["f8f8f8f8", "fff0f0f0"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(state.upper())
        return SceneState.LOADING_SCENE

    def is_valid(self) -> bool:
        return bool(self.dhash)


class TransitionScene(BaseScene):
    """过场场景"""
    LEVEL = SceneLevel.TRANSITION
    DISPLAY_NAME = "过场"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "story": ["00000001", "00000002"],
            "cinema": ["00000003", "00000004"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(f"TRANSITION_{state.upper()}")
        return SceneState.TRANSITION_STORY

    def is_valid(self) -> bool:
        return bool(self.dhash)


class UnknownScene(BaseScene):
    """未知场景"""
    LEVEL = SceneLevel.UNKNOWN
    DISPLAY_NAME = "未知"

    def classify_state(self) -> SceneState:
        return SceneState.TITLE

    def is_valid(self) -> bool:
        return bool(self.dhash)


class SceneFactory:
    """场景工厂 - 根据层级创建对应场景类"""

    _level_map: Dict[SceneLevel, type] = {
        SceneLevel.MAIN_MENU: MainMenuScene,
        SceneLevel.GAME_PLAY: GamePlayScene,
        SceneLevel.DIALOG: DialogScene,
        SceneLevel.SETTINGS: SettingsScene,
        SceneLevel.SHOP: ShopScene,
        SceneLevel.INVENTORY: InventoryScene,
        SceneLevel.SOCIAL: SocialScene,
        SceneLevel.MAP: MapScene,
        SceneLevel.BATTLE: BattleScene,
        SceneLevel.TUTORIAL: TutorialScene,
        SceneLevel.LOADING: LoadingScene,
        SceneLevel.TRANSITION: TransitionScene,
        SceneLevel.DESKTOP: UnknownScene,  # 占位，文件末尾会替换为真正的 DesktopScene
        SceneLevel.UNKNOWN: UnknownScene,
    }

    @classmethod
    def create(cls, level: SceneLevel, **kwargs) -> BaseScene:
        """根据层级创建场景实例"""
        scene_class = cls._level_map.get(level, UnknownScene)
        return scene_class(**kwargs)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaseScene:
        """从字典创建场景实例"""
        level_str = data.get("level", "unknown")
        try:
            level = SceneLevel(level_str)
        except ValueError:
            level = SceneLevel.UNKNOWN
        data_copy = data.copy()
        data_copy.pop("level", None)
        return cls.create(level, **data_copy)

    @classmethod
    def get_class(cls, level: SceneLevel) -> type:
        """获取指定层级的场景类"""
        return cls._level_map.get(level, UnknownScene)


class SceneManager:
    """场景管理器 - 管理场景的注册、查询和匹配"""

    def __init__(self):
        self._scenes: Dict[str, BaseScene] = {}

    def register(self, scene: BaseScene):
        """注册场景"""
        key = f"{scene.LEVEL.value}_{scene.scene_key}"
        self._scenes[key] = scene

    def get(self, level: SceneLevel, scene_key: str) -> Optional[BaseScene]:
        """获取场景"""
        key = f"{level.value}_{scene_key}"
        return self._scenes.get(key)

    def find_by_hash(self, dhash: str, threshold: float = 0.8) -> Optional[BaseScene]:
        """根据hash查找相似场景"""
        for scene in self._scenes.values():
            if scene.get_hash_similarity(BaseScene("", dhash, "")) >= threshold:
                return scene
        return None

    def get_all_by_level(self, level: SceneLevel) -> list[BaseScene]:
        """获取指定层级的所有场景"""
        return [s for s in self._scenes.values() if s.LEVEL == level]

    def count_by_level(self) -> Dict[str, int]:
        """按层级统计场景数量"""
        counts: Dict[str, int] = {}
        for scene in self._scenes.values():
            level = scene.LEVEL.value
            counts[level] = counts.get(level, 0) + 1
        return counts

    def clear(self):
        """清空所有场景"""
        self._scenes.clear()

    def __len__(self):
        return len(self._scenes)

    def __iter__(self):
        return iter(self._scenes.values())
