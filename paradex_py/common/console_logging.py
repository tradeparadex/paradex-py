import logging
import os

logging.basicConfig(
    level=os.getenv("LOGGING_LEVEL", "INFO"),
    format="%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

console_logger = logging.getLogger(__name__)
