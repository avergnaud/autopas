"""PAS Assistant — Configuration loader.

Loads app.yaml, .env, questions.txt, and users.yaml on startup.
All paths are relative to BASE_DIR (default: /opt/pas-assistant).
Override with the PAS_BASE_DIR environment variable for local development.
"""

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_config: dict[str, Any] | None = None

BASE_DIR = Path(os.environ.get("PAS_BASE_DIR", "/opt/pas-assistant"))
CONFIG_DIR = BASE_DIR / "data" / "config"


def load_config() -> dict[str, Any]:
    """Load and cache the full application configuration.

    Returns:
        Merged configuration dict with keys: claude, verbosity, reference,
        oauth2, teams_bot, server, questions, authorized_users.
    """
    global _config

    # Load .env so environment variables are available before reading app.yaml
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        logger.info("Loaded .env from %s", env_file)
    else:
        logger.warning(".env not found at %s — secrets must be set in environment", env_file)

    # Load app.yaml
    app_yaml_path = CONFIG_DIR / "app.yaml"
    with open(app_yaml_path, encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)
    logger.info("Loaded app.yaml from %s", app_yaml_path)

    # Load questions
    config["questions"] = _load_questions(CONFIG_DIR / "questions.txt")
    logger.info("Loaded %d questions", len(config["questions"]))

    # Load authorized users
    users_path = CONFIG_DIR / "users.yaml"
    with open(users_path, encoding="utf-8") as f:
        users_data: dict[str, Any] = yaml.safe_load(f)
    config["authorized_users"] = {
        u["email"]: u["role"] for u in users_data.get("authorized_users", [])
    }
    logger.info("Loaded %d authorized users", len(config["authorized_users"]))

    _config = config
    return _config


def get_config() -> dict[str, Any]:
    """Return the cached configuration.

    Raises:
        RuntimeError: If load_config() has not been called yet.
    """
    if _config is None:
        raise RuntimeError("Configuration not loaded. Call load_config() first.")
    return _config


def _load_questions(path: Path) -> list[dict[str, Any]]:
    """Parse questions.txt into a list of question dicts.

    Each question starts with a line beginning with '+ '.
    Subsequent non-empty lines (OPTIONS:, TYPE:, MULTI:) are metadata.
    Conditional questions start with 'IF <condition>: <text>'.

    Args:
        path: Path to questions.txt

    Returns:
        List of dicts with keys: text, options, type, multi, condition.
    """
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            if stripped.startswith("+ "):
                if current is not None:
                    questions.append(current)
                text = stripped[2:].strip()
                current = {
                    "text": text,
                    "options": None,
                    "type": "text",
                    "multi": False,
                    "condition": None,
                }
                # Detect conditional question: "IF <condition>: <question text>"
                if text.upper().startswith("IF "):
                    parts = text.split(":", 1)
                    if len(parts) == 2:
                        current["condition"] = parts[0][3:].strip()  # strip leading "IF "
                        current["text"] = parts[1].strip()

            elif stripped.startswith("OPTIONS:") and current is not None:
                opts = stripped[len("OPTIONS:"):].strip()
                current["options"] = [o.strip() for o in opts.split(",")]

            elif stripped.startswith("TYPE:") and current is not None:
                current["type"] = stripped[len("TYPE:"):].strip()

            elif stripped.startswith("MULTI:") and current is not None:
                current["multi"] = stripped[len("MULTI:"):].strip().lower() == "true"

    if current is not None:
        questions.append(current)

    return questions
