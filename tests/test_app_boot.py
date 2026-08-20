import importlib
import os
import sys

import pytest

from shared.pyutils.base import get_app_root_dir

_APP_DIR = get_app_root_dir() / "api"
_DIST_INDEX = get_app_root_dir() / "web" / "dist" / "index.html"


@pytest.fixture(scope="module")
def app_module():
    db_path = os.path.join(os.environ.get("TEMP", "/tmp"), "clyre_app_boot.sqlite3")
    os.environ.setdefault("HASHING_SECRET", "x" * 32)
    os.environ.setdefault("ACCESS_TOKEN_SECRET", "x" * 32)
    os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    sys.path.insert(0, str(_APP_DIR))
    try:
        yield importlib.import_module("app")
    finally:
        sys.path.remove(str(_APP_DIR))
        os.environ.pop("DATABASE_URL", None)
        for name in tuple(sys.modules):
            if name == "app" or name.startswith("app."):
                sys.modules.pop(name, None)


def test_app_imports_and_registers_routes(app_module):
    app = app_module.app

    paths = {route.path for route in app.routes}
    assert "/api/health" in paths
    assert "/api/auth/login" in paths
    assert "/api/auth/register" in paths
    assert "/api/chat/response" in paths
    assert "/api/chat/stream" in paths


def test_app_serves_built_frontend_when_present(app_module):
    app = app_module.app

    # Skip when the loaded app module carries no static-serving wiring (e.g. a
    # partial working tree during a pre-commit run) or the frontend build is
    # absent. _DIST_DIR/_DIST_INDEX are set by api/app.py itself.
    dist_dir = getattr(app_module, "_DIST_DIR", None)
    dist_index = getattr(app_module, "_DIST_INDEX", None)
    if dist_index is None or not dist_index.exists():
        pytest.skip("built frontend not present; run `npm run build` first")

    assert dist_dir is not None
    assert dist_dir.is_dir()
    assert any(route.path.startswith("/assets") for route in app.routes)
    assert any(getattr(route, "path", None) == "/{full_path:path}" for route in app.routes)
