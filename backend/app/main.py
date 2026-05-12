from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import init_firebase_admin
from .config import get_settings
from .database import Base, engine
from .migrations import ensure_leads_schema
from .routes import health, leads, scrape

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Import models so SQLAlchemy registers them on Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_leads_schema(engine)
    init_firebase_admin()
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Auto-allow any Vercel deployment — covers production, branch previews, and
    # renames without needing a CORS_ORIGINS env update for each new URL.
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(scrape.router, prefix="/api")


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "docs": "/docs",
    }
