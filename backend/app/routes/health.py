import os

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    settings = get_settings()
    # Render exposes the deploy commit via RENDER_GIT_COMMIT. Surfacing it
    # here is the cheapest way to verify "did my push actually deploy?"
    # without needing dashboard access.
    commit = (
        os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("GIT_COMMIT")
        or os.environ.get("VERCEL_GIT_COMMIT_SHA")
        or "unknown"
    )
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "commit": commit[:12],
    }
