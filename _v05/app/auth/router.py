"""PAS Assistant — Auth routes (OAuth2 Azure AD Authorization Code flow)."""

import logging
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.azure_ad import AuthError, build_auth_url, exchange_code
from app.config import get_config

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/auth/login")
async def login(request: Request) -> RedirectResponse:
    """Redirect the user to the Azure AD login page."""
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    auth_url = build_auth_url(state)
    return RedirectResponse(auth_url, status_code=302)


@router.get("/auth/callback")
async def callback(request: Request) -> RedirectResponse:
    """Handle the Azure AD OAuth2 callback."""
    # CSRF protection: validate state
    state = request.query_params.get("state")
    expected_state = request.session.get("oauth_state")
    if not state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Check for error from Azure AD
    error = request.query_params.get("error")
    if error:
        error_desc = request.query_params.get("error_description", error)
        logger.warning("Auth callback received error from Azure AD: %s", error_desc)
        raise HTTPException(status_code=400, detail=error_desc)

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    try:
        result = exchange_code(code)
    except AuthError as exc:
        logger.error("Token exchange failed: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    claims = result.get("id_token_claims", {})
    email: str = claims.get("preferred_username", "")
    name: str = claims.get("name", email)

    authorized_users: dict = get_config()["authorized_users"]
    if email not in authorized_users:
        logger.warning("Unauthorized login attempt: %s", email)
        return RedirectResponse("/auth/denied", status_code=302)

    role: str = authorized_users[email]
    request.session["user"] = {"email": email, "name": name, "role": role}
    request.session.pop("oauth_state", None)

    logger.info("User logged in: %s (%s)", email, role)
    return RedirectResponse("/private", status_code=302)


@router.get("/auth/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session and redirect to home."""
    request.session.clear()
    return RedirectResponse("/", status_code=302)


@router.get("/auth/denied", response_class=HTMLResponse)
async def denied() -> str:
    """Access denied page — shown when user is authenticated but not authorised."""
    return """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Accès refusé — PAS Assistant</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <main>
    <h1>Accès refusé</h1>
    <p>Votre compte n'est pas autorisé à utiliser cette application.</p>
    <p>Contactez l'administrateur pour obtenir un accès.</p>
    <a href="/" class="btn">Retour à l'accueil</a>
  </main>
</body>
</html>"""
