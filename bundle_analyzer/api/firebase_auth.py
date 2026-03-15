"""Firebase authentication for the Bundle Analyzer API.

Verifies Firebase ID tokens using Google's public keys directly,
without requiring a service account or Application Default Credentials.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, Request
from loguru import logger

# Google's public key endpoint for Firebase tokens
_GOOGLE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
_cached_certs: dict[str, str] = {}
_certs_fetched_at: float = 0
_CERTS_TTL = 3600  # refresh keys every hour


def _get_project_id() -> str:
    """Get the Firebase project ID from environment."""
    pid = os.environ.get("FIREBASE_PROJECT_ID", "")
    if not pid:
        raise RuntimeError("FIREBASE_PROJECT_ID not set")
    return pid


def _fetch_google_certs() -> dict[str, str]:
    """Fetch Google's public signing certificates for Firebase tokens.

    Returns:
        Dict mapping key ID to PEM certificate string.
    """
    global _cached_certs, _certs_fetched_at

    now = time.time()
    if _cached_certs and (now - _certs_fetched_at) < _CERTS_TTL:
        return _cached_certs

    try:
        resp = httpx.get(_GOOGLE_CERTS_URL, timeout=10)
        resp.raise_for_status()
        _cached_certs = resp.json()
        _certs_fetched_at = now
        logger.info("Fetched {} Google signing certs", len(_cached_certs))
    except Exception as exc:
        logger.warning("Failed to fetch Google certs: {}", exc)
        if _cached_certs:
            return _cached_certs
        raise

    return _cached_certs


def _verify_firebase_token(token: str) -> dict[str, Any]:
    """Verify a Firebase ID token using Google's public keys.

    Args:
        token: The raw JWT token string.

    Returns:
        Decoded token payload dict.

    Raises:
        Exception: If verification fails.
    """
    project_id = _get_project_id()
    certs = _fetch_google_certs()

    # Decode header to get key ID
    header = jwt.get_unverified_header(token)
    kid = header.get("kid", "")

    cert_pem = certs.get(kid)
    if not cert_pem:
        # Refresh certs in case keys rotated
        global _certs_fetched_at
        _certs_fetched_at = 0
        certs = _fetch_google_certs()
        cert_pem = certs.get(kid)
        if not cert_pem:
            raise ValueError(f"No matching certificate for kid={kid}")

    # Verify and decode
    decoded = jwt.decode(
        token,
        cert_pem,
        algorithms=["RS256"],
        audience=project_id,
        issuer=f"https://securetoken.google.com/{project_id}",
    )

    # Ensure uid exists
    if "sub" not in decoded or not decoded["sub"]:
        raise ValueError("Token missing sub (uid) claim")

    return decoded


async def get_current_user(request: Request) -> str:
    """Extract and verify the Firebase user ID from the Authorization header.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The Firebase user UID string.

    Raises:
        HTTPException: 401 if token is missing or invalid.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authentication token")

    token = auth_header[7:]  # strip "Bearer "

    try:
        decoded = _verify_firebase_token(token)
        uid: str = decoded["sub"]
        return uid
    except Exception as exc:
        logger.warning("Firebase token verification failed: {}", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_optional_user(request: Request) -> str | None:
    """Extract user ID if token present, otherwise return None.

    Args:
        request: The incoming FastAPI request.

    Returns:
        Firebase user UID or None.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    try:
        return await get_current_user(request)
    except HTTPException:
        return None
