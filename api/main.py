# Tracing processes

# import hunter
# from hunter import Q
# hunter.trace(
#     ~Q(module_in=(".venv", "site-packages", "sqlalchemy")),
#     Q(module_in=("app", "utils", "services", "models", "manager", "views", "crud", "schemas", "pipelines", "db")),
#     stdlib=False,
#     action=hunter.CallPrinter(stream=open('startup_trace.txt', 'w', encoding='utf-8'))
# )

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
