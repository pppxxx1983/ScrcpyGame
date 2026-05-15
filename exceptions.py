"""
Custom exceptions for ScrcpyGame application.
"""


class ScrcpyGameError(Exception):
    """Base exception for all ScrcpyGame errors."""
    pass


class DeviceConnectionError(ScrcpyGameError):
    """Raised when device connection fails."""
    pass


class DeviceNotFoundError(DeviceConnectionError):
    """Raised when the specified device is not found."""
    pass


class ApiKeyError(ScrcpyGameError):
    """Raised when API key is missing or invalid."""
    pass


class LlmApiError(ScrcpyGameError):
    """Raised when LLM API call fails."""

    def __init__(self, message: str, model: str = "", status_code: int = 0):
        super().__init__(message)
        self.model = model
        self.status_code = status_code


class RecordingError(ScrcpyGameError):
    """Raised when video recording fails."""
    pass


class EventStoreError(ScrcpyGameError):
    """Raised when event storage operation fails."""
    pass


class SceneIndexError(ScrcpyGameError):
    """Raised when scene indexing operation fails."""
    pass


class YoloModelError(ScrcpyGameError):
    """Raised when YOLO model operation fails."""
    pass


class ConfigurationError(ScrcpyGameError):
    """Raised when configuration is invalid or missing."""
    pass


class CoordinateMappingError(ScrcpyGameError):
    """Raised when coordinate mapping fails."""
    pass
