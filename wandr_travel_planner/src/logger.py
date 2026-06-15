"""
Centralized logging for the travel planner.

Each named logger writes to its own file under logs/ AND to a master
trace file (logs/master.log) so you can either zoom in on one agent or
read the full end-to-end execution in one place.

Usage:
    from src.logger import get_logger
    log = get_logger("destination")
    log.info("Called REST Countries for %s", city)
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-12s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Loggers we've already configured this process — avoids duplicate handlers
# when get_logger() is called multiple times for the same name.
_configured: set[str] = set()


def _build_handler(path: Path) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    return handler


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes to logs/{name}.log AND logs/master.log."""
    logger = logging.getLogger(name)
    if name in _configured:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # don't double-log via root

    # Per-agent file
    logger.addHandler(_build_handler(LOGS_DIR / f"{name}.log"))
    # Master trace file
    logger.addHandler(_build_handler(LOGS_DIR / "master.log"))

    # Console output as well — helpful while developing
    if os.getenv("LOG_TO_CONSOLE", "1") == "1":
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
        console.setLevel(logging.INFO)
        logger.addHandler(console)

    _configured.add(name)
    return logger


def groq_model() -> str:
    """Return the Groq model name, stripping any accidental whitespace."""
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()


def log_state_transition(from_node: str, to_node: str, reason: str = "") -> None:
    """Convenience helper for the supervisor to log routing decisions."""
    log = get_logger("supervisor")
    msg = f"ROUTE  {from_node:>12s} -> {to_node:<12s}"
    if reason:
        msg += f"  ({reason})"
    log.info(msg)
