"""
Unit tests for log_manager module.
"""
import pytest
import threading
import time
from log_manager import LogManager


class TestLogManager:
    """Test cases for LogManager singleton."""

    def setup_method(self):
        """Reset singleton before each test."""
        LogManager.reset_instance()

    def test_singleton_instance(self):
        """Test that LogManager returns same instance."""
        manager1 = LogManager()
        manager2 = LogManager()
        assert manager1 is manager2

    def test_append_single_message(self):
        """Test appending a single message."""
        manager = LogManager()
        manager.append("test message")
        logs = manager.get_and_clear()
        assert len(logs) == 1
        assert logs[0] == "test message"

    def test_append_multiple_messages(self):
        """Test appending multiple messages."""
        manager = LogManager()
        manager.append("msg1")
        manager.append("msg2")
        manager.append("msg3")
        logs = manager.get_and_clear()
        assert len(logs) == 3
        assert logs == ["msg1", "msg2", "msg3"]

    def test_get_and_clear(self):
        """Test that get_and_clear returns and clears messages."""
        manager = LogManager()
        manager.append("msg1")
        logs1 = manager.get_and_clear()
        logs2 = manager.get_and_clear()
        assert len(logs1) == 1
        assert len(logs2) == 0

    def test_clear(self):
        """Test clear method."""
        manager = LogManager()
        manager.append("msg1")
        manager.append("msg2")
        manager.clear()
        logs = manager.get_and_clear()
        assert len(logs) == 0

    def test_thread_safety(self):
        """Test thread-safe operations."""
        manager = LogManager()
        manager.clear()
        errors = []

        def append_worker():
            try:
                for i in range(100):
                    manager.append(f"worker_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=append_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        logs = manager.get_and_clear()
        assert len(logs) == 500
