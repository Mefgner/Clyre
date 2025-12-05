import logging

import sys
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

import db
from api import views
from utils import cfg, downloader, env

logging.getLogger("httpcore").setLevel(logging.WARNING)

logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

Logger = logging.getLogger()
Logger.handlers.clear()

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(cfg.get_logging_level())
handler.setFormatter(
    logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
)

Logger.addHandler(handler)

downloader.predownload("binaries.yaml", "models.yaml")

app = FastAPI(title="Clyre API", version=env.CLYRE_VERSION)
app.include_router(views.api_router, prefix="/api")

origins = [
    "http://localhost",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_event_handler("startup", db.get_session_manager().init_models)
# app.add_event_handler("startup", llama.get_current_llama_pipeline().wait_for_startup)
app.add_event_handler("shutdown", db.get_session_manager().close)
# app.add_event_handler("shutdown", llama.get_current_llama_pipeline().close)
