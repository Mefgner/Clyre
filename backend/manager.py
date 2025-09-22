import uvicorn

from app import app
from utils import env, fields


def main():
    uvicorn.run(
        app,
        host=env.HOST,
        port=env.PORT,
        log_config=fields.UVICORN_LOGGING_CONFIG,
    )


if __name__ == "__main__":
    main()

# TODO: add streaming endpoint.
# TODO: a initial way to compress chat history.
# TODO: make a queue for each user.
