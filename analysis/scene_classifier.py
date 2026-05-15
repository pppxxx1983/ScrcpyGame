"""
场景分类系统
定义多层级场景状态分类体系
"""

from __future__ import annotations
from enum import Enum
from typing import Optional


class SceneLevel(Enum):
    """场景层级 - 界面的整体层级"""
    MAIN_MENU = "main_menu"          # 主界面/菜单
    GAME_PLAY = "game_play"          # 游戏进行中
    DIALOG = "dialog"                # 对话框/弹窗
    SETTINGS = "settings"            # 设置界面
    SHOP = "shop"                    # 商店界面
    INVENTORY = "inventory"          # 背包/仓库
    SOCIAL = "social"                # 社交/公会
    MAP = "map"                      # 地图界面
    BATTLE = "battle"                # 战斗界面
    TUTORIAL = "tutorial"           # 新手引导
    LOADING = "loading"              # 加载界面
    TRANSITION = "transition"         # 过场/过渡
    DESKTOP = "desktop"              # 桌面界面
    UNKNOWN = "unknown"               # 未知界面


class SceneState(Enum):
    """场景状态 - 界面的具体状态"""
    # 主菜单状态
    TITLE = "title"                  # 标题画面
    SERVER_SELECT = "server_select"  # 服务器选择
    CHARACTER_SELECT = "char_select"  # 角色选择
    HOME = "home"                    # 主页/主城

    # 游戏进行状态
    EXPLORING = "exploring"          # 探索中
    QUEST_ACTIVE = "quest_active"    # 执行任务中
    QUEST_COMPLETE = "quest_done"    # 任务完成

    # 对话框状态
    DIALOG_TALKING = "talking"       # 对话中
    DIALOG_CHOICE = "choice"         # 选项对话
    DIALOG_CUTSCENE = "cutscene"    # 动画对话

    # 弹窗状态
    POPUP_REWARD = "reward"          # 奖励弹窗
    POPUP_ACHIEVEMENT = "achievement" # 成就弹窗
    POPUP_NOTICE = "notice"           # 公告弹窗
    POPUP_ERROR = "error"             # 错误弹窗
    POPUP_CONFIRM = "confirm"         # 确认弹窗

    # 设置状态
    SETTINGS_AUDIO = "settings_audio"    # 音效设置
    SETTINGS_VIDEO = "settings_video"    # 画面设置
    SETTINGS_CONTROL = "settings_control" # 操作设置

    # 商店状态
    SHOP_MAIN = "shop_main"          # 商店主页
    SHOP_ITEM_DETAIL = "shop_item"    # 商品详情
    SHOP_PURCHASE_CONFIRM = "shop_buy" # 购买确认

    # 背包状态
    INV_MAIN = "inv_main"            # 背包主页
    INV_ITEM_DETAIL = "inv_item"     # 物品详情
    INV_EQUIP = "inv_equip"          # 装备界面

    # 社交状态
    SOCIAL_FRIEND = "friend"         # 好友列表
    SOCIAL_GUILD = "guild"           # 公会界面
    SOCIAL_CHAT = "chat"             # 聊天界面

    # 地图状态
    MAP_WORLD = "world_map"          # 世界地图
    MAP_DUNGEON = "dungeon_map"      # 副本地图
    MAP_NAVI = "navigation"          # 导航中

    # 战斗状态
    BATTLE_AUTO = "battle_auto"      # 自动战斗
    BATTLE_MANUAL = "battle_manual" # 手动战斗
    BATTLE_PAUSED = "battle_paused" # 战斗暂停
    BATTLE_VICTORY = "victory"      # 胜利结算
    BATTLE_DEFEAT = "defeat"        # 失败结算

    # 新手引导状态
    TUTORIAL_STEP_1 = "tut_step1"   # 引导步骤1
    TUTORIAL_STEP_2 = "tut_step2"   # 引导步骤2
    TUTORIAL_STEP_N = "tut_stepN"    # 引导步骤N

    # 加载状态
    LOADING_GAME = "loading_game"    # 游戏加载
    LOADING_SCENE = "loading_scene"  # 场景切换加载
    LOADING_RESOURCE = "loading_res" # 资源加载

    # 过场状态
    TRANSITION_STORY = "story"        # 剧情过场
    TRANSITION_CINEMATIC = "cinema"  # 动画过场

    # 桌面状态
    DESKTOP_MAIN = "desktop_main"    # 桌面主页
    DESKTOP_APP = "desktop_app"      # 应用界面
    DESKTOP_WIDGET = "desktop_widget" # 桌面小组件


class SceneContext(Enum):
    """场景上下文 - 额外的上下文信息"""
    IN_TEAM = "in_team"              # 组队中
    IN_PVP = "in_pvp"                # PVP中
    LOW_BATTERY = "low_battery"      # 电量低
    LOW_NETWORK = "low_network"       # 网络差
    EVENT_ACTIVE = "event_active"     # 活动中
    NIGHT_MODE = "night_mode"        # 夜间模式
    VIP_ACTIVE = "vip"               # VIP状态


SCENE_LEVEL_DISPLAY = {
    SceneLevel.MAIN_MENU: "主菜单",
    SceneLevel.GAME_PLAY: "游戏中",
    SceneLevel.DIALOG: "对话框",
    SceneLevel.SETTINGS: "设置",
    SceneLevel.SHOP: "商店",
    SceneLevel.INVENTORY: "背包",
    SceneLevel.SOCIAL: "社交",
    SceneLevel.MAP: "地图",
    SceneLevel.BATTLE: "战斗",
    SceneLevel.TUTORIAL: "引导",
    SceneLevel.LOADING: "加载",
    SceneLevel.TRANSITION: "过场",
    SceneLevel.DESKTOP: "桌面",
    SceneLevel.UNKNOWN: "未知",
}

SCENE_STATE_DISPLAY = {
    # 主菜单
    SceneState.TITLE: "标题画面",
    SceneState.SERVER_SELECT: "服务器选择",
    SceneState.CHARACTER_SELECT: "角色选择",
    SceneState.HOME: "主页",
    # 游戏进行
    SceneState.EXPLORING: "探索中",
    SceneState.QUEST_ACTIVE: "任务进行",
    SceneState.QUEST_COMPLETE: "任务完成",
    # 对话框
    SceneState.DIALOG_TALKING: "对话中",
    SceneState.DIALOG_CHOICE: "选项对话",
    SceneState.DIALOG_CUTSCENE: "动画对话",
    # 弹窗
    SceneState.POPUP_REWARD: "奖励",
    SceneState.POPUP_ACHIEVEMENT: "成就",
    SceneState.POPUP_NOTICE: "公告",
    SceneState.POPUP_ERROR: "错误",
    SceneState.POPUP_CONFIRM: "确认",
    # 设置
    SceneState.SETTINGS_AUDIO: "音效设置",
    SceneState.SETTINGS_VIDEO: "画面设置",
    SceneState.SETTINGS_CONTROL: "操作设置",
    # 商店
    SceneState.SHOP_MAIN: "商店",
    SceneState.SHOP_ITEM_DETAIL: "商品详情",
    SceneState.SHOP_PURCHASE_CONFIRM: "购买确认",
    # 背包
    SceneState.INV_MAIN: "背包",
    SceneState.INV_ITEM_DETAIL: "物品详情",
    SceneState.INV_EQUIP: "装备",
    # 社交
    SceneState.SOCIAL_FRIEND: "好友",
    SceneState.SOCIAL_GUILD: "公会",
    SceneState.SOCIAL_CHAT: "聊天",
    # 地图
    SceneState.MAP_WORLD: "世界地图",
    SceneState.MAP_DUNGEON: "副本地图",
    SceneState.MAP_NAVI: "导航中",
    # 战斗
    SceneState.BATTLE_AUTO: "自动战斗",
    SceneState.BATTLE_MANUAL: "手动战斗",
    SceneState.BATTLE_PAUSED: "战斗暂停",
    SceneState.BATTLE_VICTORY: "胜利",
    SceneState.BATTLE_DEFEAT: "失败",
    # 引导
    SceneState.TUTORIAL_STEP_1: "引导1",
    SceneState.TUTORIAL_STEP_2: "引导2",
    SceneState.TUTORIAL_STEP_N: "引导N",
    # 加载
    SceneState.LOADING_GAME: "游戏加载",
    SceneState.LOADING_SCENE: "场景加载",
    SceneState.LOADING_RESOURCE: "资源加载",
    # 过场
    SceneState.TRANSITION_STORY: "剧情",
    SceneState.TRANSITION_CINEMATIC: "动画",
    # 桌面
    SceneState.DESKTOP_MAIN: "桌面主页",
    SceneState.DESKTOP_APP: "应用界面",
    SceneState.DESKTOP_WIDGET: "小组件",
}

SCENE_CONTEXT_DISPLAY = {
    SceneContext.IN_TEAM: "组队中",
    SceneContext.IN_PVP: "PVP",
    SceneContext.LOW_BATTERY: "低电量",
    SceneContext.LOW_NETWORK: "网络差",
    SceneContext.EVENT_ACTIVE: "活动中",
    SceneContext.NIGHT_MODE: "夜间",
    SceneContext.VIP_ACTIVE: "VIP",
}


def get_scene_full_name(level: SceneLevel, state: Optional[SceneState] = None, contexts: Optional[list] = None) -> str:
    """获取场景完整名称"""
    level_name = SCENE_LEVEL_DISPLAY.get(level, level.value)
    if state:
        state_name = SCENE_STATE_DISPLAY.get(state, state.value)
        result = f"{level_name}-{state_name}"
    else:
        result = level_name

    if contexts:
        ctx_names = [SCENE_CONTEXT_DISPLAY.get(c, c.value) for c in contexts if c]
        if ctx_names:
            result += f" [{','.join(ctx_names)}]"

    return result


def parse_scene_type(scene_type: str) -> tuple[Optional[SceneLevel], Optional[SceneState], list]:
    """解析场景类型字符串，返回 (level, state, contexts)"""
    if not scene_type:
        return None, None, []

    contexts = []
    level = None
    state = None

    parts = scene_type.replace("]", "").split("[")
    main_part = parts[0]
    if len(parts) > 1:
        ctx_str = parts[1]
        for ctx_name in ctx_str.split(","):
            ctx_name = ctx_name.strip()
            for ctx in SceneContext:
                if ctx_name == ctx.value or ctx_name == SCENE_CONTEXT_DISPLAY.get(ctx, ""):
                    contexts.append(ctx)
                    break

    for lv in SceneLevel:
        if lv.value == main_part or SCENE_LEVEL_DISPLAY.get(lv, "") == main_part:
            level = lv
            break

    for st in SceneState:
        if st.value == main_part or SCENE_STATE_DISPLAY.get(st, "") == main_part:
            state = st
            break

    return level, state, contexts
