"""Programmatic Alembic entrypoint used by the deployment launchers.

Runs `alembic upgrade head` against the configured DATABASE_URL. It is invoked
by the desktop launcher (`run-desktop.py`) and the Dockerfile CMD
(`python -m db_migrations`) before uvicorn starts, so both delivery shapes get
the schema without holding the migrations inside the async app lifecycle.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config

_APP_ROOT = Path(__file__).resolve().parent.parent


def _alembic_config() -> Config:
    cfg = Config(str(_APP_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_APP_ROOT / "alembic"))
    return cfg


def run_migrations() -> None:
    """Apply pending migrations (idempotent)."""
    command.upgrade(_alembic_config(), "head")


if __name__ == "__main__":
    run_migrations()
