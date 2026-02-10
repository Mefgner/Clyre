import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter

from routes.auth.views import auth_router
from routes.chatting.views import chat_router
from routes.thread.views import thread_router
from routes.user.views import user_router

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)

api_router = APIRouter()
api_router.include_router(chat_router, prefix="/chat")
api_router.include_router(auth_router, prefix="/auth")
api_router.include_router(user_router, prefix="/user")
api_router.include_router(thread_router, prefix="/thread")


@api_router.get("/health", tags=["api"])
def health():
    logging.info("Health check")
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


@api_router.get("/version", tags=["api"])
def version():
    logging.info("Version check")
    return {"app": "clyre-backend", "version": os.getenv("CLYRE_VERSION", "0.0.1")}
