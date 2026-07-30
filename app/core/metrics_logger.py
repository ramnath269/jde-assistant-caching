import json
import logging
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

metrics_logger = logging.getLogger("jde-metrics")
metrics_logger.setLevel(logging.INFO)

handler = logging.FileHandler(
    LOG_DIR / "metrics.jsonl",
    encoding="utf-8",
)

handler.setFormatter(logging.Formatter("%(message)s"))

metrics_logger.handlers.clear()
metrics_logger.addHandler(handler)
metrics_logger.propagate = False