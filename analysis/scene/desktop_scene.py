"""
桌面场景类
"""
from __future__ import annotations

from analysis.scene_classes import BaseScene, SceneLevel, SceneState


class DesktopScene(BaseScene):
    """桌面场景"""

    LEVEL = SceneLevel.DESKTOP
    DISPLAY_NAME = "桌面"

    def classify_state(self) -> SceneState:
        hash_patterns = {
            "desktop_main": ["a0a0a0a0", "b0b0b0b0"],
            "desktop_app": ["c0c0c0c0", "d0d0d0d0"],
            "desktop_widget": ["e0e0e0e0", "f0f0f0f0"],
        }
        for state, patterns in hash_patterns.items():
            for pattern in patterns:
                if pattern in self.dhash.lower():
                    return SceneState(f"DESKTOP_{state.upper()}")
        return SceneState.DESKTOP_MAIN

    def is_valid(self) -> bool:
        return bool(self.dhash)


def _register():
    """延迟注册到 SceneFactory，避免循环导入。"""
    from analysis.scene_classes import SceneFactory, SceneLevel
    SceneFactory._level_map[SceneLevel.DESKTOP] = DesktopScene


_register()
