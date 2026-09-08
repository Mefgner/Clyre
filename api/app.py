import logging
from pathlib import Path

from fastapi import FastAPI
from starlette.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

# from starlette.middleware.cors import CORSMiddleware
import db
from crud.vector import get_vector_repository
from pipelines import embed, inference
from routes import views
from services import generation as services_generation
from shared.pyutils.logs import setup_logging
from utils import env

# Set up logging

logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

Logger = setup_logging()

Logger.info("Pre-downloading necessary files...")

# Init FastAPI, set routes

app = FastAPI(title="Clyre API", version=env.CLYRE_VERSION)
app.include_router(views.api_router, prefix="/api")

# Static web build (web/dist) served on the same origin as the API for both
# delivery shapes. The SPA fallback below answers non-API routes with index.html.

_APP_ROOT = Path(__file__).resolve().parent.parent
_DIST_DIR = next(
    (path for path in (_APP_ROOT / "web" / "dist", _APP_ROOT / "dist") if path.exists()),
    _APP_ROOT / "dist",
)
_DIST_INDEX = _DIST_DIR / "index.html"

if _DIST_INDEX.exists():
    _DIST_ROOT = _DIST_DIR.resolve()
    app.mount("/assets", StaticFiles(directory=_DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        candidate = (_DIST_DIR / full_path).resolve()
        if full_path and candidate.is_relative_to(_DIST_ROOT) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST_INDEX)

else:
    Logger.warning(
        "Built frontend not found at %s; the API will serve only /api routes. "
        "Run `npm ci && npm run build` before boot.",
        _DIST_DIR,
    )


@app.exception_handler(Exception)
async def handle_exception(request, exc):
    Logger.error(
        "Unhandled exception for %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse({"error": "Internal server error"}, status_code=500)


app.add_event_handler("shutdown", inference.close_inference_pipelines)
app.add_event_handler("shutdown", db.get_session_manager().close)


async def _ensure_vector_schema():
    await get_vector_repository().ensure_schema(db.get_session_manager().async_engine)


app.add_event_handler("startup", _ensure_vector_schema)


async def _sweep_interrupted_generations():
    await services_generation.sweep_interrupted_runs()


app.add_event_handler("startup", _sweep_interrupted_generations)
app.add_event_handler(
    "startup", inference.get_inference_pipeline(inference.Tier.SMALL).wait_for_startup
)
app.add_event_handler("startup", embed.get_embedding_pipeline().wait_for_startup)
