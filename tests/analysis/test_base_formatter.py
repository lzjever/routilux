"""
Tests for BaseFormatter base class.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from routilux.analysis.exporters.base import BaseFormatter


class DummyFormatter(BaseFormatter):
    """Dummy concrete formatter for testing BaseFormatter."""

    def format(self, data):
        """Return formatted string for testing."""
        return f"Formatted: {data}"


class TestBaseFormatter:
    """Tests for BaseFormatter base class."""

    def test_format_is_abstract(self):
        """Test that BaseFormatter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseFormatter()

    def test_save_creates_parent_directories(self, tmp_path):
        """Test that save creates parent directories if they don't exist."""
        formatter = DummyFormatter()
        data = {"key": "value"}
        output_path = tmp_path / "deep" / "nested" / "output.txt"

        formatter.save(data, output_path)

        assert output_path.exists()
        assert output_path.parent.is_dir()

    def test_save_writes_formatted_content(self, tmp_path):
        """Test that save writes the formatted content to file."""
        formatter = DummyFormatter()
        data = {"test": "content"}
        output_path = tmp_path / "output.txt"

        formatter.save(data, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert content == "Formatted: {'test': 'content'}"

    def test_save_with_pathlib_path(self, tmp_path):
        """Test save with Path object."""
        formatter = DummyFormatter()
        data = {"key": "value"}
        output_path = tmp_path / "path_output.txt"

        formatter.save(data, output_path)

        assert output_path.exists()

    def test_save_with_string_path(self, tmp_path):
        """Test save with string path."""
        formatter = DummyFormatter()
        data = {"key": "value"}
        output_path = str(tmp_path / "string_output.txt")

        formatter.save(data, output_path)

        assert Path(output_path).exists()

    def test_save_overwrites_existing_file(self, tmp_path):
        """Test that save overwrites existing file."""
        formatter = DummyFormatter()
        output_path = tmp_path / "overwrite.txt"

        # Create initial file
        output_path.write_text("old content", encoding="utf-8")

        # Save new content
        formatter.save({"new": "data"}, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "new" in content
        assert "old" not in content

    def test_save_with_unicode_content(self, tmp_path):
        """Test save with unicode content."""
        formatter = DummyFormatter()
        data = {"message": "Hello 世界 🌍"}
        output_path = tmp_path / "unicode.txt"

        formatter.save(data, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "世界" in content
        assert "🌍" in content

    def test_save_with_empty_data(self, tmp_path):
        """Test save with empty data."""
        formatter = DummyFormatter()
        data = {}
        output_path = tmp_path / "empty.txt"

        formatter.save(data, output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "Formatted: {}" in content
