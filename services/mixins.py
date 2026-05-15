from services.device_connection import DeviceConnectionMixin
from services.frame_capture import FrameCaptureMixin
from services.getevent_listener import GeteventListenerMixin
from services.maintenance_service import MaintenanceServiceMixin
from services.physical_touch_input import PhysicalTouchInputMixin
from services.projected_touch_input import ProjectedTouchInputMixin
from services.recording_event_service import RecordingEventMixin
from services.scrcpy_control import ScrcpyControlMixin
from services.touch_mapping import TouchMappingMixin


class ServicesMixin(
    DeviceConnectionMixin,
    FrameCaptureMixin,
    TouchMappingMixin,
    GeteventListenerMixin,
    ScrcpyControlMixin,
    PhysicalTouchInputMixin,
    ProjectedTouchInputMixin,
    RecordingEventMixin,
    MaintenanceServiceMixin,
):
    pass
