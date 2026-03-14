"""PAS Assistant — FastAPI session dependencies."""

import os

from fastapi import HTTPException, Request

# When DEV_AUTH_BYPASS=true, authentication is skipped entirely.
# Use only for local development — never in production.
_DEV_USER = {"email": "dev@localhost", "name": "Dev User", "role": "admin"}


def _is_dev_bypass() -> bool:
    return os.environ.get("DEV_AUTH_BYPASS", "").lower() == "true"


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency — require an authenticated session.

    Returns:
        User dict with keys: email, name, role.

    Raises:
        HTTPException: 401 if no valid session exists.
    """
    if _is_dev_bypass():
        return _DEV_USER
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return user


async def get_optional_user(request: Request) -> dict | None:
    """FastAPI dependency — return current user or None if not authenticated."""
    if _is_dev_bypass():
        return _DEV_USER
    return request.session.get("user")
