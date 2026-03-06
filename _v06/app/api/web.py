"""PAS Assistant — Web API endpoints."""

import json
import logging
import shutil
import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from openpyxl import load_workbook
from openpyxl.workbook.defined_name import DefinedName
from pydantic import BaseModel

from app.auth.session import get_current_user
from app.config import BASE_DIR
from app.services.anonymizer import (
    anonymize_xlsx,
    extract_metadata,
    safe_local_defined_names,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

PROJECTS_DIR = BASE_DIR / "data" / "projects"


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_file(
    file: UploadFile,
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload an xlsx file and create a project directory with a working copy.

    Args:
        file: The uploaded xlsx file.
        user: The authenticated user (injected by dependency).

    Returns:
        project_id and download_url for the working copy.
    """
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers .xlsx sont acceptés.")

    project_id = str(uuid.uuid4())
    project_dir = PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    original_path = project_dir / "original.xlsx"
    working_path = project_dir / "working.xlsx"

    content = await file.read()
    original_path.write_bytes(content)

    shutil.copy2(original_path, working_path)

    logger.info(
        "Project %s created by %s — original file: %s (%d bytes)",
        project_id,
        user["email"],
        file.filename,
        len(content),
    )

    return {
        "project_id": project_id,
        "filename": file.filename,
        "download_url": f"/api/projects/{project_id}/working",
    }


# ---------------------------------------------------------------------------
# Download working copy
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/working")
async def download_working(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> FileResponse:
    """Download the working copy of a project.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).
    """
    working_path = PROJECTS_DIR / project_id / "working.xlsx"
    if not working_path.exists():
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    return FileResponse(
        path=str(working_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="working.xlsx",
    )


# ---------------------------------------------------------------------------
# Roundtrip (developer test — open/save with openpyxl, no changes)
# ---------------------------------------------------------------------------


def _openpyxl_roundtrip(working_path: Path, roundtrip_path: Path) -> None:
    """Open working.xlsx with openpyxl and save it unchanged to roundtrip.xlsx.

    Preserves local defined names (Excel dropdowns) using safe_local_defined_names.
    keep_links=False discards external link definitions that openpyxl cannot
    round-trip correctly.
    """
    safe_names = safe_local_defined_names(working_path)

    wb = load_workbook(working_path, keep_links=False)

    wb_count = len(wb.defined_names)
    wb.defined_names.clear()
    ws_count = 0
    for ws in wb.worksheets:
        ws_count += len(ws.defined_names)
        ws.defined_names.clear()
        ws.print_area = None
        ws.print_title_rows = None
        ws.print_title_cols = None

    for name, attr_text, local_sheet_id in safe_names:
        dn = DefinedName(name=name, attr_text=attr_text, localSheetId=local_sheet_id)
        wb.defined_names.add(dn)

    logger.info(
        "Defined names: cleared %d workbook-level + %d sheet-level, "
        "re-injected %d safe local names: %s",
        wb_count,
        ws_count,
        len(safe_names),
        [n for n, _, _ in safe_names],
    )

    wb.save(roundtrip_path)
    wb.close()


@router.post("/projects/{project_id}/roundtrip")
async def roundtrip(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Open working.xlsx with openpyxl and save it unchanged to roundtrip.xlsx.

    Verifies that openpyxl can round-trip the file without corruption before
    any actual transformation is applied.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).
    """
    working_path = PROJECTS_DIR / project_id / "working.xlsx"
    if not working_path.exists():
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    roundtrip_path = PROJECTS_DIR / project_id / "roundtrip.xlsx"

    await anyio.to_thread.run_sync(
        lambda: _openpyxl_roundtrip(working_path, roundtrip_path)
    )

    logger.info("Roundtrip done for project %s by %s", project_id, user["email"])

    return {"download_url": f"/api/projects/{project_id}/roundtrip"}


@router.get("/projects/{project_id}/roundtrip")
async def download_roundtrip(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> FileResponse:
    """Download the openpyxl round-trip result.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).
    """
    roundtrip_path = PROJECTS_DIR / project_id / "roundtrip.xlsx"
    if not roundtrip_path.exists():
        raise HTTPException(status_code=404, detail="Round-trip non effectué.")

    return FileResponse(
        path=str(roundtrip_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="roundtrip.xlsx",
    )


# ---------------------------------------------------------------------------
# Anonymization — step 1: extract metadata suggestions
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/metadata")
async def get_metadata(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Extract PII metadata from working.xlsx and return keyword suggestions.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).

    Returns:
        metadata dict and deduplicated suggestions list.
    """
    working_path = PROJECTS_DIR / project_id / "working.xlsx"
    if not working_path.exists():
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    meta = await anyio.to_thread.run_sync(lambda: extract_metadata(working_path))

    # Deduplicate while preserving order; skip generic app names
    _generic = {"Microsoft Excel", "Microsoft Office Excel"}
    seen: set[str] = set()
    suggestions: list[str] = []
    for v in meta.values():
        if v and v not in seen and v not in _generic:
            seen.add(v)
            suggestions.append(v)

    return {"metadata": meta, "suggestions": suggestions}


# ---------------------------------------------------------------------------
# Anonymization — step 2: apply keyword replacement + metadata strip
# ---------------------------------------------------------------------------


class KeywordPair(BaseModel):
    """One keyword substitution pair."""

    original: str
    replacement: str


class AnonymizeRequest(BaseModel):
    """Request body for POST /api/projects/{id}/anonymize."""

    keywords: list[KeywordPair]


@router.post("/projects/{project_id}/anonymize")
async def anonymize_project(
    project_id: str,
    body: AnonymizeRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    """Anonymize working.xlsx: replace keywords and strip file metadata.

    Saves anonymized.xlsx and anonymized_map.json in the project directory.
    The map is needed to de-anonymize Claude's output later.

    Args:
        project_id: UUID of the project.
        body: JSON body with a list of {original, replacement} pairs.
        user: The authenticated user (injected by dependency).

    Returns:
        download_url for anonymized.xlsx and the keyword→replacement mapping.
    """
    working_path = PROJECTS_DIR / project_id / "working.xlsx"
    if not working_path.exists():
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    raw_mapping = {
        pair.original.strip(): pair.replacement.strip()
        for pair in body.keywords
        if pair.original.strip()
    }
    if not raw_mapping:
        raise HTTPException(status_code=400, detail="Aucun mot-clé fourni.")

    anonymized_path = PROJECTS_DIR / project_id / "anonymized.xlsx"
    map_path = PROJECTS_DIR / project_id / "anonymized_map.json"

    mapping = await anyio.to_thread.run_sync(
        lambda: anonymize_xlsx(working_path, anonymized_path, raw_mapping)
    )

    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(
        "Project %s anonymized by %s — %d keywords",
        project_id,
        user["email"],
        len(mapping),
    )

    return {
        "download_url": f"/api/projects/{project_id}/anonymized",
        "mapping": mapping,
    }


@router.get("/projects/{project_id}/anonymized")
async def download_anonymized(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> FileResponse:
    """Download the anonymized xlsx file.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).
    """
    anonymized_path = PROJECTS_DIR / project_id / "anonymized.xlsx"
    if not anonymized_path.exists():
        raise HTTPException(status_code=404, detail="Anonymisation non effectuée.")

    return FileResponse(
        path=str(anonymized_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="anonymized.xlsx",
    )
