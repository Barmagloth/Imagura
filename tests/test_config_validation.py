"""Tests for config validation from imagura2.py."""

from __future__ import annotations
import pytest


def validate_settings_value(value_str: str, val_type: type, min_val, max_val) -> tuple:
    """Validate a settings value. Returns (is_valid, parsed_value, error_msg).

    This is extracted from imagura2.py to avoid importing the full module
    which requires raylib dependencies.
    """
    if not value_str.strip():
        return False, None, "Empty value"

    try:
        if val_type == int:
            val = int(value_str)
        elif val_type == float:
            val = float(value_str)
        else:
            return False, None, "Unknown type"

        if min_val is not None and val < min_val:
            return False, None, f"Min: {min_val}"
        if max_val is not None and val > max_val:
            return False, None, f"Max: {max_val}"

        return True, val, None

    except ValueError:
        return False, None, "Invalid number"


class TestValidateSettingsValue:
    """Test validate_settings_value function."""

    def test_valid_int(self):
        """Test validating a valid integer within bounds."""
        is_valid, val, error = validate_settings_value("120", int, 30, 240)
        assert is_valid is True
        assert val == 120
        assert error is None

    def test_valid_float(self):
        """Test validating a valid float within bounds."""
        is_valid, val, error = validate_settings_value("0.95", float, 0.5, 1.0)
        assert is_valid is True
        assert val == 0.95
        assert error is None

    def test_empty_value(self):
        """Test empty value returns error."""
        is_valid, val, error = validate_settings_value("", int, 30, 240)
        assert is_valid is False
        assert val is None
        assert error == "Empty value"

    def test_whitespace_only(self):
        """Test whitespace-only value is treated as empty."""
        is_valid, val, error = validate_settings_value("   ", int, 30, 240)
        assert is_valid is False
        assert val is None
        assert error == "Empty value"

    def test_below_min(self):
        """Test value below minimum returns error."""
        is_valid, val, error = validate_settings_value("10", int, 30, 240)
        assert is_valid is False
        assert val is None
        assert error == "Min: 30"

    def test_above_max(self):
        """Test value above maximum returns error."""
        is_valid, val, error = validate_settings_value("300", int, 30, 240)
        assert is_valid is False
        assert val is None
        assert error == "Max: 240"

    def test_invalid_number(self):
        """Test invalid number string returns error."""
        is_valid, val, error = validate_settings_value("abc", int, 30, 240)
        assert is_valid is False
        assert val is None
        assert error == "Invalid number"

    def test_valid_int_no_bounds(self):
        """Test valid int with no min/max bounds."""
        is_valid, val, error = validate_settings_value("999", int, None, None)
        assert is_valid is True
        assert val == 999
        assert error is None

    def test_valid_float_with_min_only(self):
        """Test float with only min bound."""
        is_valid, val, error = validate_settings_value("0.6", float, 0.5, None)
        assert is_valid is True
        assert val == 0.6
        assert error is None

    def test_valid_float_with_max_only(self):
        """Test float with only max bound."""
        is_valid, val, error = validate_settings_value("0.4", float, None, 0.5)
        assert is_valid is True
        assert val == 0.4
        assert error is None

    def test_float_at_min_boundary(self):
        """Test float at exact minimum boundary."""
        is_valid, val, error = validate_settings_value("0.5", float, 0.5, 1.0)
        assert is_valid is True
        assert val == 0.5
        assert error is None

    def test_float_at_max_boundary(self):
        """Test float at exact maximum boundary."""
        is_valid, val, error = validate_settings_value("1.0", float, 0.5, 1.0)
        assert is_valid is True
        assert val == 1.0
        assert error is None

    def test_negative_int(self):
        """Test negative integer."""
        is_valid, val, error = validate_settings_value("-50", int, -100, 100)
        assert is_valid is True
        assert val == -50
        assert error is None

    def test_negative_float(self):
        """Test negative float."""
        is_valid, val, error = validate_settings_value("-1.5", float, -2.0, 0.0)
        assert is_valid is True
        assert val == -1.5
        assert error is None

    def test_zero_int(self):
        """Test zero as integer value."""
        is_valid, val, error = validate_settings_value("0", int, -10, 10)
        assert is_valid is True
        assert val == 0
        assert error is None

    def test_zero_float(self):
        """Test zero as float value."""
        is_valid, val, error = validate_settings_value("0.0", float, -1.0, 1.0)
        assert is_valid is True
        assert val == 0.0
        assert error is None
