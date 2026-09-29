"""Load dotenv from Secret Manager mount path and/or local .env."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("env")

DEFAULT_SECRET_ENV_PATH = "/secrets/.env"


def resolve_dotenv_paths() -> list[Path]:
    """Return dotenv file paths to load (secret mount first, then local .env)."""
    configured = (os.getenv("DOTENV_PATH") or "").strip()
    candidates = [
        Path(configured) if configured else Path(DEFAULT_SECRET_ENV_PATH),
        Path(".env"),
    ]
    unique_paths: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)
    return unique_paths


def load_app_env() -> None:
    """Load environment variables from mounted secret .env and local .env."""
    for path in resolve_dotenv_paths():
        if not path.is_file():
            continue
        load_dotenv(dotenv_path=path, override=False)
        logger.info("Loaded env file path=%s", path)
