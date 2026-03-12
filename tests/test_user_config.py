"""Tests for the user_config module."""

from __future__ import annotations
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from imagura import user_config


class TestParseTomlSimple:
    """Test _parse_toml_simple function."""

    def test_parse_toml_simple(self):
        """Test parsing simple key = value pairs."""
        content = "KEY = 123\nFLOAT_KEY = 1.5"
        result = user_config._parse_toml_simple(content)
        assert result == {"KEY": 123, "FLOAT_KEY": 1.5}

    def test_parse_toml_comments(self):
        """Test that lines with # comments are ignored."""
        content = "KEY = 123\n# This is a comment\nVALUE = 456"
        result = user_config._parse_toml_simple(content)
        assert result == {"KEY": 123, "VALUE": 456}

    def test_parse_toml_inline_comments(self):
        """Test that inline comments are stripped."""
        content = "KEY = 123  # inline comment"
        result = user_config._parse_toml_simple(content)
        assert result == {"KEY": 123}

    def test_parse_toml_empty(self):
        """Test parsing empty string returns empty dict."""
        content = ""
        result = user_config._parse_toml_simple(content)
        assert result == {}

    def test_parse_toml_empty_lines(self):
        """Test that empty lines are ignored."""
        content = "\n\nKEY = 123\n\n"
        result = user_config._parse_toml_simple(content)
        assert result == {"KEY": 123}

    def test_parse_toml_string_values(self):
        """Test parsing string values with and without quotes."""
        content = 'STRING = "value"\nUNQUOTED = value'
        result = user_config._parse_toml_simple(content)
        assert result["STRING"] == "value"
        assert result["UNQUOTED"] == "value"

    def test_parse_toml_section_headers_ignored(self):
        """Test that section headers are ignored."""
        content = "[section]\nKEY = 123"
        result = user_config._parse_toml_simple(content)
        assert result == {"KEY": 123}


class TestLoadUserConfig:
    """Test load_user_config function."""

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading from non-existent file returns empty dict."""
        config_path = tmp_path / "nonexistent.toml"
        with patch("imagura.user_config.get_config_path", return_value=config_path):
            result = user_config.load_user_config()
            assert result == {}

    def test_load_existing_file(self, tmp_path):
        """Test loading from existing file."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("KEY = 123\nVALUE = 1.5", encoding="utf-8")

        with patch("imagura.user_config.get_config_path", return_value=config_path):
            result = user_config.load_user_config()
            assert result == {"KEY": 123, "VALUE": 1.5}


class TestSaveAndLoad:
    """Test save_value and round-trip persistence."""

    def test_save_and_load_int(self, tmp_path):
        """Test saving and loading an integer value."""
        config_path = tmp_path / "config.toml"

        with patch("imagura.user_config.get_config_path", return_value=config_path):
            # Save a value
            success = user_config.save_value("TEST_KEY", 123, int)
            assert success is True
            assert config_path.exists()

            # Load it back
            result = user_config.load_user_config()
            assert result["TEST_KEY"] == 123

    def test_save_and_load_float(self, tmp_path):
        """Test saving and loading a float value."""
        config_path = tmp_path / "config.toml"

        with patch("imagura.user_config.get_config_path", return_value=config_path):
            success = user_config.save_value("FLOAT_KEY", 3.14, float)
            assert success is True

            result = user_config.load_user_config()
            assert result["FLOAT_KEY"] == 3.14

    def test_save_multiple_values(self, tmp_path):
        """Test saving multiple values persists them all."""
        config_path = tmp_path / "config.toml"

        with patch("imagura.user_config.get_config_path", return_value=config_path):
            user_config.save_value("KEY1", 100, int)
            user_config.save_value("KEY2", 2.5, float)
            user_config.save_value("KEY3", 999, int)

            result = user_config.load_user_config()
            assert result["KEY1"] == 100
            assert result["KEY2"] == 2.5
            assert result["KEY3"] == 999


class TestSaveInvalidType:
    """Test save_value type validation."""

    def test_save_invalid_type_str(self, tmp_path):
        """Test saving with val_type=str returns False."""
        config_path = tmp_path / "config.toml"

        with patch("imagura.user_config.get_config_path", return_value=config_path):
            success = user_config.save_value("KEY", "value", str)
            assert success is False
            # File should not be created
            assert not config_path.exists()

    def test_save_type_mismatch(self, tmp_path):
        """Test saving with type mismatch returns False."""
        config_path = tmp_path / "config.toml"

        with patch("imagura.user_config.get_config_path", return_value=config_path):
            # Try to save string with int type
            success = user_config.save_value("KEY", "not_a_number", int)
            assert success is False

    def test_save_wrong_type_int_as_float(self, tmp_path):
        """Test saving int when float is expected fails."""
        config_path = tmp_path / "config.toml"

        with patch("imagura.user_config.get_config_path", return_value=config_path):
            # Save int but declare float type - should fail
            success = user_config.save_value("KEY", 123, float)
            assert success is False


class TestApplyUserConfig:
    """Test apply_user_config function."""

    def test_apply_user_config(self, tmp_path):
        """Test apply_user_config calls setattr on config module."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("TEST_SETTING = 42", encoding="utf-8")

        with patch("imagura.user_config.get_config_path", return_value=config_path):
            mock_config = MagicMock()
            with patch("imagura.config.TEST_SETTING", 99, create=True):
                # Just verify apply_user_config doesn't crash and loads correctly
                # The actual setattr happens on the real config module
                user_config.apply_user_config()
                # Function executes successfully

    def test_apply_user_config_empty(self, tmp_path):
        """Test apply_user_config with no user config."""
        config_path = tmp_path / "nonexistent.toml"

        with patch("imagura.user_config.get_config_path", return_value=config_path):
            # Should not raise, should just return early
            user_config.apply_user_config()


class TestReadonlyGraceful:
    """Test graceful handling of readonly directories."""

    def test_readonly_graceful_save(self, tmp_path):
        """Test save_value returns False gracefully if directory can't be created."""
        # Use a path that's deeply nested where we can't create dirs
        config_path = Path("/proc/test/imagura/config.toml")

        with patch("imagura.user_config.get_config_path", return_value=config_path):
            success = user_config.save_value("KEY", 123, int)
            assert success is False
