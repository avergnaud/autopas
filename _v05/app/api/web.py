"""REST API — endpoints de l'interface web."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth.session import get_current_user
from app.config import get_config
from app.models.project import DocumentStructure, Project, ProjectStatus, SheetStructure
from app.services import project_manager, response_generator

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_EXTS = {"xlsx", "docx"}
_MAX_UPLOAD = 50 * 1024 * 1024  # 50 MB


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _require_project(project_id: str, user: dict) -> Project:
    project = project_manager.load_project(project_id)
    if project is None:
        raise HTTPException(404, f"Projet {project_id} introuvable")
    if project.user_email != user["email"]:
        raise HTTPException(403, "Accès interdit")
    return project


def _project_dict(project: Project) -> dict:
    d = project.model_dump()
    if project.structure:
        d["structure"] = project.structure.model_dump()
    return d


def _parse_structure_dict(fmt: str, raw: dict) -> DocumentStructure:
    """Convert the raw dict (from Claude or from frontend) into DocumentStructure."""
    if fmt == "xlsx":
        sheets_data = raw.get("sheets", [])
        sheets = [
            SheetStructure(
                name=s.get("name", "Sheet1"),
                has_questions=s.get("has_questions", True),
                id_column=s.get("id_column") or None,
                question_column=s.get("question_column", "A"),
                response_columns=s.get("response_columns", ["B"]),
                header_row=int(s.get("header_row", 1)),
                first_data_row=int(s.get("first_data_row", 2)),
            )
            for s in sheets_data
        ]
        if not sheets:
            sheets = [SheetStructure(name="Sheet1", question_column="A", response_columns=["B"])]
        return DocumentStructure(format="xlsx", sheets=sheets)
    else:
        return DocumentStructure(
            format="docx",
            pattern=raw.get("pattern", ""),
            response_marker=raw.get("response_marker", "Réponse du titulaire"),
        )


def _default_structure(fmt: str) -> DocumentStructure:
    if fmt == "xlsx":
        return DocumentStructure(
            format="xlsx",
            sheets=[SheetStructure(name="Sheet1", question_column="A", response_columns=["B"])],
        )
    return DocumentStructure(format="docx", response_marker="Réponse du titulaire")


# ─── POST /api/projects — Upload + structure analysis ─────────────────────────


@router.post("/api/projects")
async def create_project(
    file: UploadFile,
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload questionnaire, detect structure via Claude, return project."""
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(400, f"Format non supporté : .{ext}. Acceptés : xlsx, docx")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Fichier vide")
    if len(file_bytes) > _MAX_UPLOAD:
        raise HTTPException(413, "Fichier trop volumineux (max 50 Mo)")

    project = project_manager.create_project(user["email"], filename, file_bytes)

    # Analyze structure via Claude (run in thread pool to avoid blocking the event loop)
    try:
        from app.services import claude_client, parser_xlsx, parser_docx
        orig_path = project_manager.get_original_path(project.id, ext)
        if ext == "xlsx":
            raw_content = parser_xlsx.extract_raw_content(orig_path)
        else:
            raw_content = parser_docx.extract_raw_content(orig_path)

        structure_data = await anyio.to_thread.run_sync(
            lambda: claude_client.analyze_structure(raw_content, ext)
        )
        inner = structure_data.get("structure", structure_data)
        structure = _parse_structure_dict(ext, inner)
    except Exception as exc:
        logger.error("Structure analysis failed for %s: %s", project.id, exc)
        structure = _default_structure(ext)

    project.structure = structure
    project.status = ProjectStatus.structure_detected
    project_manager.save_project(project)
    return _project_dict(project)


# ─── GET /api/projects ────────────────────────────────────────────────────────


@router.get("/api/projects")
async def list_projects(user: dict = Depends(get_current_user)) -> list[dict]:
    projects = project_manager.list_projects(user["email"])
    return [_project_dict(p) for p in projects]


# ─── GET /api/projects/{id} ───────────────────────────────────────────────────


@router.get("/api/projects/{project_id}")
async def get_project(project_id: str, user: dict = Depends(get_current_user)) -> dict:
    return _project_dict(_require_project(project_id, user))


# ─── PUT /api/projects/{id}/structure ─────────────────────────────────────────


class StructureBody(BaseModel):
    structure: dict[str, Any]


@router.put("/api/projects/{project_id}/structure")
async def update_structure(
    project_id: str,
    body: StructureBody,
    user: dict = Depends(get_current_user),
) -> dict:
    """Validate / correct the detected structure."""
    project = _require_project(project_id, user)
    project.structure = _parse_structure_dict(project.format, body.structure)
    project.status = ProjectStatus.structure_detected
    project_manager.save_project(project)
    return _project_dict(project)


# ─── GET /api/projects/{id}/questions ─────────────────────────────────────────


@router.get("/api/projects/{project_id}/questions")
async def get_questions(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return cadrage questions parsed from questions.txt."""
    _require_project(project_id, user)
    config = get_config()
    raw_questions: list[dict] = config.get("questions", [])
    verbosity_levels: dict = config.get("verbosity", {}).get("levels", {})

    api_questions = []
    for idx, q in enumerate(raw_questions):
        condition = None
        raw_cond: str | None = q.get("condition")
        if raw_cond:
            # "previous == \"value\"" or "previous contains \"value\""
            # Resolve "previous" to the question index before this one (1-based id)
            prev_id = idx  # idx is 0-based; id will be idx+1; previous = idx
            if "contains" in raw_cond:
                m = re.search(r'"([^"]+)"', raw_cond)
                value = m.group(1) if m else ""
                condition = {"question_id": prev_id, "operator": "contains", "value": value}
            else:
                m = re.search(r'"([^"]+)"', raw_cond)
                value = m.group(1) if m else ""
                condition = {"question_id": prev_id, "operator": "equals", "value": value}

        api_questions.append({
            "id": idx + 1,
            "text": q.get("text", ""),
            "type": "options" if q.get("options") else q.get("type", "text"),
            "options": q.get("options"),
            "multi": q.get("multi", False),
            "condition": condition,
        })

    verbosity_options = [
        f"{lvl} — {data.get('label', '')} ({data.get('max_words', '')} mots max)"
        for lvl, data in sorted(verbosity_levels.items(), key=lambda x: int(x[0]))
    ]

    verbosity_question = {
        "id": 99,
        "text": "Quel niveau de détail souhaitez-vous pour les réponses ?",
        "type": "options",
        "options": verbosity_options,
        "multi": False,
        "condition": None,
    }

    return {"questions": api_questions, "verbosity_question": verbosity_question}


# ─── POST /api/projects/{id}/cadrage ──────────────────────────────────────────


class CadrageBody(BaseModel):
    answers: dict[str, Any]
    verbosity_level: int = 2


@router.post("/api/projects/{project_id}/cadrage")
async def submit_cadrage(
    project_id: str,
    body: CadrageBody,
    user: dict = Depends(get_current_user),
) -> dict:
    project = _require_project(project_id, user)
    project.cadrage = body.answers
    project.verbosity_level = body.verbosity_level
    project.status = ProjectStatus.cadrage
    project_manager.save_project(project)
    return _project_dict(project)


# ─── POST /api/projects/{id}/anonymize ────────────────────────────────────────


class AnonymizeBody(BaseModel):
    mappings: list[dict[str, str]]  # [{"real": "...", "alias": "..."}]


@router.post("/api/projects/{project_id}/anonymize")
async def submit_anonymize(
    project_id: str,
    body: AnonymizeBody,
    user: dict = Depends(get_current_user),
) -> dict:
    project = _require_project(project_id, user)
    project.anonymization = {
        m["real"]: m["alias"] for m in body.mappings if m.get("real") and m.get("alias")
    }
    project.status = ProjectStatus.anonymizing
    project_manager.save_project(project)
    return _project_dict(project)


# ─── POST /api/projects/{id}/generate ─────────────────────────────────────────


@router.post("/api/projects/{project_id}/generate")
async def start_generation(
    project_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
) -> dict:
    """Launch generation in a background task."""
    project = _require_project(project_id, user)

    if project.status == ProjectStatus.generating:
        raise HTTPException(409, "Génération déjà en cours")
    if project.status == ProjectStatus.completed:
        raise HTTPException(409, "Génération déjà terminée. Créez un nouveau projet pour relancer.")

    project.status = ProjectStatus.generating
    project.progress_step = "Démarrage du traitement..."
    project.progress_pct = 0
    project.error_message = None
    project.generation_started_at = datetime.now(timezone.utc).isoformat()
    project_manager.save_project(project)

    background_tasks.add_task(response_generator.run_generation, project)
    return _project_dict(project)


# ─── GET /api/projects/{id}/status ────────────────────────────────────────────


@router.get("/api/projects/{project_id}/status")
async def get_status(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Polling endpoint for generation status."""
    project = _require_project(project_id, user)
    return {
        "id": project.id,
        "status": project.status,
        "progress_step": project.progress_step,
        "progress_pct": project.progress_pct,
        "error_message": project.error_message,
    }


# ─── GET /api/projects/{id}/output ────────────────────────────────────────────


@router.get("/api/projects/{project_id}/output")
async def download_output(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> FileResponse:
    project = _require_project(project_id, user)
    if project.status != ProjectStatus.completed:
        raise HTTPException(400, "Document pas encore disponible")

    output_path = project_manager.get_output_path(project.id, project.format)
    if not output_path.exists():
        raise HTTPException(404, "Fichier de sortie introuvable")

    media_types = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    return FileResponse(
        str(output_path),
        media_type=media_types.get(project.format, "application/octet-stream"),
        filename=f"PAS_rempli_{project_id}.{project.format}",
    )


# ─── GET /api/projects/{id}/attention ─────────────────────────────────────────


@router.get("/api/projects/{project_id}/attention")
async def download_attention(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> FileResponse:
    project = _require_project(project_id, user)
    if project.status != ProjectStatus.completed:
        raise HTTPException(400, "Points d'attention pas encore disponibles")

    attention_path = project_manager.get_attention_path(project.id)
    if not attention_path.exists():
        raise HTTPException(404, "Fichier points d'attention introuvable")

    return FileResponse(
        str(attention_path),
        media_type="text/markdown; charset=utf-8",
        filename=f"points_attention_{project_id}.md",
    )


# ─── DELETE /api/projects/{id} ────────────────────────────────────────────────


@router.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Delete a project and all its associated data."""
    _require_project(project_id, user)
    project_manager.delete_project(project_id)
    return {"deleted": project_id}


# ─── POST /api/projects/{id}/corrections ──────────────────────────────────────


@router.post("/api/projects/{project_id}/corrections")
async def upload_correction(
    project_id: str,
    file: UploadFile,
    user: dict = Depends(get_current_user),
) -> dict:
    project = _require_project(project_id, user)
    if project.status != ProjectStatus.completed:
        raise HTTPException(400, "Le projet doit être complété avant de soumettre une correction")

    file_bytes = await file.read()
    corrections_dir = project_manager._project_dir(project.id) / "corrections"
    corrections_dir.mkdir(exist_ok=True)
    v = project.corrections_count + 1
    (corrections_dir / f"v{v}.{project.format}").write_bytes(file_bytes)

    project.corrections_count += 1
    project_manager.save_project(project)
    return {"message": "Correction enregistrée", "version": v}
