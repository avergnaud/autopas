"""Pydantic models for projects and document structures."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ProjectStatus(str, Enum):
    created = "created"
    structure_detected = "structure_detected"
    cadrage = "cadrage"
    anonymizing = "anonymizing"
    generating = "generating"
    completed = "completed"
    error = "error"


class SheetStructure(BaseModel):
    name: str
    has_questions: bool = True
    id_column: str | None = None
    question_column: str = "A"
    response_columns: list[str] = []
    header_row: int = 1
    first_data_row: int = 2


class DocumentStructure(BaseModel):
    format: str  # "xlsx" or "docx"
    sheets: list[SheetStructure] | None = None  # xlsx only
    pattern: str | None = None               # docx only
    response_marker: str | None = None       # docx only


class Project(BaseModel):
    id: str
    created_at: str
    updated_at: str
    user_email: str
    status: ProjectStatus = ProjectStatus.created
    original_filename: str
    format: str  # "xlsx" or "docx"
    structure: DocumentStructure | None = None
    cadrage: dict[str, Any] = {}
    anonymization: dict[str, str] = {}  # {real_word: alias}
    verbosity_level: int = 2
    claude_model: str = ""
    reference_files_used: list[str] = []
    generation_started_at: str | None = None
    generation_completed_at: str | None = None
    progress_step: str = ""
    progress_pct: int = 0
    error_message: str | None = None
    corrections_count: int = 0
