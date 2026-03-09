"""Logging helpers."""

from __future__ import annotations

import logging


def configure_logging(verbose: bool = False, level: str = "INFO") -> None:
    """Configure project logging."""

    resolved_level = "DEBUG" if verbose else level.upper()
    logging.basicConfig(
        level=getattr(logging, resolved_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )
    quiet_level = logging.INFO if verbose else logging.WARNING
    logging.getLogger("httpx").setLevel(quiet_level)
    logging.getLogger("httpcore").setLevel(quiet_level)
