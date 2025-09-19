import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter

from api.auth.views import auth_router
from api.chatting.views import chat_router

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)

api_router = APIRouter()
api_views = APIRouter(tags=["api"])
api_router.include_router(api_views, prefix="")
api_router.include_router(chat_router, prefix="/chat")
api_router.include_router(auth_router, prefix="/auth")


@api_views.get("/health")
def health():
    logging.info("Health check")
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


@api_views.get("/version")
def version():
    logging.info("Version check")
    return {"app": "clyre-backend", "version": os.getenv("CLYRE_VERSION", "0.0.1")}
