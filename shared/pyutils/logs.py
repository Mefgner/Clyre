import logging
import sys

import colorlog

from shared.pyutils.env import get_logging_level


def setup_logging() -> logging.Logger:
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logger = logging.getLogger()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(get_logging_level())
    handler.setFormatter(
        colorlog.ColoredFormatter(
            fmt="%(thin_light_white)s%(asctime)s%(reset)s - %(log_color)s%(levelname)s%(reset)s - %(name)s: %(thin_light_green)s%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                "DEBUG": "purple",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
        )
    )

    if not logger.handlers:
        logger.addHandler(handler)
    return logger


__all__ = ["setup_logging"]
