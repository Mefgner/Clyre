import logging
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

import db
from routes import views
from pipelines import llama
from utils import env
from shared.pyutils.logs import setup_logging

# Set up logging

logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

Logger = setup_logging()

Logger.info("Pre-downloading necessary files...")

# Init FastAPI, set routes

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
    Logger.error("Unhandled exception: \n%s\n\n Request: %s", exc, request, exc_info=True)
    raise exc


# DB engine startup side effect

app.add_event_handler("startup", db.get_session_manager().init_models)
app.add_event_handler("shutdown", db.get_session_manager().close)

# Llama.cpp connection side effect

app.add_event_handler("startup", llama.get_current_llama_pipeline().wait_for_startup)
