"""
Unit tests for scene_classifier module.
"""
import pytest
from analysis.scene_classifier import (
    SceneLevel,
    SceneState,
    SceneContext,
    get_scene_full_name,
    parse_scene_type,
    SCENE_LEVEL_DISPLAY,
    SCENE_STATE_DISPLAY,
    SCENE_CONTEXT_DISPLAY,
)


class TestSceneClassifier:
    """Test cases for scene classification system."""

    def test_scene_level_enum_values(self):
        """Test SceneLevel enum has expected values."""
        assert SceneLevel.MAIN_MENU.value == "main_menu"
        assert SceneLevel.GAME_PLAY.value == "game_play"
        assert SceneLevel.BATTLE.value == "battle"
        assert SceneLevel.UNKNOWN.value == "unknown"

    def test_scene_state_enum_values(self):
        """Test SceneState enum has expected values."""
        assert SceneState.TITLE.value == "title"
        assert SceneState.EXPLORING.value == "exploring"
        assert SceneState.BATTLE_AUTO.value == "battle_auto"
        assert SceneState.DIALOG_TALKING.value == "talking"

    def test_scene_context_enum_values(self):
        """Test SceneContext enum has expected values."""
        assert SceneContext.IN_TEAM.value == "in_team"
        assert SceneContext.IN_PVP.value == "in_pvp"
        assert SceneContext.VIP_ACTIVE.value == "vip"

    def test_get_scene_full_name_level_only(self):
        """Test getting full name with level only."""
        name = get_scene_full_name(SceneLevel.BATTLE)
        assert "战斗" in name or "battle" in name.lower()

    def test_get_scene_full_name_with_state(self):
        """Test getting full name with level and state."""
        name = get_scene_full_name(SceneLevel.BATTLE, SceneState.BATTLE_AUTO)
        assert "战斗" in name or "battle" in name.lower()
        assert "自动" in name or "auto" in name.lower()

    def test_get_scene_full_name_with_context(self):
        """Test getting full name with context."""
        name = get_scene_full_name(
            SceneLevel.BATTLE,
            SceneState.BATTLE_AUTO,
            [SceneContext.IN_TEAM]
        )
        assert "组队" in name or "in_team" in name.lower()

    def test_parse_scene_type_empty(self):
        """Test parsing empty scene type."""
        level, state, contexts = parse_scene_type("")
        assert level is None
        assert state is None
        assert contexts == []

    def test_parse_scene_type_level(self):
        """Test parsing level only."""
        level, state, contexts = parse_scene_type("main_menu")
        assert level == SceneLevel.MAIN_MENU
        assert state is None

    def test_parse_scene_type_display_name(self):
        """Test parsing display name."""
        level, state, contexts = parse_scene_type("主菜单")
        assert level == SceneLevel.MAIN_MENU

    def test_scene_level_display_mapping(self):
        """Test all scene levels have display names."""
        for level in SceneLevel:
            assert level in SCENE_LEVEL_DISPLAY
            assert len(SCENE_LEVEL_DISPLAY[level]) > 0

    def test_scene_state_display_mapping(self):
        """Test all scene states have display names."""
        for state in SceneState:
            assert state in SCENE_STATE_DISPLAY
            assert len(SCENE_STATE_DISPLAY[state]) > 0

    def test_scene_context_display_mapping(self):
        """Test all scene contexts have display names."""
        for ctx in SceneContext:
            assert ctx in SCENE_CONTEXT_DISPLAY
            assert len(SCENE_CONTEXT_DISPLAY[ctx]) > 0

    def test_level_coverage(self):
        """Test that key game scenes are covered."""
        expected_values = [
            "main_menu", "game_play", "dialog", "settings",
            "shop", "inventory", "battle", "loading",
        ]
        for val in expected_values:
            assert val in SceneLevel._value2member_map_

    def test_battle_states_coverage(self):
        """Test battle-related states are covered."""
        battle_values = [
            "battle_auto", "battle_manual", "battle_paused",
            "victory", "defeat",
        ]
        for val in battle_values:
            assert val in SceneState._value2member_map_
