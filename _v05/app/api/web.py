"""PAS Assistant — Web API endpoints."""

import logging
import re
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from openpyxl import load_workbook
from openpyxl.workbook.defined_name import DefinedName

from app.auth.session import get_current_user
from app.config import BASE_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

PROJECTS_DIR = BASE_DIR / "data" / "projects"


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


_XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _safe_local_defined_names(xlsx_path: Path) -> list[tuple[str, str, int | None]]:
    """Extract safe, local defined names directly from workbook.xml.

    openpyxl's DefinedNameDict is keyed by name only, so when the same name
    appears twice in the XML (once sheet-scoped with localSheetId, once as a
    broken workbook-level external ref), the external #REF! entry silently
    overwrites the valid local one.  We read the raw XML first, before openpyxl
    touches it, to capture the local definitions that openpyxl would lose.

    Returns a list of (name, attr_text, local_sheet_id) for names that:
    - reference cells inside this workbook (no [n] external-workbook notation)
    - are not already broken (#REF!)
    - are not _xlnm.* built-ins (autofilter databases, etc.)
    - are not hidden
    """
    with zipfile.ZipFile(xlsx_path) as z:
        with z.open("xl/workbook.xml") as f:
            tree = ET.parse(f)

    results = []
    for dn in tree.iter(f"{{{_XLSX_NS}}}definedName"):
        name = dn.get("name", "")
        value = dn.text or ""
        hidden = dn.get("hidden", "0") == "1"
        local_sheet_id_raw = dn.get("localSheetId")

        if name.startswith("_xlnm."):
            continue
        if hidden:
            continue
        if "#REF" in value or re.search(r"\[\d+\]", value):
            continue

        sid = int(local_sheet_id_raw) if local_sheet_id_raw is not None else None
        results.append((name, value, sid))

    return results


def _openpyxl_roundtrip(working_path: Path, roundtrip_path: Path) -> None:
    """Open working.xlsx with openpyxl and save it unchanged to roundtrip.xlsx.

    This is a synchronous function intended to be run in a thread via anyio.
    It does not modify any cell, sheet, or property — pure open/save identity.

    keep_links=False: discard external link definitions (references to other xlsx
    files). openpyxl cannot round-trip them correctly and produces broken XML that
    triggers Excel's repair dialog. Cached cell values are preserved.

    Named ranges: openpyxl serializes them from three sources (workbook/_writer.py):
    wb.defined_names, ws.defined_names, and ws.print_area / ws.print_titles.
    We clear all three to eliminate broken external-reference entries.
    We then re-inject only the safe local definitions recovered from the raw XML,
    so that data-validation dropdowns (e.g. the "Cotation" list on column F)
    continue to work in the output file.
    """
    # Step 1: capture safe local defined names from raw XML before openpyxl
    # loses them (it de-duplicates by name, keeping the broken external entry).
    safe_names = _safe_local_defined_names(working_path)

    # Step 2: load workbook, stripping external links.
    wb = load_workbook(working_path, keep_links=False)

    # Step 3: clear ALL defined names from every source to prevent broken XML.
    wb_count = len(wb.defined_names)
    wb.defined_names.clear()
    ws_count = 0
    for ws in wb.worksheets:
        ws_count += len(ws.defined_names)
        ws.defined_names.clear()
        ws.print_area = None
        ws.print_title_rows = None
        ws.print_title_cols = None

    # Step 4: re-inject only the safe local names so dropdowns keep working.
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

    This verifies that openpyxl can round-trip the file without corruption,
    before any actual transformation is applied.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).

    Returns:
        download_url for roundtrip.xlsx.
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
