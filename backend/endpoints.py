import os

from fastapi import FastAPI

from api.views import api_router

app = FastAPI(title="Clyre API", version=os.getenv("CLYRE_VERSION"))
app.include_router(api_router)
