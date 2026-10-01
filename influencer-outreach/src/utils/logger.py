"""Shared logger writing to console and logs/pipeline.log."""
import logging
from pathlib import Path

_FMT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def get_logger(name: str, log_file: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(_FMT))
    logger.addHandler(sh)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FMT))
        logger.addHandler(fh)
    return logger
