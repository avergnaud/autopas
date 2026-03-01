"""Client API Claude — analyse structure, génération réponses, points d'attention."""
from __future__ import annotations

import json
import logging
import re

import anthropic

from app.config import BASE_DIR, get_config

logger = logging.getLogger(__name__)

PROMPTS_DIR = BASE_DIR / "data" / "config" / "prompts"


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def _parse_json(text: str) -> dict:
    """Extract and parse JSON from Claude response, stripping markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text.strip())


def _client() -> anthropic.Anthropic:
    import os
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def analyze_structure(raw_content: str, fmt: str) -> dict:
    """Ask Claude to identify the structure of the questionnaire document."""
    config = get_config()
    system_prompt = _load_prompt("system_structure.txt")
    user_content = f"Format du document : {fmt}\n\n{raw_content}"

    message = _client().messages.create(
        model=config["claude"]["model"],
        max_tokens=2000,
        temperature=0.1,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    response_text = message.content[0].text
    logger.info("Structure analysis result: %s", response_text[:300])
    return _parse_json(response_text)


def generate_responses(
    cadrage_context: str,
    verbosity_text: str,
    questionnaire_content: str,
    reference_contents: list[str],
) -> list[dict]:
    """Generate questionnaire responses. Returns list of {question_id, response}."""
    config = get_config()
    system_prompt = _load_prompt("system_response.txt")

    content_blocks: list[dict] = [
        {"type": "text", "text": f"CONTEXTE DE CADRAGE :\n{cadrage_context}"},
        {"type": "text", "text": f"CONTRAINTE DE VERBOSITÉ : {verbosity_text}"},
    ]
    for i, ref in enumerate(reference_contents, 1):
        if ref.strip():
            content_blocks.append({
                "type": "text",
                "text": f"EXEMPLE DE RÉFÉRENCE {i} :\n{ref}",
            })
    content_blocks.append({
        "type": "text",
        "text": f"QUESTIONNAIRE À REMPLIR :\n{questionnaire_content}",
    })
    content_blocks.append({
        "type": "text",
        "text": "Remplis toutes les réponses. Retourne uniquement le JSON demandé.",
    })

    message = _client().messages.create(
        model=config["claude"]["model"],
        max_tokens=config["claude"]["max_tokens"],
        temperature=config["claude"]["temperature"],
        system=system_prompt,
        messages=[{"role": "user", "content": content_blocks}],
    )
    data = _parse_json(message.content[0].text)
    return data.get("responses", [])


def generate_attention_points(
    cadrage_context: str,
    questionnaire_with_responses: str,
) -> list[dict]:
    """Identify attention points in the filled questionnaire."""
    config = get_config()
    system_prompt = _load_prompt("system_attention.txt")

    user_content = (
        f"CONTEXTE DE CADRAGE :\n{cadrage_context}\n\n"
        f"QUESTIONNAIRE REMPLI :\n{questionnaire_with_responses}"
    )

    message = _client().messages.create(
        model=config["claude"]["model"],
        max_tokens=4000,
        temperature=0.2,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    data = _parse_json(message.content[0].text)
    return data.get("attention_points", [])
