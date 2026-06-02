from shared.pyutils.env import Settings

# Required fields are populated from the environment / .env, which pyright can't model.
env = Settings()  # pyright: ignore[reportCallIssue]
