"""
Unit tests for coordinate_mapper module.
"""
import pytest
from domain.coordinate_mapper import (
    oriented_screen_size,
    frame_to_device,
    device_to_frame,
    parse_abs_range,
    raw_touch_to_device,
)


class TestCoordinateMapper:
    """Test cases for coordinate mapping functions."""

    def test_oriented_screen_size_landscape(self):
        """Test landscape orientation detection."""
        result = oriented_screen_size(1920, 1080, (1920, 1080))
        assert result == (1920, 1080, "landscape")

    def test_oriented_screen_size_portrait(self):
        """Test portrait orientation detection."""
        result = oriented_screen_size(1080, 1920, (1080, 1920))
        assert result == (1080, 1920, "portrait")

    def test_oriented_screen_size_rotated_device(self):
        """Test with rotated device resolution.

        When frame is portrait (1080x1920) but device is landscape (1920x1080),
        the function determines orientation based on frame aspect ratio.
        """
        result = oriented_screen_size(1080, 1920, (1920, 1080))
        assert result[2] == "portrait"

    def test_frame_to_device_basic(self):
        """Test basic frame to device coordinate conversion."""
        frame_shape = (1080, 1920)
        device_resolution = (1080, 1920)

        result = frame_to_device(960, 540, frame_shape, device_resolution)

        assert len(result) == 3
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)
        assert result[2] in ("portrait", "landscape")

    def test_frame_to_device_boundary(self):
        """Test boundary value handling."""
        frame_shape = (1080, 1920)
        device_resolution = (1080, 1920)

        x, y, _ = frame_to_device(0, 0, frame_shape, device_resolution)
        assert x == 0
        assert y == 0

        x, y, _ = frame_to_device(1920, 1080, frame_shape, device_resolution)
        assert x == 1919
        assert y == 1079

    def test_frame_to_device_exceed_boundary(self):
        """Test coordinates exceeding boundaries are clamped."""
        frame_shape = (100, 100)
        device_resolution = (100, 100)

        x, y, _ = frame_to_device(150, 150, frame_shape, device_resolution)
        assert x == 99
        assert y == 99

    def test_device_to_frame_basic(self):
        """Test basic device to frame coordinate conversion."""
        frame_shape = (1080, 1920)
        device_resolution = (1080, 1920)

        x, y = device_to_frame(540, 540, frame_shape, device_resolution)

        assert x == 540
        assert y == 540

    def test_device_to_frame_round_trip(self):
        """Test round-trip conversion maintains values in valid range."""
        frame_shape = (1080, 1920)
        device_resolution = (1080, 1920)
        original_x, original_y = 500, 600

        device_result = frame_to_device(original_x, original_y, frame_shape, device_resolution)
        device_x, device_y = device_result[0], device_result[1]
        result_x, result_y = device_to_frame(device_x, device_y, frame_shape, device_resolution)

        assert 0 <= result_x < 1920
        assert 0 <= result_y < 1080

    def test_parse_abs_range_valid(self):
        """Test parsing valid abs_range lines."""
        result = parse_abs_range("abs x [min 100 max 500]")
        assert result == (100, 500)

    def test_parse_abs_range_no_match(self):
        """Test parsing invalid lines."""
        assert parse_abs_range("random text") is None
        assert parse_abs_range("abs x") is None

    def test_raw_touch_to_device_basic(self):
        """Test raw touch to device conversion."""
        touch_info = (None, 1000, 2000, 500, 1500)
        device_resolution = (1080, 1920)

        x, y = raw_touch_to_device(1500, 1000, touch_info, device_resolution, False)

        assert x >= 0
        assert y >= 0

    def test_raw_touch_to_device_landscape(self):
        """Test raw touch in landscape mode."""
        touch_info = (None, 1000, 2000, 500, 1500)
        device_resolution = (1920, 1080)

        x, y = raw_touch_to_device(1500, 1000, touch_info, device_resolution, True)

        assert x >= 0 and x < 1920
        assert y >= 0 and y < 1080

    def test_raw_touch_to_device_none_inputs(self):
        """Test handling of None inputs."""
        result = raw_touch_to_device(None, 100, {}, (1920, 1080), False)
        assert result == (None, None)

    def test_raw_touch_to_device_normalized(self):
        """Test normalized coordinate range is [0, 1]."""
        touch_info = (None, 0, 100, 0, 100)
        device_resolution = (1920, 1080)

        x, y = raw_touch_to_device(50, 50, touch_info, device_resolution, False)

        assert 0 <= x <= 1919
        assert 0 <= y <= 1079
