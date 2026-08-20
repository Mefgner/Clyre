import logging

from fastapi import FastAPI
from starlette.responses import JSONResponse

# from starlette.middleware.cors import CORSMiddleware
import db
from crud.vector import get_vector_repository
from pipelines import embed, inference
from routes import views
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

# origins = [
#     "http://localhost",
#     "http://localhost:3000",
#     "http://0.0.0.0",
#     "http://192.168.137.1:3000",
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


@app.exception_handler(Exception)
async def handle_exception(request, exc):
    Logger.error("Unhandled exception: \n%s\n\n Request: %s", exc, request, exc_info=True)
    return JSONResponse({"error": str(exc)}, status_code=500)


# DB engine startup side effect

app.add_event_handler("shutdown", db.get_session_manager().close)


# Vector store schema (lives outside the ORM; created by the VectorRepository)


async def _ensure_vector_schema():
    await get_vector_repository().ensure_schema(db.get_session_manager().async_engine)


app.add_event_handler("startup", _ensure_vector_schema)

# Llama.cpp connection side effect

app.add_event_handler(
    "startup", inference.get_inference_pipeline(inference.Tier.SMALL).wait_for_startup
)
app.add_event_handler("startup", embed.get_embedding_pipeline().wait_for_startup)
