"""Agent data manager facade and active game data path."""

from pathlib import Path
from typing import Optional

from data.agent_schema import hash_confidence, init_agent_db, init_game_dirs
from log_manager import LogManager
from repositories.session_repo import SessionRepository
from repositories.event_repo import EventRepository
from repositories.ui_element_repo import UiElementRepository
from repositories.runtime_rule_repo import RuntimeRuleRepository
from repositories.stats_repo import StatsRepository


GAME_DATA_DIR = Path("game_agent_data") / "games" / "my_game"


def set_game_data_dir(game_name: str) -> Path:
    """Switch active game data directory and reset the singleton manager."""
    global GAME_DATA_DIR
    GAME_DATA_DIR = Path("game_agent_data") / "games" / game_name
    AgentDataManager._instance = None
    LogManager().append(f"[GameSwitch] switched to {GAME_DATA_DIR}")
    return GAME_DATA_DIR


class AgentDataManager(
    SessionRepository,
    EventRepository,
    UiElementRepository,
    RuntimeRuleRepository,
    StatsRepository,
):
    """Singleton facade that wires repositories to the active game database."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.game_dir = GAME_DATA_DIR
        init_game_dirs(self.game_dir)
        self.db_path = self.game_dir / "agent.db"
        init_agent_db(self.db_path)
        self.current_session_id: Optional[str] = None
        self.current_session_dir: Optional[Path] = None
        self.current_session_events_path: Optional[Path] = None
        self.current_session_meta_path: Optional[Path] = None
        self.click_counter = 0

    def switch_game(self, game_name: str):
        global GAME_DATA_DIR
        GAME_DATA_DIR = Path("game_agent_data") / "games" / game_name
        self.game_dir = GAME_DATA_DIR
        init_game_dirs(self.game_dir)
        self.db_path = self.game_dir / "agent.db"
        init_agent_db(self.db_path)
        LogManager().append(f"[AgentData] switched game to {game_name}")

    @staticmethod
    def _hash_confidence(left: str, right: str) -> float:
        return hash_confidence(left, right)
