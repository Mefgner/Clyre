import logging

import colorlog
import sys
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

import db
from api import views
from pipelines import llama
from utils import cfg, downloader, env

logging.getLogger("httpcore").setLevel(logging.WARNING)

logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

Logger = logging.getLogger()

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(cfg.get_logging_level())
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

Logger.addHandler(handler)

Logger.info("Pre-downloading necessary files...")

downloader.predownload("binaries.yaml", "models.yaml")

app = FastAPI(title="Clyre API", version=env.CLYRE_VERSION)
app.include_router(views.api_router, prefix="/api")

origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://0.0.0.0",
    "http://192.168.137.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def handle_exception(request, exc):
    Logger.error(f"Unhandled exception: \n%s\n\n Request: %s", exc, request, exc_info=True)
    raise exc


app.add_event_handler("startup", db.get_session_manager().init_models)
app.add_event_handler("startup", llama.get_current_llama_pipeline().wait_for_startup)
app.add_event_handler("shutdown", db.get_session_manager().close)
app.add_event_handler("shutdown", llama.get_current_llama_pipeline().close)
