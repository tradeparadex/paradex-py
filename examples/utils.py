"""Shared utilities for Paradex example scripts."""

import logging
import os
import sys
from datetime import datetime


def get_logger(name: str = __name__) -> logging.Logger:
    """Configure and return a logger.

    Env vars:
        LOG_FILE=true    write to a timestamped file in logs/ instead of stdout
        LOGGING_LEVEL    override log level (default: INFO)
    """
    level = os.getenv("LOGGING_LEVEL", "INFO")
    fmt = "%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    if os.getenv("LOG_FILE", "").lower() == "true":
        ts = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        fn = os.path.basename(sys.argv[0]).rsplit(".", 1)[0]
        os.makedirs("logs", exist_ok=True)
        logging.basicConfig(filename=f"logs/{fn}_{ts}.log", level=level, format=fmt, datefmt=datefmt)
    else:
        logging.basicConfig(level=level, format=fmt, datefmt=datefmt)

    return logging.getLogger(name)
