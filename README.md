# Knowledge Ingest Job

Python batch job that scrapes help-center articles, converts them to clean Markdown, and uploads only new or changed documents to a Gemini File Search Store. Runs once per invocation and exits `0`—ready for a daily schedule.

## What it does

1. Fetches articles from a Zendesk Help Center API.
2. Writes clean Markdown to `articles/<slug>.md` (headings, code blocks, and links kept; site chrome removed).
3. Classifies each article as **added**, **updated**, or **skipped** via content hash.
4. Uploads only the delta to Gemini File Search Store via API.
5. Logs file counts, chunk counts, and added/updated/skipped totals.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
```

Required env vars (see `.env.sample`):

| Variable | Purpose |
| --- | --- |
| `API_KEY` or `GEMINI_API_KEY` | Gemini API key |
| `GEMINI_FILE_SEARCH_STORE_NAME` | File Search Store resource name |
| `HELP_CENTER_BASE_URL` | Help center origin (no trailing path) |

## Run locally

```bash
python main.py
```

## Run with Docker

```bash
docker build -t knowledge-ingest .
docker run --rm \
  -e API_KEY \
  -e GEMINI_FILE_SEARCH_STORE_NAME \
  -e HELP_CENTER_BASE_URL \
  knowledge-ingest
```

## Daily job & logs

Schedule the container once per day (e.g. Cloud Run Job + Cloud Scheduler). After deploy, paste the log URL here:

- **Job logs:** _(add after deploy)_

## Smoke test

In Google AI Studio, attach the same File Search Store to an assistant and ask:

> How do I add a YouTube video?

Save a screenshot of a correct answer with citations:

![Assistant smoke test](docs/assistant-smoke-test.png)

## Chunking

~2000 character windows with ~200 overlap; prefer splits near Markdown headings. Each upload logs file name, character count, and chunk count.
