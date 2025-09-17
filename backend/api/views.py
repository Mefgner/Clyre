import os
from datetime import datetime, timezone

from fastapi import APIRouter

from api.chatting.views import chat_router
from api.auth.views import auth_router

api_router = APIRouter()
api_views = APIRouter(tags=["api"])
api_router.include_router(api_views, prefix="")
api_router.include_router(chat_router, prefix="/chat")
api_router.include_router(auth_router, prefix="/auth")


@api_views.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@api_views.get("/version")
def version():
    return {"app": "clyre-backend", "version": os.getenv("CLYRE_VERSION", "0.0.1")}
