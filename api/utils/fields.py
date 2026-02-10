UVICORN_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "loggers": {
        "uvicorn": {"level": "INFO", "propagate": True},
        "uvicorn.error": {"level": "INFO", "propagate": True},
        "uvicorn.access": {"level": "INFO", "propagate": True},
    },
}
