from PySide6.QtCore import QObject, Signal

class SignalBridge(QObject):
    status_changed = Signal(str, str)
    buttons_changed = Signal(bool)
    decision_ready = Signal(dict)
    touch_feedback = Signal(object, int)
    overlay_changed = Signal(object)
    events_changed = Signal()
    yolo_reanalyze_ready = Signal(object)

