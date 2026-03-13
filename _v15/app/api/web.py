"""PAS Assistant — Web API endpoints."""

import json
import logging
import shutil
import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from openpyxl import load_workbook
from openpyxl.workbook.defined_name import DefinedName
from pydantic import BaseModel

from app.auth.session import get_current_user
from app.config import BASE_DIR, get_config
from app.services.structure_analyzer import detect_xlsx_structure
from app.services import project_manager
from app.services.reference_selector import score_corpus_entries
from app.services.response_generator import run_generation
from app.services.anonymizer import (
    anonymize_docx,
    anonymize_xlsx,
    extract_metadata,
    extract_metadata_docx,
    safe_local_defined_names,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

PROJECTS_DIR = BASE_DIR / "data" / "projects"
CORPUS_DIR = BASE_DIR / "data" / "corpus"
POLICIES_DIR = BASE_DIR / "data" / "policies"


# ---------------------------------------------------------------------------
# Upload — POST /api/projects
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/contract")
async def upload_project_contract(
    project_id: str,
    file: UploadFile,
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload an optional contract (.docx) associated with a project.

    The file is saved as contract_original.docx. It will be anonymized later
    when POST /api/projects/{id}/anonymize is called.

    Args:
        project_id: UUID of the project.
        file: The uploaded .docx contract file.
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "ok", "filename": ...}
    """
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers .docx sont acceptés.")

    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    content = await file.read()
    (project_dir / "contract_original.docx").write_bytes(content)

    logger.info(
        "Contract uploaded for project %s by %s — %s (%d bytes)",
        project_id, user["email"], file.filename, len(content),
    )
    return {"status": "ok", "filename": file.filename}


@router.post("/projects")
async def upload_file(
    file: UploadFile,
    user: dict = Depends(get_current_user),
) -> dict:
    """Create a new project by uploading an xlsx questionnaire.

    Args:
        file: The uploaded xlsx file.
        user: The authenticated user (injected by dependency).

    Returns:
        project_id, status, and download_url for the working copy.
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

    proj = project_manager.create_project(project_id, file.filename, user["email"])

    logger.info(
        "Project %s created by %s — original file: %s (%d bytes)",
        project_id,
        user["email"],
        file.filename,
        len(content),
    )

    return {
        "project_id": project_id,
        "status": proj["status"],
        "filename": file.filename,
        "download_url": f"/api/projects/{project_id}/working",
    }


# ---------------------------------------------------------------------------
# List / detail projects
# ---------------------------------------------------------------------------


@router.get("/projects")
async def list_projects(user: dict = Depends(get_current_user)) -> dict:
    """List all projects belonging to the current user.

    Args:
        user: The authenticated user (injected by dependency).

    Returns:
        List of project dicts.
    """
    projects = project_manager.list_projects(user["email"])
    return {"projects": projects}


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return the details of a project.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).

    Returns:
        The project dict.
    """
    try:
        proj = project_manager.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    if proj.get("user_email") != user["email"]:
        raise HTTPException(status_code=403, detail="Accès refusé.")

    return proj


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

    wb = load_workbook(working_path, keep_links=False, rich_text=False)

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

    # Merge contract metadata if a contract was uploaded
    contract_path = PROJECTS_DIR / project_id / "contract_original.docx"
    if contract_path.exists():
        contract_meta = await anyio.to_thread.run_sync(lambda: extract_metadata_docx(contract_path))
        meta = {**meta, **{f"contract_{k}": v for k, v in contract_meta.items()}}

    # Deduplicate while preserving order; skip generic app names
    _generic = {"Microsoft Excel", "Microsoft Office Excel", "Microsoft Word"}
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

    # Anonymize contract if present
    contract_original = PROJECTS_DIR / project_id / "contract_original.docx"
    if contract_original.exists():
        contract_anonymized = PROJECTS_DIR / project_id / "contract_anonymized.docx"
        await anyio.to_thread.run_sync(
            lambda: anonymize_docx(contract_original, contract_anonymized, raw_mapping)
        )
        logger.info("Project %s — contract anonymized (%d keywords)", project_id, len(raw_mapping))

    try:
        project_manager.update_project(
            project_id,
            status="anonymizing",
            anonymization={"mappings": mapping},
        )
    except FileNotFoundError:
        pass  # project.json may not exist for older projects

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


@router.get("/questions")
async def get_questions(user: dict = Depends(get_current_user)) -> dict:
    """Return the list of cadrage questions from config.

    Args:
        user: The authenticated user (injected by dependency).

    Returns:
        List of question dicts (text, options, type, multi, condition, key).
    """
    config = get_config()
    return {"questions": config["questions"]}


# ---------------------------------------------------------------------------
# Corpus — upload already-filled questionnaire
# ---------------------------------------------------------------------------


@router.post("/corpus/{corpus_id}/contract")
async def upload_corpus_contract(
    corpus_id: str,
    file: UploadFile,
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload an optional contract (.docx) associated with a corpus entry.

    The file is saved as contract_original.docx. It will be anonymized later
    when POST /api/corpus/{id}/anonymize is called.

    Args:
        corpus_id: UUID of the corpus entry.
        file: The uploaded .docx contract file.
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "ok", "filename": ...}
    """
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers .docx sont acceptés.")

    corpus_dir = CORPUS_DIR / corpus_id
    if not corpus_dir.exists():
        raise HTTPException(status_code=404, detail="Entrée corpus introuvable.")

    content = await file.read()
    (corpus_dir / "contract_original.docx").write_bytes(content)

    logger.info(
        "Contract uploaded for corpus %s by %s — %s (%d bytes)",
        corpus_id, user["email"], file.filename, len(content),
    )
    return {"status": "ok", "filename": file.filename}


@router.post("/corpus")
async def upload_corpus(
    file: UploadFile,
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload an already-filled questionnaire to the corpus.

    Args:
        file: The uploaded xlsx or docx file.
        user: The authenticated user (injected by dependency).

    Returns:
        corpus_id and original filename.
    """
    if not file.filename or not Path(file.filename).suffix.lower() in {".xlsx", ".docx"}:
        raise HTTPException(status_code=400, detail="Seuls les fichiers .xlsx et .docx sont acceptés.")

    corpus_id = str(uuid.uuid4())
    corpus_dir = CORPUS_DIR / corpus_id
    corpus_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix.lower()
    original_path = corpus_dir / f"original{ext}"

    content = await file.read()
    original_path.write_bytes(content)

    meta: dict = {"filename": file.filename, "format": ext.lstrip(".")}
    (corpus_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(
        "Corpus %s created by %s — %s (%d bytes)",
        corpus_id, user["email"], file.filename, len(content),
    )
    return {"corpus_id": corpus_id, "filename": file.filename}


class StructureModel(BaseModel):
    """Confirmed questionnaire structure (one xlsx sheet)."""

    selected_sheet: str | None = None
    header_row: int = 1
    first_data_row: int = 2
    col_id: str | None = None
    col_question: str | None = None
    col_response: str | None = None
    col_status: str | None = None
    col_evidence: str | None = None


# ---------------------------------------------------------------------------
# Structure detection — projects
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/detect-structure")
async def detect_project_structure(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Detect the questionnaire structure in the anonymized xlsx using Claude.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).

    Returns:
        Detected structure dict (sheet, columns, rows).
    """
    anonymized_path = PROJECTS_DIR / project_id / "anonymized.xlsx"
    if not anonymized_path.exists():
        raise HTTPException(status_code=404, detail="Fichier anonymisé introuvable. Lancez d'abord l'anonymisation.")

    try:
        result = await anyio.to_thread.run_sync(lambda: detect_xlsx_structure(anonymized_path))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    logger.info("Structure detected for project %s by %s", project_id, user["email"])
    return result


@router.post("/projects/{project_id}/structure")
async def save_project_structure(
    project_id: str,
    body: StructureModel,
    user: dict = Depends(get_current_user),
) -> dict:
    """Save the confirmed questionnaire structure for a project.

    Args:
        project_id: UUID of the project.
        body: Confirmed structure fields.
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "ok"}.
    """
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    structure_path = project_dir / "structure.json"
    structure_data = body.model_dump()
    structure_path.write_text(
        json.dumps(structure_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    try:
        project_manager.update_project(project_id, structure=structure_data)
    except FileNotFoundError:
        pass  # project.json may not exist for older projects

    logger.info("Structure saved for project %s by %s", project_id, user["email"])
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Structure detection — corpus
# ---------------------------------------------------------------------------


@router.post("/corpus/{corpus_id}/detect-structure")
async def detect_corpus_structure(
    corpus_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Detect the questionnaire structure in the anonymized corpus xlsx using Claude.

    Args:
        corpus_id: UUID of the corpus entry.
        user: The authenticated user (injected by dependency).

    Returns:
        Detected structure dict, or {"skipped": true} for non-xlsx files.
    """
    corpus_dir = CORPUS_DIR / corpus_id
    meta_path = corpus_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Entrée corpus introuvable.")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fmt = meta.get("format", "xlsx")

    if fmt != "xlsx":
        return {"skipped": True, "reason": "Détection automatique disponible uniquement pour les fichiers xlsx."}

    anonymized_path = corpus_dir / f"anonymized.{fmt}"
    if not anonymized_path.exists():
        raise HTTPException(status_code=404, detail="Fichier anonymisé introuvable. Lancez d'abord l'anonymisation.")

    try:
        result = await anyio.to_thread.run_sync(lambda: detect_xlsx_structure(anonymized_path))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    logger.info("Structure detected for corpus %s by %s", corpus_id, user["email"])
    return result


@router.post("/corpus/{corpus_id}/structure")
async def save_corpus_structure(
    corpus_id: str,
    body: StructureModel,
    user: dict = Depends(get_current_user),
) -> dict:
    """Save the confirmed questionnaire structure for a corpus entry.

    Args:
        corpus_id: UUID of the corpus entry.
        body: Confirmed structure fields.
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "ok"}.
    """
    corpus_dir = CORPUS_DIR / corpus_id
    if not corpus_dir.exists():
        raise HTTPException(status_code=404, detail="Entrée corpus introuvable.")

    structure_path = corpus_dir / "structure.json"
    structure_path.write_text(
        json.dumps(body.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Structure saved for corpus %s by %s", corpus_id, user["email"])
    return {"status": "ok"}


class CorpusMetadataRequest(BaseModel):
    """Request body for POST /api/corpus/{id}/metadata."""

    answers: dict
    date_remplissage: str = ""
    tags: list[str] = []


def _resolve_type_prestation(answers: dict) -> str:
    """Combine type_prestation_base and type_prestation_detail into a single value."""
    if answers.get("pas_niveau_entreprise") == "Oui":
        return "Entreprise"
    base = answers.get("type_prestation_base", "")
    if base == "Assistance Technique":
        return "AT"
    return answers.get("type_prestation_detail", base)


@router.post("/corpus/{corpus_id}/metadata")
async def save_corpus_metadata(
    corpus_id: str,
    body: CorpusMetadataRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    """Save cadrage answers as corpus metadata.

    Args:
        corpus_id: UUID of the corpus entry.
        body: Wizard answers + date + tags.
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "ok"}.
    """
    corpus_dir = CORPUS_DIR / corpus_id
    meta_path = corpus_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Entrée corpus introuvable.")

    existing = json.loads(meta_path.read_text(encoding="utf-8"))
    a = body.answers

    lieu = a.get("lieu_travail", [])
    if isinstance(lieu, str):
        lieu = [lieu]

    pas_entreprise = a.get("pas_niveau_entreprise") == "Oui"

    meta = {
        **existing,
        "pas_niveau_entreprise": pas_entreprise,
        "type_prestation": _resolve_type_prestation(a),
        "activites": a.get("activites", ""),
        "secteur_client": a.get("secteur_client", ""),
        "date_remplissage": body.date_remplissage,
        "tags_supplementaires": body.tags,
    }

    if not pas_entreprise:
        meta.update({
            "nb_etp": int(a["nb_etp"]) if a.get("nb_etp") else None,
            "expertise_atlassian": a.get("expertise_atlassian") == "Oui",
            "hebergement_donnees": a.get("hebergement_donnees", ""),
            "cloud_provider": a.get("cloud_provider", ""),
            "sous_traitance_rgpd": a.get("sous_traitance_rgpd") == "Oui",
            "lieu_travail": lieu,
            "agences": a.get("agences", ""),
            "poste_travail": a.get("poste_travail", ""),
            "connexion_distante": a.get("connexion_distante", ""),
        })

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Corpus %s metadata saved by %s", corpus_id, user["email"])
    return {"status": "ok"}


@router.get("/corpus")
async def list_corpus(user: dict = Depends(get_current_user)) -> dict:
    """List all corpus entries with their metadata.

    Args:
        user: The authenticated user (injected by dependency).

    Returns:
        List of corpus entries.
    """
    if not CORPUS_DIR.exists():
        return {"entries": []}

    entries = []
    for d in sorted(CORPUS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            entries.append({
                "corpus_id": d.name,
                "has_contract": (d / "contract_original.docx").exists(),
                **meta,
            })

    return {"entries": entries}


@router.get("/corpus/{corpus_id}/anon-suggestions")
async def corpus_anon_suggestions(
    corpus_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Extract metadata suggestions from a corpus file for the anonymization step.

    Args:
        corpus_id: UUID of the corpus entry.
        user: The authenticated user (injected by dependency).

    Returns:
        metadata dict and deduplicated suggestions list.
    """
    corpus_dir = CORPUS_DIR / corpus_id
    meta_path = corpus_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Entrée corpus introuvable.")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fmt = meta.get("format", "xlsx")
    original_path = corpus_dir / f"original.{fmt}"
    if not original_path.exists():
        raise HTTPException(status_code=404, detail="Fichier original introuvable.")

    if fmt == "xlsx":
        file_meta = await anyio.to_thread.run_sync(lambda: extract_metadata(original_path))
    else:
        file_meta = await anyio.to_thread.run_sync(lambda: extract_metadata_docx(original_path))

    # Merge contract metadata if a contract was uploaded
    contract_path = corpus_dir / "contract_original.docx"
    if contract_path.exists():
        contract_meta = await anyio.to_thread.run_sync(lambda: extract_metadata_docx(contract_path))
        file_meta = {**file_meta, **{f"contract_{k}": v for k, v in contract_meta.items()}}

    _generic = {"Microsoft Excel", "Microsoft Office Excel", "Microsoft Word"}
    seen: set[str] = set()
    suggestions: list[str] = []
    for v in file_meta.values():
        if v and v not in seen and v not in _generic:
            seen.add(v)
            suggestions.append(v)

    return {"metadata": file_meta, "suggestions": suggestions}


@router.post("/corpus/{corpus_id}/anonymize")
async def corpus_anonymize(
    corpus_id: str,
    body: AnonymizeRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    """Anonymize a corpus file: replace keywords and strip file metadata.

    Saves anonymized.{ext} and anonymized_map.json in the corpus directory.

    Args:
        corpus_id: UUID of the corpus entry.
        body: JSON body with a list of {original, replacement} pairs.
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "ok", "mapping": {...}}.
    """
    corpus_dir = CORPUS_DIR / corpus_id
    meta_path = corpus_dir / "metadata.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Entrée corpus introuvable.")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fmt = meta.get("format", "xlsx")
    original_path = corpus_dir / f"original.{fmt}"
    anonymized_path = corpus_dir / f"anonymized.{fmt}"

    raw_mapping = {
        pair.original.strip(): pair.replacement.strip()
        for pair in body.keywords
        if pair.original.strip()
    }
    if not raw_mapping:
        raise HTTPException(status_code=400, detail="Aucun mot-clé fourni.")

    if fmt == "xlsx":
        mapping = await anyio.to_thread.run_sync(
            lambda: anonymize_xlsx(original_path, anonymized_path, raw_mapping)
        )
    else:
        mapping = await anyio.to_thread.run_sync(
            lambda: anonymize_docx(original_path, anonymized_path, raw_mapping)
        )

    map_path = corpus_dir / "anonymized_map.json"
    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    # Anonymize contract if present
    contract_original = corpus_dir / "contract_original.docx"
    if contract_original.exists():
        contract_anonymized = corpus_dir / "contract_anonymized.docx"
        await anyio.to_thread.run_sync(
            lambda: anonymize_docx(contract_original, contract_anonymized, raw_mapping)
        )
        logger.info("Corpus %s — contract anonymized (%d keywords)", corpus_id, len(raw_mapping))

    logger.info(
        "Corpus %s anonymized by %s — %d keywords", corpus_id, user["email"], len(mapping)
    )
    return {"status": "ok", "mapping": mapping}


@router.delete("/corpus/{corpus_id}")
async def delete_corpus(
    corpus_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Delete a corpus entry (file + metadata).

    Args:
        corpus_id: UUID of the corpus entry.
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "deleted"}.
    """
    corpus_dir = CORPUS_DIR / corpus_id
    if not corpus_dir.exists():
        raise HTTPException(status_code=404, detail="Entrée corpus introuvable.")

    shutil.rmtree(corpus_dir)
    logger.info("Corpus %s deleted by %s", corpus_id, user["email"])
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Politiques sécurité — unique fichier Markdown
# ---------------------------------------------------------------------------

_POLICY_FILE = POLICIES_DIR / "politiques.md"


@router.post("/policies")
async def upload_policy(
    file: UploadFile,
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload (or replace) the unique security policy Markdown file.

    Args:
        file: The uploaded .md file.
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "ok", "filename": ..., "size": ...}.
    """
    if not file.filename or not file.filename.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers .md sont acceptés.")

    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    _POLICY_FILE.write_bytes(content)

    logger.info(
        "Policy file uploaded by %s — %s (%d bytes)",
        user["email"], file.filename, len(content),
    )
    return {"status": "ok", "filename": file.filename, "size": len(content)}


@router.get("/policies")
async def get_policy(user: dict = Depends(get_current_user)) -> dict:
    """Return info about the current policy Markdown file.

    Args:
        user: The authenticated user (injected by dependency).

    Returns:
        {"exists": bool, "size": int, "updated_at": str} — updated_at is ISO 8601 if file exists.
    """
    if not _POLICY_FILE.exists():
        return {"exists": False}

    stat = _POLICY_FILE.stat()
    import datetime
    updated_at = datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.timezone.utc).isoformat()
    return {"exists": True, "size": stat.st_size, "updated_at": updated_at}


@router.delete("/policies")
async def delete_policy(user: dict = Depends(get_current_user)) -> dict:
    """Delete the policy Markdown file.

    Args:
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "deleted"}.
    """
    if not _POLICY_FILE.exists():
        raise HTTPException(status_code=404, detail="Aucune politique sécurité trouvée.")

    _POLICY_FILE.unlink()
    logger.info("Policy file deleted by %s", user["email"])
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Cadrage — GET/POST /api/projects/{project_id}/cadrage
# ---------------------------------------------------------------------------


class CadrageBody(BaseModel):
    answers: dict


@router.get("/projects/{project_id}/cadrage")
async def get_cadrage(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return saved cadrage answers for a project.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).

    Returns:
        {"answers": dict | null}
    """
    try:
        proj = project_manager.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Projet introuvable.")
    return {"answers": proj.get("cadrage")}


@router.post("/projects/{project_id}/cadrage")
async def save_cadrage(
    project_id: str,
    body: CadrageBody,
    user: dict = Depends(get_current_user),
) -> dict:
    """Save cadrage answers and advance project status to cadrage_done.

    Args:
        project_id: UUID of the project.
        body: {"answers": dict}
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "cadrage_done"}
    """
    try:
        project_manager.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    project_manager.update_project(project_id, cadrage=body.answers, status="cadrage_done")
    logger.info("Project %s cadrage saved (%d answers)", project_id, len(body.answers))
    return {"status": "cadrage_done"}


# ---------------------------------------------------------------------------
# Corpus selection — GET/POST /api/projects/{project_id}/corpus-selection
# ---------------------------------------------------------------------------


class CorpusSelectionBody(BaseModel):
    """Request body for POST /api/projects/{id}/corpus-selection."""

    selected_corpus_ids: list[str]


@router.get("/projects/{project_id}/corpus-selection")
async def get_corpus_selection(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return corpus entries scored by relevance to the project's cadrage.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).

    Returns:
        {"entries": [...]} sorted by score descending.
    """
    try:
        proj = project_manager.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    cadrage = proj.get("cadrage")
    if not cadrage:
        raise HTTPException(status_code=400, detail="Cadrage non effectué.")

    if not CORPUS_DIR.exists():
        return {"entries": []}

    entries = []
    for d in sorted(CORPUS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            entries.append({"corpus_id": d.name, **meta})

    scored = score_corpus_entries(cadrage, entries)

    project_is_atlassian = cadrage.get("expertise_atlassian") == "Oui"

    # Keep only fields needed by the frontend
    result = [
        {
            "corpus_id": e["corpus_id"],
            "filename": e.get("filename", e["corpus_id"]),
            "type_prestation": e.get("type_prestation", ""),
            "nb_etp": e.get("nb_etp"),
            "date_remplissage": e.get("date_remplissage", ""),
            "expertise_atlassian": e.get("expertise_atlassian"),
            "poste_travail": e.get("poste_travail", ""),
            "score": e["score"],
        }
        for e in scored
    ]
    return {"entries": result, "project_is_atlassian": project_is_atlassian}


@router.post("/projects/{project_id}/corpus-selection")
async def save_corpus_selection(
    project_id: str,
    body: CorpusSelectionBody,
    user: dict = Depends(get_current_user),
) -> dict:
    """Save the selected corpus ids for a project.

    Args:
        project_id: UUID of the project.
        body: {"selected_corpus_ids": list[str]}
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "corpus_selected", "count": N}
    """
    try:
        project_manager.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    if not body.selected_corpus_ids:
        raise HTTPException(status_code=400, detail="Sélectionnez au moins une entrée.")

    for cid in body.selected_corpus_ids:
        if not (CORPUS_DIR / cid).is_dir():
            raise HTTPException(status_code=400, detail=f"Entrée corpus introuvable : {cid}")

    project_manager.update_project(
        project_id,
        selected_corpus=body.selected_corpus_ids,
        status="corpus_selected",
    )
    logger.info(
        "Project %s corpus selection saved (%d ids) by %s",
        project_id,
        len(body.selected_corpus_ids),
        user["email"],
    )
    return {"status": "corpus_selected", "count": len(body.selected_corpus_ids)}


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


# ---------------------------------------------------------------------------
# Generation — POST /api/projects/{project_id}/generate
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/generate", status_code=202)
async def start_generation(
    project_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
) -> dict:
    """Trigger response generation as a background task.

    Allowed from statuses: corpus_selected, completed, error (allows re-generation).

    Args:
        project_id: UUID of the project.
        background_tasks: FastAPI background task queue.
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": "generating"}
    """
    try:
        proj = project_manager.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    if proj.get("user_email") != user["email"]:
        raise HTTPException(status_code=403, detail="Accès refusé.")

    allowed = {"corpus_selected", "completed", "error"}
    if proj.get("status") not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Le projet n'est pas dans un état permettant la génération.",
        )

    project_manager.update_project(
        project_id,
        status="generating",
        progress_step="Démarrage...",
        error_message=None,
    )
    background_tasks.add_task(run_generation, project_id)
    logger.info("Generation started for project %s by %s", project_id, user["email"])
    return {"status": "generating"}


# ---------------------------------------------------------------------------
# Status polling — GET /api/projects/{project_id}/status
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/status")
async def get_project_status(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Return the current status of a project (for polling during generation).

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).

    Returns:
        {"status": str, "progress_step": str | None, "error_message": str | None}
    """
    try:
        proj = project_manager.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    if proj.get("user_email") != user["email"]:
        raise HTTPException(status_code=403, detail="Accès refusé.")

    return {
        "status": proj.get("status"),
        "progress_step": proj.get("progress_step"),
        "error_message": proj.get("error_message"),
    }


# ---------------------------------------------------------------------------
# Download output — GET /api/projects/{project_id}/output
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/output")
async def download_output(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> FileResponse:
    """Download the generated and de-anonymized xlsx output.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).
    """
    try:
        proj = project_manager.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    if proj.get("user_email") != user["email"]:
        raise HTTPException(status_code=403, detail="Accès refusé.")

    output_path = PROJECTS_DIR / project_id / "output.xlsx"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Résultat non disponible. Lancez d'abord la génération.")

    filename = f"PAS_rempli_{project_id[:8]}.xlsx"
    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


# ---------------------------------------------------------------------------
# Download attention — GET /api/projects/{project_id}/attention
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/attention")
async def download_attention(
    project_id: str,
    user: dict = Depends(get_current_user),
) -> FileResponse:
    """Download the attention points Markdown file.

    Args:
        project_id: UUID of the project.
        user: The authenticated user (injected by dependency).
    """
    try:
        proj = project_manager.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Projet introuvable.")

    if proj.get("user_email") != user["email"]:
        raise HTTPException(status_code=403, detail="Accès refusé.")

    attention_path = PROJECTS_DIR / project_id / "attention.md"
    if not attention_path.exists():
        raise HTTPException(status_code=404, detail="Points d'attention non disponibles.")

    return FileResponse(
        path=str(attention_path),
        media_type="text/markdown; charset=utf-8",
        filename="points_attention.md",
    )
