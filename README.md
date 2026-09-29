# Knowledge API (Cloud Run Service)

FastAPI backend that scrapes OptiSigns help articles into Gemini File Search or an OpenAI Vector Store, and exposes a chat endpoint grounded in that knowledge.

## Endpoints

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/health` | No | Liveness for Cloud Run |
| `POST` | `/api/v1/ingest` | `X-API-Key` | Start scrape+upload in background (`202`) |
| `GET` | `/api/v1/ingest/status` | `X-API-Key` | Current/last ingest counts |
| `POST` | `/api/v1/chat` | `X-API-Key` | Chatbot answer via file search |

All JSON fields use **snake_case**.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
```

Required env:

| Variable | Purpose |
| --- | --- |
| `SERVICE_API_KEY` | Shared secret for `X-API-Key` |
| `INGEST_PROVIDER` | `openai` (default) or `gemini` |
| `HELP_CENTER_BASE_URL` | Help center origin |

OpenAI:

| Variable | Purpose |
| --- | --- |
| `OPEN_AI_API_KEY` | OpenAI API key (raw value only in Secret Manager) |
| `OPENAI_VECTOR_STORE_ID` | `vs_...` |

Gemini:

| Variable | Purpose |
| --- | --- |
| `API_KEY` / `GEMINI_API_KEY` | Gemini API key |
| `GEMINI_FILE_SEARCH_STORE_NAME` | `fileSearchStores/...` |

## Run locally

```bash
# API server
uvicorn app:app --reload --port 8080

# One-shot CLI ingest (same pipeline)
python main.py
```

### Example calls

```bash
# Start ingest (async)
curl -X POST "http://localhost:8080/api/v1/ingest" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SERVICE_API_KEY" \
  -d '{"provider":"openai"}'

# Poll status
curl "http://localhost:8080/api/v1/ingest/status" \
  -H "X-API-Key: $SERVICE_API_KEY"

# Chat
curl -X POST "http://localhost:8080/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SERVICE_API_KEY" \
  -d '{"message":"How do I add a YouTube video?"}'
```

## Deploy (GCP Cloud Run Service)

All runtime config is one Secret Manager secret in **full `.env` format** (many `KEY=value` lines), mounted as a file:

| Item | Value |
| --- | --- |
| Secret name | `AI_ASSISTANT_ENV` |
| Mount path | `/secrets/.env` |
| App env | `DOTENV_PATH=/secrets/.env` |

Create / update the secret from your local `.env`:

```bash
# First time
gcloud secrets create AI_ASSISTANT_ENV --data-file=.env

# Later updates
gcloud secrets versions add AI_ASSISTANT_ENV --data-file=.env
```

Grant the Cloud Run runtime SA `roles/secretmanager.secretAccessor` on `AI_ASSISTANT_ENV`.

Push triggers [cloudbuild.yaml](cloudbuild.yaml), which deploys with:

- timeout 3600s
- `--no-cpu-throttling` (background ingest after `202`)
- `--set-secrets=/secrets/.env=AI_ASSISTANT_ENV:latest`

Do **not** put the whole `.env` into a single env-var secret like `API_KEY=...` — mount it as a **file** so dotenv can parse each key.
## Daily Scheduler

```bash
# Once per day at 02:00 Asia/Ho_Chi_Minh
gcloud scheduler jobs create http ai-assistant-daily-ingest \
  --location=asia-southeast1 \
  --schedule="0 2 * * *" \
  --time-zone="Asia/Ho_Chi_Minh" \
  --uri="https://SERVICE_URL/api/v1/ingest" \
  --http-method=POST \
  --headers="Content-Type=application/json,X-API-Key=YOUR_SERVICE_API_KEY" \
  --message-body='{"provider":"openai"}'
```

Replace `SERVICE_URL` with the Cloud Run service URL.

## Logs

Cloud Run → service `ai-assisstant` → Logs. Look for:

- `INGEST_STARTED` / `INGEST_SCRAPE_DONE`
- `INGEST_ARTICLE` / `INGEST_UPLOAD_START` / `INGEST_UPLOAD_DONE`
- `INGEST_SUMMARY` / `INGEST_FINISHED`
