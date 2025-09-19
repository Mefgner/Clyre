import logging
import sys

from fastapi import FastAPI

from api.views import api_router
from db import get_session_manager
from pipelines import llama
from utils import downloader, env

if env.DEBUG:
    LOGGING_LEVEL = logging.DEBUG
else:
    LOGGING_LEVEL = logging.INFO

Logger = logging.getLogger()
Logger.handlers.clear()

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(LOGGING_LEVEL)
handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))

Logger.addHandler(handler)

logging.getLogger("httpcore").setLevel(logging.WARNING)
Logger = logging.getLogger(__name__)

Logger.setLevel(logging.INFO)

downloader.predownload("binaries.yaml", "models.yaml")

app = FastAPI(title="Clyre API", version=env.CLYRE_VERSION)
app.include_router(api_router, prefix="/api")

app.add_event_handler("startup", get_session_manager().init_models)
app.add_event_handler("startup", llama.get_llama_pipeline().wait_for_startup)


def shutdown():
    Logger.info("Shutting down")
    llama_instance = llama.get_llama_pipeline()
    session_manager = get_session_manager()
    del llama_instance
    del session_manager


app.add_event_handler("shutdown", shutdown)
