from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import asyncio

from .config import settings
from .api.v1.router import api_router
from .core.database import init_db
from .ai.knowledge import KnowledgeBase

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.DEBUG else None,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    description="MoMiChat Backend for AI Milk Tea Bot"
)

# Sanitize CORS: wildcard origin + credentials is invalid per spec
_origins = settings.ALLOWED_ORIGINS
_credentials = True
if "*" in _origins:
    _origins = ["*"]
    _credentials = False  # Browsers reject wildcard + credentials anyway

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    # Setup Database
    await init_db()
    
    # Load Knowledge Base
    kb = KnowledgeBase()
    # Path adjusts since main is in src/momichat/
    csv_path = Path(__file__).parent.parent.parent / "Menu.csv"
    kb.initialize_menu(csv_path)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "version": settings.VERSION,
        "status": "online"
    }

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
