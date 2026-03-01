"""Orchestration du pipeline complet de génération des réponses."""
from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime, timezone

from app.config import get_config
from app.models.project import Project, ProjectStatus
from app.services import claude_client, reference_selector
from app.services import parser_xlsx, parser_docx
from app.services.anonymizer import Anonymizer
from app.services.project_manager import (
    create_working_copy,
    get_attention_path,
    get_output_path,
    get_working_path,
    save_project,
    update_status,
)

logger = logging.getLogger(__name__)


def _format_cadrage(cadrage: dict) -> str:
    lines = ["Contexte de la prestation :"]
    for key, value in cadrage.items():
        lines.append(f"  - {key} : {value}")
    return "\n".join(lines)


def _format_with_responses(questions: list[dict], responses: list[dict]) -> str:
    resp_map = {r["question_id"]: r["response"] for r in responses}
    lines = []
    for q in questions:
        lines.append(f"ID: {q['id']}")
        lines.append(f"Question: {q['question']}")
        lines.append(f"Réponse: {resp_map.get(q['id'], '[non rempli]')}")
        lines.append("")
    return "\n".join(lines)


def _format_attention_markdown(attention_points: list[dict]) -> str:
    lines = ["# Points d'attention\n"]
    for i, point in enumerate(attention_points, 1):
        category = point.get("category", "")
        q_id = point.get("question_id", "")
        description = point.get("description", "")
        recommendation = point.get("recommendation", "")
        lines.append(f"## {i}. [{category}] {q_id}\n")
        lines.append(f"{description}\n")
        lines.append(f"**Recommandation :** {recommendation}\n")
    return "\n".join(lines)


def run_generation(project: Project) -> None:
    """
    Full generation pipeline. Called as a FastAPI background task.
    Updates project status and progress_pct throughout.
    """
    config = get_config()
    t0 = time.monotonic()
    logger.info("[GEN %s] Pipeline démarré (format=%s)", project.id, project.format)

    try:
        # 1 — Working copy
        t = time.monotonic()
        update_status(project, ProjectStatus.generating, "Création de la copie de travail…", 5)
        working_path = create_working_copy(project)
        logger.info("[GEN %s] Étape 1 — copie de travail : %.1fs", project.id, time.monotonic() - t)

        # 1b — Delete sheets excluded by the user (xlsx only)
        if project.format == "xlsx" and project.structure and project.structure.sheets:
            t = time.monotonic()
            sheet_names_to_keep = [s.name for s in project.structure.sheets]
            parser_xlsx.delete_unlisted_sheets(working_path, sheet_names_to_keep)
            logger.info(
                "[GEN %s] Étape 1b — onglets conservés : %s (%.1fs)",
                project.id, sheet_names_to_keep, time.monotonic() - t,
            )

        # 2 — Anonymize working copy
        t = time.monotonic()
        update_status(project, ProjectStatus.generating, "Anonymisation du document…", 15)
        anonymizer = Anonymizer(project.anonymization) if project.anonymization else None
        if anonymizer:
            logger.info("[GEN %s] Étape 2 — anonymisation (%d règles)…", project.id, len(project.anonymization))
            if project.format == "xlsx":
                parser_xlsx.apply_anonymization(working_path, anonymizer)
            else:
                parser_docx.apply_anonymization(working_path, anonymizer)
            logger.info("[GEN %s] Étape 2 — anonymisation terminée : %.1fs", project.id, time.monotonic() - t)
        else:
            logger.info("[GEN %s] Étape 2 — pas d'anonymisation (aucune règle)", project.id)

        # 3 — Extract questions
        t = time.monotonic()
        update_status(project, ProjectStatus.generating, "Extraction des questions…", 25)
        structure = project.structure
        if project.format == "xlsx":
            questions = parser_xlsx.extract_questions(working_path, structure)
            questionnaire_text = parser_xlsx.format_questionnaire_for_claude(questions)
        else:
            questions = parser_docx.extract_questions(working_path, structure)
            questionnaire_text = parser_docx.format_questionnaire_for_claude(questions)
        logger.info(
            "[GEN %s] Étape 3 — %d questions extraites : %.1fs",
            project.id, len(questions), time.monotonic() - t,
        )
        update_status(
            project, ProjectStatus.generating,
            f"Questions extraites : {len(questions)} question(s)…", 30,
        )

        # 4 — Select reference files
        t = time.monotonic()
        update_status(project, ProjectStatus.generating, "Sélection des fichiers de référence…", 35)
        max_files = config.get("reference", {}).get("max_files", 3)
        refs = reference_selector.select_references(project.cadrage, max_files=max_files)
        reference_contents = [content for _, content, _ in refs]
        project.reference_files_used = [fpath for fpath, _, _ in refs]
        save_project(project)
        logger.info(
            "[GEN %s] Étape 4 — %d fichier(s) de référence sélectionné(s) : %.1fs",
            project.id, len(refs), time.monotonic() - t,
        )

        # 5 — Generate responses via Claude
        t = time.monotonic()
        update_status(
            project, ProjectStatus.generating,
            f"Appel Claude — génération des réponses ({len(questions)} questions)…", 50,
        )
        logger.info(
            "[GEN %s] Étape 5 — appel Claude (génération réponses, %d questions, %d références)…",
            project.id, len(questions), len(refs),
        )
        cadrage_text = _format_cadrage(project.cadrage)
        v_level = str(project.verbosity_level)
        v_conf = config.get("verbosity", {}).get("levels", {}).get(v_level, {})
        verbosity_text = (
            f"Niveau {v_level} — {v_conf.get('label', '')} "
            f"({v_conf.get('max_words', 100)} mots max par réponse)"
        )
        responses = claude_client.generate_responses(
            cadrage_context=cadrage_text,
            verbosity_text=verbosity_text,
            questionnaire_content=questionnaire_text,
            reference_contents=reference_contents,
        )
        logger.info(
            "[GEN %s] Étape 5 — %d réponses générées : %.1fs",
            project.id, len(responses), time.monotonic() - t,
        )

        # 6 — Write responses into output document
        t = time.monotonic()
        update_status(project, ProjectStatus.generating, "Écriture des réponses dans le document…", 70)
        output_path = get_output_path(project.id, project.format)
        shutil.copy2(working_path, output_path)
        if project.format == "xlsx":
            parser_xlsx.write_responses(output_path, responses, structure)
        else:
            parser_docx.write_responses(output_path, responses, structure)
        logger.info("[GEN %s] Étape 6 — écriture document : %.1fs", project.id, time.monotonic() - t)

        # 7 — Deanonymize output
        if anonymizer:
            t = time.monotonic()
            update_status(project, ProjectStatus.generating, "Dé-anonymisation du document…", 80)
            if project.format == "xlsx":
                parser_xlsx.apply_deanonymization(output_path, anonymizer)
            else:
                parser_docx.apply_deanonymization(output_path, anonymizer)
            logger.info("[GEN %s] Étape 7 — dé-anonymisation : %.1fs", project.id, time.monotonic() - t)

        # 8 — Generate attention points
        t = time.monotonic()
        update_status(project, ProjectStatus.generating, "Appel Claude — points d'attention…", 88)
        logger.info("[GEN %s] Étape 8 — appel Claude (points d'attention)…", project.id)
        filled_text = _format_with_responses(questions, responses)
        attention_points = claude_client.generate_attention_points(
            cadrage_context=cadrage_text,
            questionnaire_with_responses=filled_text,
        )
        logger.info(
            "[GEN %s] Étape 8 — %d points d'attention générés : %.1fs",
            project.id, len(attention_points), time.monotonic() - t,
        )

        # 9 — Save attention markdown
        t = time.monotonic()
        update_status(project, ProjectStatus.generating, "Finalisation…", 95)
        attention_path = get_attention_path(project.id)
        attention_path.write_text(_format_attention_markdown(attention_points), encoding="utf-8")
        logger.info("[GEN %s] Étape 9 — finalisation : %.1fs", project.id, time.monotonic() - t)

        # Done
        project.status = ProjectStatus.completed
        project.progress_step = "Terminé"
        project.progress_pct = 100
        project.generation_completed_at = datetime.now(timezone.utc).isoformat()
        save_project(project)
        logger.info(
            "[GEN %s] Pipeline terminé en %.1fs au total",
            project.id, time.monotonic() - t0,
        )

    except Exception as exc:
        logger.exception("[GEN %s] Pipeline échoué après %.1fs : %s", project.id, time.monotonic() - t0, exc)
        project.status = ProjectStatus.error
        project.error_message = str(exc)
        project.progress_step = f"Erreur : {exc}"
        save_project(project)
