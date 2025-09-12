import os
from datetime import datetime, timezone

from fastapi import APIRouter

from api.chatting.views import chat_router

api_router = APIRouter(tags=["core"])
api_router.include_router(chat_router, prefix="/chat")

@api_router.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@api_router.get("/version")
def version():
    return {"app": "clyre-backend", "version": os.getenv("CLYRE_VERSION", "0.0.1")}
