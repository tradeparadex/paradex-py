"""Tests for user_agent module."""

import platform
import sys
from unittest.mock import patch

from paradex_py.user_agent import get_user_agent


class TestUserAgent:
    """Test suite for user agent generation."""

    def test_user_agent_format(self):
        """Test that user agent follows expected format."""
        user_agent = get_user_agent()

        # Should contain all required components
        assert "paradex-py/" in user_agent
        assert "Python" in user_agent
        assert platform.system() in user_agent

    def test_user_agent_includes_sdk_version(self):
        """Test that user agent includes SDK version."""
        user_agent = get_user_agent()

        # Should have version after paradex-py/
        assert user_agent.startswith("paradex-py/")
        version_part = user_agent.split("paradex-py/")[1].split(" ")[0]
        # Version should be either semver format or "dev"
        assert version_part == "dev" or "." in version_part

    def test_user_agent_includes_python_version(self):
        """Test that user agent includes Python version."""
        user_agent = get_user_agent()

        expected_python = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        assert expected_python in user_agent

    def test_user_agent_includes_platform(self):
        """Test that user agent includes platform."""
        user_agent = get_user_agent()

        platform_name = platform.system()
        assert platform_name in user_agent

    def test_user_agent_fallback_dev_version(self):
        """Test that user agent falls back to 'dev' when package not installed."""
        from importlib.metadata import PackageNotFoundError

        with patch("paradex_py.user_agent.version", side_effect=PackageNotFoundError("Package not found")):
            user_agent = get_user_agent()

            # Should fallback to "dev"
            assert "paradex-py/dev" in user_agent

    def test_user_agent_structure(self):
        """Test that user agent has correct structure."""
        user_agent = get_user_agent()

        # Expected format: "paradex-py/{VERSION} (Python {PYTHON_VERSION}; {PLATFORM})"
        parts = user_agent.split(" ", 1)
        assert len(parts) == 2
        assert parts[0].startswith("paradex-py/")
        assert parts[1].startswith("(")
        assert parts[1].endswith(")")

        # Check inner part
        inner = parts[1][1:-1]  # Remove parentheses
        inner_parts = inner.split("; ")
        assert len(inner_parts) == 2
        assert inner_parts[0].startswith("Python ")
        # inner_parts[1] is the platform

    def test_user_agent_consistent(self):
        """Test that user agent returns consistent value across multiple calls."""
        user_agent1 = get_user_agent()
        user_agent2 = get_user_agent()

        assert user_agent1 == user_agent2
