from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.monitors import router as monitors_router
from app.api.public import router as public_router
from app.api.research import router as research_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="ResearchMind API", version="1.0.0")
cors_list = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
allow_any_origin = "*" in cors_list
if allow_any_origin:
    cors_list = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_list,
    allow_credentials=not allow_any_origin,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(research_router)
app.include_router(monitors_router)
app.include_router(public_router)



@app.get("/")
def root():
    return {"name": "ResearchMind", "docs": "/docs"}
