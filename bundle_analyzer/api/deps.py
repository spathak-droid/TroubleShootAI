"""FastAPI dependency injection providers.

Centralises shared singletons (SessionStore) and common parameter
extraction (session lookup with 404 handling).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from bundle_analyzer.api.session import BundleSession, SessionStore

_store = SessionStore()


def get_store() -> SessionStore:
    """Return the global session store singleton.

    Returns:
        The shared SessionStore instance.
    """
    return _store


def get_session(
    bundle_id: str,
    store: SessionStore = Depends(get_store),
) -> BundleSession:
    """Look up a bundle session by id, raising 404 if not found.

    Args:
        bundle_id: The bundle/session identifier from the URL path.
        store: Injected session store.

    Returns:
        The matching BundleSession.

    Raises:
        HTTPException: 404 if no session exists for the given id.
    """
    session = store.get(bundle_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Bundle {bundle_id} not found",
        )
    return session
