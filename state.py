"""Content-hash tracker for article delta detection."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

ChangeKind = Literal["added", "updated", "skipped"]


class ArticleStateStore:
    """Persists SHA256 hashes keyed by article id in a JSON file."""

    def __init__(self, state_path: str | Path | None = None) -> None:
        self.path = Path(state_path or os.getenv("STATE_PATH", "state.json"))
        self._records: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._records = {}
            return
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self._records = payload.get("articles", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump({"articles": self._records}, handle, indent=2, sort_keys=True)
            handle.write("\n")

    def classify(self, article_id: str, content_hash: str) -> ChangeKind:
        previous = self._records.get(article_id)
        if previous is None:
            return "added"
        if previous.get("content_hash") != content_hash:
            return "updated"
        return "skipped"

    def mark(self, article_id: str, content_hash: str, slug: str) -> None:
        self._records[article_id] = {
            "content_hash": content_hash,
            "slug": slug,
        }
