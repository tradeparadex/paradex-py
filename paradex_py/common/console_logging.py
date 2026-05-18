import logging
import os
import warnings

warnings.warn(
    "paradex_py.common.console_logging is deprecated and will be removed in a future version. "
    "Use the standard logging module directly.",
    DeprecationWarning,
    stacklevel=2,
)

logging.basicConfig(
    level=os.getenv("LOGGING_LEVEL", "INFO"),
    format="%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

console_logger = logging.getLogger(__name__)
