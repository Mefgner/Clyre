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

# TODO: extract general code from view.
# TODO: refactor service function to make them more simple and less god-like.

# TODO: a initial way to compress chat history.

# TODO: try to make less abstractions while generating completion.
# TODO: make a queue for each user.
