import uvicorn

from app import app
from utils import cfg


def main():
    uvicorn.run(
        app,
        host=cfg.get_host(),
        port=int(cfg.get_port()),
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "fmt": "%(levelname)s:uvicorn:%(message)s",
                    "use_colors": None,
                },
                "access": {
                    "()": "uvicorn.logging.AccessFormatter",
                    "fmt": '%(levelname)s:uvicorn:"%(request_line)s":%(status_code)s',
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
                "access": {
                    "formatter": "access",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "uvicorn.error": {"level": "INFO"},
                "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
            },
        },
    )


if __name__ == "__main__":
    main()

# TODO: switch from "get from the env something" functions to PydanticSettings.
# TODO: add streaming endpoint.
# TODO: bring better logging.
# TODO: bring better error handling and raising. truncate traceback up to project's files excluding .venv modules.
# TODO: a initial way to compress chat history.
# TODO: make a queue for each user.
# TODO: rewrite downloader in a better way.
# TODO: implement refresh token logic
