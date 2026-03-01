"""PAS Assistant — FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.web import router as web_router
from app.auth.router import router as auth_router
from app.auth.session import get_current_user, get_optional_user
from app.config import BASE_DIR, load_config
from app.models.project import ProjectStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Load .env early so SESSION_SECRET_KEY is available when adding SessionMiddleware.
# load_config() will call load_dotenv() again in lifespan (idempotent).
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    load_dotenv(_env_file)


def _recover_stale_generating_projects() -> None:
    """Reset projects stuck in 'generating' state (e.g. after an unclean restart)."""
    from app.services.project_manager import PROJECTS_DIR, load_project, save_project

    if not PROJECTS_DIR.exists():
        return
    for d in PROJECTS_DIR.iterdir():
        if not d.is_dir():
            continue
        project = load_project(d.name)
        if project and project.status == ProjectStatus.generating:
            logger.warning(
                "Project %s was stuck in 'generating' state — marking as error", project.id
            )
            project.status = ProjectStatus.error
            project.error_message = "Traitement interrompu (redémarrage du serveur)."
            project.progress_step = "Erreur : traitement interrompu"
            save_project(project)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load full configuration at startup."""
    load_config()
    _recover_stale_generating_projects()
    logger.info("PAS Assistant started")
    yield
    logger.info("PAS Assistant stopped")


app = FastAPI(
    title="PAS Assistant",
    description="API REST — Plans d'Assurance Sécurité",
    version="0.1.0",
    lifespan=lifespan,
)

# SessionMiddleware must be added before any route handler runs.
# https_only=True sets the Secure flag on the cookie (requires HTTPS in the browser).
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET_KEY", "dev-changeme-in-prod"),
    max_age=86400,
    https_only=True,
    same_site="lax",
)

app.include_router(auth_router)
app.include_router(web_router)


@app.get("/api/health")
async def health() -> dict:
    """Health check — no authentication required."""
    return {"status": "ok"}


@app.get("/api/auth/me")
async def auth_me(user: dict = Depends(get_current_user)) -> dict:
    """Return the current authenticated user info."""
    return user


@app.get("/private")
async def private_page(user: dict | None = Depends(get_optional_user)):
    """Serve the private page, or redirect to / if not authenticated."""
    if user is None:
        return RedirectResponse("/", status_code=302)
    return FileResponse(BASE_DIR / "web" / "private.html")


# Mount static files last — after all explicit FastAPI routes.
# In production, web/ is deployed to BASE_DIR/web by Ansible.
# In dev, run from the _v03/ directory with PAS_BASE_DIR=. uvicorn ...
_web_dir = BASE_DIR / "web"
if _web_dir.exists():
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="static")
else:
    logger.warning("web/ directory not found at %s — static files not served", _web_dir)
