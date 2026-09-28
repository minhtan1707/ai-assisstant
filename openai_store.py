"""OpenAI Vector Store upload helper (Playground / file_search)."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from openai import OpenAI


DEFAULT_CHUNK_SIZE = 2000
DEFAULT_CHUNK_OVERLAP = 200

logger = logging.getLogger("ingest.openai")


def extract_api_key(raw_value: str) -> str:
    """Normalize a secret that may be a raw key or a pasted .env blob."""
    value = raw_value.strip().strip("\ufeff")
    if not value:
        return ""
    prefixes = ("OPEN_AI_API_KEY=", "OPENAI_API_KEY=", "API_KEY=")
    if "\n" not in value and not any(value.startswith(prefix) for prefix in prefixes):
        return value.strip().strip('"').strip("'")
    for line in value.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for prefix in prefixes:
            if stripped.startswith(prefix):
                return stripped[len(prefix) :].strip().strip('"').strip("'")
    return value.splitlines()[0].strip().strip('"').strip("'")


def resolve_api_key() -> str:
    """Resolve API key from OPEN_AI_API_KEY or OPENAI_API_KEY."""
    api_key = extract_api_key(
        os.getenv("OPEN_AI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    )
    if not api_key:
        raise ValueError("Set OPEN_AI_API_KEY or OPENAI_API_KEY in the environment.")
    if "\n" in api_key:
        raise ValueError(
            "OPEN_AI_API_KEY secret must contain only the raw key value, not a full .env file."
        )
    return api_key


def resolve_vector_store_id() -> str:
    """Resolve the OpenAI Vector Store id used by Playground file_search."""
    store_id = (os.getenv("OPENAI_VECTOR_STORE_ID") or "").strip()
    if not store_id:
        raise ValueError("Set OPENAI_VECTOR_STORE_ID in the environment.")
    return store_id


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split text with a sliding window, preferring Markdown heading boundaries."""
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            window = text[start:end]
            heading_matches = list(re.finditer(r"\n#{1,6}\s", window))
            if heading_matches:
                last_heading = heading_matches[-1].start()
                if last_heading > chunk_size // 2:
                    end = start + last_heading
        chunks.append(text[start:end])
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


class OpenAIStoreManager:
    """Uploads Markdown files to an OpenAI Vector Store for Playground file_search."""

    def __init__(
        self,
        api_key: str | None = None,
        vector_store_id: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self.api_key = api_key or resolve_api_key()
        self.vector_store_id = vector_store_id or resolve_vector_store_id()
        self.chunk_size = chunk_size or int(os.getenv("CHUNK_SIZE", str(DEFAULT_CHUNK_SIZE)))
        self.chunk_overlap = chunk_overlap or int(
            os.getenv("CHUNK_OVERLAP", str(DEFAULT_CHUNK_OVERLAP))
        )
        self.client = OpenAI(api_key=self.api_key)

    def count_chunks(self, text: str) -> int:
        """Return how many chunks would be produced for logging."""
        return len(chunk_text(text, self.chunk_size, self.chunk_overlap))

    def upload_file(self, filepath: Path, display_name: str | None = None) -> object:
        """Upload a file into the vector store and wait until indexing completes."""
        name = display_name or filepath.name
        with filepath.open("rb") as handle:
            vector_file = self.client.vector_stores.files.upload_and_poll(
                vector_store_id=self.vector_store_id,
                file=(name, handle),
            )
        status = getattr(vector_file, "status", None)
        if status not in (None, "completed"):
            raise RuntimeError(f"Upload failed for {filepath}: status={status}")
        logger.info("Uploaded %s (file_id=%s)", name, getattr(vector_file, "id", None))
        return vector_file
