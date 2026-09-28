# Knowledge Ingest Job

Python batch job that scrapes help-center articles, converts them to clean Markdown, and uploads only new or changed documents to a knowledge store. **Default provider is OpenAI** (`INGEST_PROVIDER=openai`). Set `INGEST_PROVIDER=gemini` to use Gemini File Search instead.

## What it does

1. Fetches articles from a Zendesk Help Center API.
2. Writes clean Markdown to `articles/<slug>.md`.
3. Classifies each article as **added**, **updated**, or **skipped** via content hash.
4. Uploads only the delta to Gemini File Search (default) or OpenAI Vector Store.
5. Logs file counts, chunk counts, and added/updated/skipped totals.

## Provider switch

| `INGEST_PROVIDER` | Target | Typical use |
| --- | --- | --- |
| `openai` (default) | OpenAI Vector Store | Playground file_search |
| `gemini` | Gemini File Search Store | AI Studio (needs billing/credits) |

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
```

Required for **OpenAI** (default):

| Variable | Purpose |
| --- | --- |
| `OPEN_AI_API_KEY` | OpenAI API key (raw key only) |
| `OPENAI_VECTOR_STORE_ID` | `vs_...` |
| `HELP_CENTER_BASE_URL` | Help center origin |

Optional for **Gemini** (`INGEST_PROVIDER=gemini`):

| Variable | Purpose |
| --- | --- |
| `API_KEY` or `GEMINI_API_KEY` | Gemini API key |
| `GEMINI_FILE_SEARCH_STORE_NAME` | `fileSearchStores/...` |

## Run locally

```bash
# OpenAI (default)
python main.py

# Gemini
INGEST_PROVIDER=gemini python main.py
```

## Cloud Build

Default substitution `_INGEST_PROVIDER: openai`. To deploy Gemini instead, set `_INGEST_PROVIDER=gemini`.

## Smoke test (OpenAI)

In OpenAI Playground, enable file_search on vector store `OPENAI_VECTOR_STORE_ID` and ask:

> How do I add a YouTube video?
