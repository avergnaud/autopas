"""PAS Assistant — Project lifecycle management.

Handles reading and writing project.json for each project.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

PROJECTS_DIR = BASE_DIR / "data" / "projects"


def _project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def _project_json_path(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"


def create_project(project_id: str, filename: str, user_email: str) -> dict:
    """Create project.json with status='created'.

    Args:
        project_id: UUID of the project.
        filename: Original uploaded filename.
        user_email: Email of the authenticated user.

    Returns:
        The created project dict.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data = {
        "id": project_id,
        "created_at": now,
        "updated_at": now,
        "user_email": user_email,
        "status": "created",
        "original_filename": filename,
        "format": "xlsx",
        "structure": None,
        "cadrage": None,
        "anonymization": None,
        "verbosity_level": 2,
        "progress_step": None,
        "error_message": None,
    }
    save_project(project_id, data)
    logger.info("Project %s created for %s", project_id, user_email)
    return data


def load_project(project_id: str) -> dict:
    """Read and return project.json.

    Args:
        project_id: UUID of the project.

    Returns:
        The project dict.

    Raises:
        FileNotFoundError: If project.json does not exist.
    """
    path = _project_json_path(project_id)
    if not path.exists():
        raise FileNotFoundError(f"Project {project_id} not found.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_project(project_id: str, data: dict) -> None:
    """Write project.json (full replacement).

    Args:
        project_id: UUID of the project.
        data: Full project dict to write.
    """
    path = _project_json_path(project_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_project(project_id: str, **fields) -> dict:
    """Update specific fields in project.json and return the updated dict.

    Args:
        project_id: UUID of the project.
        **fields: Fields to update (e.g., status="anonymizing").

    Returns:
        The updated project dict.
    """
    data = load_project(project_id)
    data.update(fields)
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_project(project_id, data)
    return data


def list_projects(user_email: str) -> list[dict]:
    """List all projects belonging to a user.

    Args:
        user_email: Email of the authenticated user.

    Returns:
        List of project dicts filtered by user_email, sorted by created_at descending.
    """
    if not PROJECTS_DIR.exists():
        return []

    projects: list[dict] = []
    for d in PROJECTS_DIR.iterdir():
        if not d.is_dir():
            continue
        path = d / "project.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("user_email") == user_email:
                projects.append(data)
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read project.json for %s", d.name)

    projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return projects


def recover_stale_projects() -> None:
    """At startup: move projects stuck in 'generating' to 'error'.

    Projects with status='generating' at startup were interrupted by a server
    restart; they will never complete, so we mark them as errors.
    """
    if not PROJECTS_DIR.exists():
        return

    for d in PROJECTS_DIR.iterdir():
        if not d.is_dir():
            continue
        path = d / "project.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("status") == "generating":
                data["status"] = "error"
                data["error_message"] = "Génération interrompue par redémarrage du serveur."
                data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                logger.warning("Recovered stale project %s → error", d.name)
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not recover project %s", d.name)
