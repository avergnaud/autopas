"""PAS Assistant — FastAPI session dependencies."""

from fastapi import HTTPException, Request


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency — require an authenticated session.

    Returns:
        User dict with keys: email, name, role.

    Raises:
        HTTPException: 401 if no valid session exists.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return user


async def get_optional_user(request: Request) -> dict | None:
    """FastAPI dependency — return current user or None if not authenticated."""
    return request.session.get("user")
