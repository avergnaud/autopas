"""PAS Assistant — Azure AD OAuth2 client using MSAL."""

import logging
import os
from typing import Any

import msal

from app.config import get_config

logger = logging.getLogger(__name__)

_msal_app: msal.ConfidentialClientApplication | None = None


class AuthError(Exception):
    """Raised when Azure AD authentication fails."""


def _get_msal_app() -> msal.ConfidentialClientApplication:
    """Return (or lazily create) the MSAL ConfidentialClientApplication."""
    global _msal_app
    if _msal_app is None:
        cfg = get_config()["oauth2"]
        tenant_id: str = cfg["tenant_id"]
        client_id: str = cfg["client_id"]
        client_secret: str = os.environ.get(cfg["client_secret_env"], "")
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        _msal_app = msal.ConfidentialClientApplication(
            client_id,
            authority=authority,
            client_credential=client_secret,
        )
        logger.info("MSAL app initialized for tenant %s", tenant_id)
    return _msal_app


def _redirect_uri() -> str:
    """Return the OAuth2 redirect URI.

    The environment variable OAUTH2_REDIRECT_URI overrides app.yaml,
    which is useful for local development (http://localhost:8000/auth/callback).
    """
    override = os.environ.get("OAUTH2_REDIRECT_URI")
    if override:
        return override
    return get_config()["oauth2"]["redirect_uri"]


def build_auth_url(state: str) -> str:
    """Build the Azure AD authorization URL.

    Args:
        state: Anti-CSRF nonce included in the request.

    Returns:
        Full Azure AD authorization URL to redirect the user to.
    """
    cfg = get_config()["oauth2"]
    return _get_msal_app().get_authorization_request_url(
        scopes=cfg["scopes"],
        state=state,
        redirect_uri=_redirect_uri(),
    )


def exchange_code(code: str) -> dict[str, Any]:
    """Exchange an authorization code for tokens.

    Args:
        code: Authorization code received from Azure AD callback.

    Returns:
        Token result dict containing id_token_claims.

    Raises:
        AuthError: If the token exchange fails.
    """
    cfg = get_config()["oauth2"]
    result: dict[str, Any] = _get_msal_app().acquire_token_by_authorization_code(
        code=code,
        scopes=cfg["scopes"],
        redirect_uri=_redirect_uri(),
    )
    if "error" in result:
        error_desc = result.get("error_description", result.get("error", "unknown"))
        logger.error("Token exchange failed: %s", error_desc)
        raise AuthError(f"Token exchange failed: {error_desc}")
    return result
