from ui.panels.audit_actions_panel import AuditActionsPanelMixin
from ui.panels.audit_refresh_panel import AuditRefreshPanelMixin
from ui.panels.audit_setup_panel import AuditSetupPanelMixin
from ui.panels.event_detail_panel import EventDetailPanelMixin
from ui.panels.event_list_panel import EventListPanelMixin
from ui.panels.event_video_panel import EventVideoPanelMixin
from ui.panels.execution_panel import ExecutionPanelMixin
from ui.panels.reanalyze_history_panel import ReanalyzeHistoryPanelMixin
from ui.panels.rules_actions_panel import RulesActionsPanelMixin
from ui.panels.rules_refresh_panel import RulesRefreshPanelMixin
from ui.panels.rules_setup_panel import RulesSetupPanelMixin
from ui.panels.scene_audit_panel import SceneAuditPanelMixin
from ui.panels.status_panel import StatusPanelMixin
from ui.panels.tab_manager_panel import TabManagerPanelMixin
from ui.panels.video_replay_panel import VideoReplayPanelMixin
from ui.panels.yolo_audit_panel import YoloAuditPanelMixin


class PanelsMixin(
    EventListPanelMixin,
    EventDetailPanelMixin,
    EventVideoPanelMixin,
    TabManagerPanelMixin,
    VideoReplayPanelMixin,
    ExecutionPanelMixin,
    RulesSetupPanelMixin,
    RulesRefreshPanelMixin,
    RulesActionsPanelMixin,
    AuditSetupPanelMixin,
    AuditRefreshPanelMixin,
    AuditActionsPanelMixin,
    SceneAuditPanelMixin,
    YoloAuditPanelMixin,
    ReanalyzeHistoryPanelMixin,
    StatusPanelMixin,
):
    pass
