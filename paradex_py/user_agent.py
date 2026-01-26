"""User agent utility for HTTP and WebSocket clients."""

import platform
import sys
from importlib.metadata import PackageNotFoundError, version


def get_user_agent() -> str:
    """Generate a formatted User-Agent header for paradex-py SDK.

    Format: paradex-py/{VERSION} (Python {PYTHON_VERSION}; {PLATFORM})

    Returns:
        str: Formatted user agent string

    Examples:
        >>> agent = get_user_agent()
        >>> print(agent)
        paradex-py/0.5.4 (Python 3.11.14; Darwin)
    """
    # Get SDK version
    try:
        sdk_version = version("paradex_py")
    except PackageNotFoundError:
        # Fallback for development mode when package not installed
        sdk_version = "dev"

    # Get Python version (e.g., "3.11.14")
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # Get platform name (e.g., "Darwin", "Linux", "Windows")
    platform_name = platform.system()

    return f"paradex-py/{sdk_version} (Python {python_version}; {platform_name})"
