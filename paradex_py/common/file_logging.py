import logging
import os
import sys
from datetime import datetime

LOG_TIMESTAMP = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
fn = sys.argv[0].split("/")[-1]
fn_base = fn.split(".")[0]
logging.basicConfig(
    filename=f"logs/{fn_base}_{LOG_TIMESTAMP}.log",
    level=os.getenv("LOGGING_LEVEL", "INFO"),
    format="%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

file_logger = logging.getLogger(__name__)
