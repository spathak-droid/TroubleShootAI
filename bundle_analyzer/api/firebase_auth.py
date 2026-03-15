"""Firebase authentication for the Bundle Analyzer API.

Verifies Firebase ID tokens from the frontend and extracts user identity.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, HTTPException, Request
from loguru import logger

_firebase_initialized = False


def _init_firebase() -> None:
    """Initialize Firebase Admin SDK (once)."""
    global _firebase_initialized
    if _firebase_initialized:
        return

    try:
        import firebase_admin
        from firebase_admin import credentials

        # Check if already initialized
        try:
            firebase_admin.get_app()
            _firebase_initialized = True
            return
        except ValueError:
            pass

        # Try service account JSON file first
        cred_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY")
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            # Use project ID only (works for token verification without service account)
            project_id = os.environ.get("FIREBASE_PROJECT_ID", "")
            if project_id:
                firebase_admin.initialize_app(options={"projectId": project_id})
            else:
                # Minimal init — will use GOOGLE_APPLICATION_CREDENTIALS or default
                firebase_admin.initialize_app()

        _firebase_initialized = True
        logger.info("Firebase Admin SDK initialized")
    except Exception as exc:
        logger.warning("Firebase Admin init failed: {}", exc)


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
        _init_firebase()
        from firebase_admin import auth

        decoded = auth.verify_id_token(token)
        uid: str = decoded["uid"]
        return uid
    except Exception as exc:
        logger.warning("Firebase token verification failed: {}", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_optional_user(request: Request) -> str | None:
    """Extract user ID if token present, otherwise return None.

    Used for endpoints that work with or without auth.

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
