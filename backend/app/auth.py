"""Firebase ID token verification for protected API routes.

Reads FIREBASE_SERVICE_ACCOUNT_JSON (the JSON string of a Firebase Admin SDK
service account key) once at startup, then `require_user` validates the
`Authorization: Bearer <idToken>` header on every protected request.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache

import firebase_admin
from fastapi import Header, HTTPException, status
from firebase_admin import auth as fb_auth, credentials

from .config import get_settings

log = logging.getLogger(__name__)

# Mirror of frontend/src/lib/firebase.js ADMIN_EMAILS and firestore.rules.
ADMIN_EMAILS = frozenset({
    "muhammadnabeer2004@gmail.com",
    "muhammadusman193744@gmail.com",
})


@dataclass(frozen=True)
class CurrentUser:
    uid: str
    email: str | None
    is_admin: bool


@lru_cache(maxsize=1)
def _init_admin() -> firebase_admin.App:
    settings = get_settings()
    raw = settings.firebase_service_account_json
    if not raw:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON is unset. Download a service account "
            "JSON from Firebase Console -> Project settings -> Service accounts, "
            "and paste its contents into this env var."
        )
    cred = credentials.Certificate(json.loads(raw))
    return firebase_admin.initialize_app(cred)


def init_firebase_admin() -> None:
    """Eagerly initialize at startup so config issues fail fast."""
    _init_admin()


def _verify_token(token: str) -> CurrentUser:
    _init_admin()
    try:
        decoded = fb_auth.verify_id_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid auth token: {exc}",
        ) from exc

    uid = decoded["uid"]
    email = (decoded.get("email") or "").lower() or None
    is_admin = email is not None and email in ADMIN_EMAILS
    return CurrentUser(uid=uid, email=email, is_admin=is_admin)


def require_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token.",
        )
    return _verify_token(authorization[7:].strip())
