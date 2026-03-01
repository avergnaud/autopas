"""Project lifecycle management — filesystem backed."""
from __future__ import annotations

import json
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.config import BASE_DIR
from app.models.project import DocumentStructure, Project, ProjectStatus

PROJECTS_DIR = BASE_DIR / "data" / "projects"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def create_project(user_email: str, original_filename: str, file_bytes: bytes) -> Project:
    """Create a new project directory, save the original file, return the Project."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    rand = secrets.token_hex(3)
    project_id = f"proj_{ts}_{rand}"

    ext = Path(original_filename).suffix.lower().lstrip(".")
    project_dir = _project_dir(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    orig_path = project_dir / f"original.{ext}"
    orig_path.write_bytes(file_bytes)

    project = Project(
        id=project_id,
        created_at=_now(),
        updated_at=_now(),
        user_email=user_email,
        status=ProjectStatus.created,
        original_filename=original_filename,
        format=ext,
    )
    save_project(project)
    return project


def save_project(project: Project) -> None:
    """Persist project state to disk."""
    project.updated_at = _now()
    project_dir = _project_dir(project.id)
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / "project.json"
    path.write_text(project.model_dump_json(indent=2), encoding="utf-8")


def load_project(project_id: str) -> Project | None:
    """Load project from disk; return None if not found."""
    path = _project_dir(project_id) / "project.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Project(**data)


def list_projects(user_email: str) -> list[Project]:
    """List all projects for a user, newest first."""
    if not PROJECTS_DIR.exists():
        return []
    projects = []
    for d in PROJECTS_DIR.iterdir():
        if not d.is_dir():
            continue
        project = load_project(d.name)
        if project and project.user_email == user_email:
            projects.append(project)
    projects.sort(key=lambda p: p.created_at, reverse=True)
    return projects


def get_original_path(project_id: str, fmt: str) -> Path:
    return _project_dir(project_id) / f"original.{fmt}"


def get_working_path(project_id: str, fmt: str) -> Path:
    return _project_dir(project_id) / f"working.{fmt}"


def get_output_path(project_id: str, fmt: str) -> Path:
    return _project_dir(project_id) / f"output.{fmt}"


def get_attention_path(project_id: str) -> Path:
    return _project_dir(project_id) / "attention.md"


def create_working_copy(project: Project) -> Path:
    """Copy original file to working.{fmt} and return the path."""
    orig = get_original_path(project.id, project.format)
    working = get_working_path(project.id, project.format)
    shutil.copy2(orig, working)
    return working


def delete_project(project_id: str) -> bool:
    """Delete a project directory entirely. Returns True if deleted, False if not found."""
    project_dir = _project_dir(project_id)
    if not project_dir.exists():
        return False
    shutil.rmtree(project_dir)
    return True


def update_status(
    project: Project,
    status: ProjectStatus,
    progress_step: str = "",
    progress_pct: int = 0,
) -> None:
    """Update status/progress and persist."""
    project.status = status
    project.progress_step = progress_step
    project.progress_pct = progress_pct
    save_project(project)
