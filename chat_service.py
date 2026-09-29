"""Chat helpers grounded in Gemini File Search or OpenAI Vector Store."""

from __future__ import annotations

import logging
import os
from typing import Any

from ingest_runner import resolve_provider

logger = logging.getLogger("chat")

DEFAULT_OPENAI_CHAT_MODEL = "gpt-4.1-mini"
DEFAULT_GEMINI_CHAT_MODEL = "gemini-2.0-flash"


def resolve_openai_chat_model() -> str:
    """Resolve OpenAI chat model from env."""
    return (os.getenv("OPENAI_CHAT_MODEL") or DEFAULT_OPENAI_CHAT_MODEL).strip()


def resolve_gemini_chat_model() -> str:
    """Resolve Gemini chat model from env."""
    return (os.getenv("GEMINI_CHAT_MODEL") or DEFAULT_GEMINI_CHAT_MODEL).strip()


def extract_openai_citations(response: Any) -> list[dict[str, str]]:
    """Best-effort citation extraction from an OpenAI Responses payload."""
    citations: list[dict[str, str]] = []
    output_items = getattr(response, "output", None) or []
    for item in output_items:
        contents = getattr(item, "content", None) or []
        for content in contents:
            annotations = getattr(content, "annotations", None) or []
            for annotation in annotations:
                file_id = getattr(annotation, "file_id", None) or getattr(
                    annotation, "file_citation", None
                )
                filename = getattr(annotation, "filename", None) or ""
                if file_id or filename:
                    citations.append(
                        {
                            "file_id": str(file_id or ""),
                            "filename": str(filename or ""),
                        }
                    )
    return citations


def chat_with_openai(message: str) -> dict[str, object]:
    """Answer using OpenAI Responses API with file_search."""
    from openai import OpenAI
    from openai_store import resolve_api_key, resolve_vector_store_id

    client = OpenAI(api_key=resolve_api_key())
    vector_store_id = resolve_vector_store_id()
    model = resolve_openai_chat_model()
    logger.info("CHAT_START provider=openai model=%s", model)
    response = client.responses.create(
        model=model,
        input=message,
        tools=[
            {
                "type": "file_search",
                "vector_store_ids": [vector_store_id],
            }
        ],
    )
    answer = getattr(response, "output_text", None) or ""
    citations = extract_openai_citations(response)
    logger.info("CHAT_DONE provider=openai citations=%s", len(citations))
    return {
        "answer": answer,
        "provider": "openai",
        "citations": citations,
    }


def chat_with_gemini(message: str) -> dict[str, object]:
    """Answer using Gemini generate_content with File Search tool."""
    from google import genai
    from google.genai import types

    from gemini_store import resolve_api_key

    store_name = (os.getenv("GEMINI_FILE_SEARCH_STORE_NAME") or "").strip()
    if not store_name:
        raise ValueError("Set GEMINI_FILE_SEARCH_STORE_NAME in the environment.")
    client = genai.Client(api_key=resolve_api_key())
    model = resolve_gemini_chat_model()
    logger.info("CHAT_START provider=gemini model=%s", model)
    response = client.models.generate_content(
        model=model,
        contents=message,
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[store_name],
                    )
                )
            ]
        ),
    )
    answer = getattr(response, "text", None) or ""
    citations: list[dict[str, str]] = []
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        grounding = getattr(candidates[0], "grounding_metadata", None)
        chunks = getattr(grounding, "grounding_chunks", None) or []
        for chunk in chunks:
            retrieved = getattr(chunk, "retrieved_context", None)
            title = getattr(retrieved, "title", None) or ""
            uri = getattr(retrieved, "uri", None) or ""
            if title or uri:
                citations.append({"filename": str(title), "uri": str(uri)})
    logger.info("CHAT_DONE provider=gemini citations=%s", len(citations))
    return {
        "answer": answer,
        "provider": "gemini",
        "citations": citations,
    }


def execute_chat(message: str, provider: str | None = None) -> dict[str, object]:
    """Route chat to the configured knowledge provider."""
    text = (message or "").strip()
    if not text:
        raise ValueError("message must not be empty")
    resolved = resolve_provider(provider)
    if resolved == "openai":
        return chat_with_openai(text)
    return chat_with_gemini(text)
