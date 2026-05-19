# NyayaNode Backend

Decentralized multi-agent dispute arbitration API for India's ONDC network.
Built with **FastAPI 0.136 + Supabase + Python 3.11**.

---

## What this service does

- Accepts ONDC dispute webhooks and creates dispute records in Supabase
- Runs an AI arbitration agent (stub included; plug in Member 1's agent)
- Streams real-time progress to the frontend via Server-Sent Events
- Exposes mock ONDC buyer / seller / logistics APIs for demo purposes
- Serves a full audit trail per dispute

Swagger UI (auto-generated): **http://localhost:8000/docs**

---

## Prerequisites

| Tool | Minimum version | Install |
|---|---|---|
| Python | 3.11 | https://python.org/downloads |
| pip | bundled with Python | — |
| Git | any | https://git-scm.com |
| Supabase account | free tier is fine | https://supabase.com |

---

## 1 — Clone and enter the backend directory

```bash
git clone <repo-url>
cd <repo-root>/backend
```

---

## 2 — Create a virtual environment

```bash
# Mac / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

---

## 3 — Install dependencies

```bash
pip install -r requirements.txt
```

All packages are pinned. See `requirements.txt` for the full list.

Key packages:

| Package | Purpose |
|---|---|
| `fastapi` | Web framework + OpenAPI |
| `uvicorn[standard]` | ASGI server |
| `supabase` | Async Supabase client |
| `python-dotenv` | Load `.env` file |
| `httpx` | Async HTTP (used in tests + health check) |
| `pydantic` | Request / response validation |

---

## 4 — Set up Supabase

### 4a — Create a project

1. Go to https://supabase.com → **New project**
2. Choose a name (e.g. `nyayanode`), set a database password, pick a region close to India (e.g. `ap-south-1`)
3. Wait ~2 minutes for provisioning

### 4b — Run the database migration

1. In the Supabase dashboard open **SQL Editor**
2. Click **New query**
3. Paste the entire contents of `backend/migrations/001_init.sql`
4. Click **Run**

This creates four tables: `disputes`, `evidence`, `audit_events`, `agent_runs`
and a helper RPC `nyaya_select_one` used by the health check.

### 4c — Get your API keys

Dashboard → **Settings** → **API**

| Key | Where to find it | Which env var |
|---|---|---|
| Project URL | "Project URL" box | `SUPABASE_URL` |
| Anon / public key | "Project API keys" → anon | `SUPABASE_ANON_KEY` |
| Service role key | "Project API keys" → service_role | `SUPABASE_SERVICE_KEY` |

> The service role key bypasses Row Level Security. Never expose it to the browser.

---

## 5 — Configure environment variables

```bash
# From the backend/ directory:
# Windows
Copy-Item .env.example .env

# Mac / Linux
cp .env.example .env
```

Open `backend/.env` and fill in the three Supabase values:

```dotenv
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
BACKEND_API_KEY=nyayanode-internal-secret-key
FRONTEND_URL=https://nyayanode.vercel.app
AGENT_MODULE_PATH=agents.core.arbitrator
PORT=8000
```

`BACKEND_API_KEY` can be any string — it is checked on every `/api/v1/*` request
via the `X-API-Key` header. The default value works for local dev.

---

## 6 — Verify the setup

```bash
# From backend/
python scripts/verify_setup.py
```

Expected output:

```
Checking imports...
OK: 42 routes registered
SUPABASE_URL: https://xxxx.supabase.co
health: {'status': 'healthy', 'supabase': 'connected', ...}
stats: {'total_disputes': 0, ...}
VERIFY OK
```

If `supabase` shows `error` — double-check your `.env` values and that you ran the migration.

---

## 7 — Seed sample data (optional but recommended for demo)

```bash
# From backend/
python seed_data.py
```

Inserts 5 pre-resolved disputes covering all dispute types and outcomes.
The script is idempotent — safe to run multiple times.

---

## 8 — Start the server

```bash
# From backend/
uvicorn main:app --reload --port 8000
```

Or use the project script from the repo root:

```powershell
# Windows PowerShell (from repo root)
.\scripts\run.ps1
```

Server is ready when you see:

```
INFO:     Application startup complete.
```

Open **http://localhost:8000/docs** to see the full Swagger UI.

---

## 9 — Run the checklist (verify all tasks pass)

With the server running, open a second terminal from the repo root:

```powershell
# Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts/test_checklist.ps1
```

Expected: `27 passed, 0 failed, 0 warnings`

---

## Environment variables reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `SUPABASE_URL` | YES | — | Supabase project URL |
| `SUPABASE_ANON_KEY` | YES | — | Supabase anon/public key |
| `SUPABASE_SERVICE_KEY` | YES | — | Supabase service role key (bypasses RLS) |
| `BACKEND_API_KEY` | YES | `nyayanode-internal-secret-key` | `X-API-Key` header value |
| `FRONTEND_URL` | no | — | Extra CORS origin (Vercel URL) |
| `AGENT_MODULE_PATH` | no | `agents.core.arbitrator` | Import path for Member 1's agent |
| `PORT` | no | `8000` | Railway injects this automatically |

---

## API quick reference

All `/api/v1/*` endpoints require the `X-API-Key` header.
The SSE stream endpoint (`/stream`) does **not** require it (browser EventSource cannot send custom headers).

### Create a dispute

```bash
curl -X POST http://localhost:8000/api/v1/disputes \
  -H "X-API-Key: nyayanode-internal-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "buyer_id": "ondc_buyer_001",
    "seller_id": "ondc_seller_042",
    "logistics_id": "ondc_lsp_007",
    "order_id": "order_xyz",
    "dispute_type": "DAMAGED_ITEM",
    "dispute_amount_inr": 499.00,
    "evidence": [{"type": "text", "content": "Box arrived crushed"}]
  }'
```

### Trigger agent arbitration

```bash
curl -X POST http://localhost:8000/api/v1/disputes/<DISPUTE_ID>/arbitrate \
  -H "X-API-Key: nyayanode-internal-secret-key"
```

### Stream live progress (SSE — no API key needed)

```bash
curl -N --no-buffer http://localhost:8000/api/v1/disputes/<DISPUTE_ID>/stream
```

### Get audit trail

```bash
curl http://localhost:8000/api/v1/disputes/<DISPUTE_ID>/audit-trail \
  -H "X-API-Key: nyayanode-internal-secret-key"
```

### Ingest ONDC webhook

```bash
curl -X POST http://localhost:8000/api/v1/ondc/webhook/dispute-raised \
  -H "X-API-Key: nyayanode-internal-secret-key" \
  -H "X-ONDC-Signature: mock-sig-abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "domain": "nic2004:52110", "action": "on_issue",
      "bap_id": "buyer-app.ondc.org", "bpp_id": "seller-app.ondc.org",
      "transaction_id": "txn_001", "message_id": "msg_001",
      "timestamp": "2025-01-14T10:00:00Z"
    },
    "message": {
      "issue": {
        "id": "issue_001", "order_id": "order_xyz",
        "issue_sub_category": "ITM03",
        "source": {"id": "ondc_buyer_001"},
        "description": {"short_desc": "Item damaged", "long_desc": "Box crushed"},
        "order_details": {"id": "order_xyz", "provider_id": "ondc_seller_042"}
      }
    }
  }'
```

---

## Deploy to Railway

1. Push this repo to GitHub (`.env` is gitignored — never committed)
2. Go to https://railway.app → **New Project** → **Deploy from GitHub repo**
3. Select the repo; Railway auto-detects `backend/railway.toml` and the `Dockerfile`
4. In the Railway dashboard → **Variables**, add:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_KEY`
   - `BACKEND_API_KEY`
   - `FRONTEND_URL` (your Vercel URL)
5. Railway injects `PORT` automatically — do not set it manually
6. The `/health` endpoint is used as the healthcheck

---

## Connecting Member 1's agent

When Member 1 pushes their arbitrator code, replace the stub in
`backend/services/agent_runner.py`:

```python
# Current stub (remove this):
async def run_agent_stub(dispute_id: str) -> dict:
    await asyncio.sleep(5)
    return { "status": "RESOLVED", "decision": "FULL_REFUND", ... }

# Replace with (uncomment and adjust import path):
# from agents.core.arbitrator import ArbitratorAgent
# async def run_agent_stub(dispute_id: str) -> dict:
#     agent = ArbitratorAgent()
#     return await agent.run(dispute_id)
```

Set `AGENT_MODULE_PATH=agents.core.arbitrator` in `.env` to match the import path.

---

## Project structure

```
backend/
├── main.py                  # FastAPI app, middleware, health, stats
├── env_loader.py            # Loads backend/.env on import
├── requirements.txt         # Pinned dependencies
├── Dockerfile               # python:3.11-slim, Railway-ready
├── railway.toml             # Railway build + deploy config
├── seed_data.py             # Insert 5 sample disputes
├── core/
│   ├── schemas.py           # HealthResponse, StatsResponse
│   ├── dispute_schemas.py   # CreateDisputeRequest, DisputeResponse
│   ├── mock_schemas.py      # Mock ONDC response schemas
│   └── problem_details.py   # RFC 7807 error helpers
├── routers/
│   ├── disputes.py          # CRUD + status lifecycle
│   ├── agent_bridge.py      # /arbitrate, /agent-status, /stream (SSE)
│   ├── ondc_webhook.py      # ONDC webhook ingress
│   ├── mock_parties.py      # Mock buyer / seller / logistics APIs
│   └── audit.py             # Audit trail + cascadeflow audit
├── services/
│   ├── supabase_client.py   # Async Supabase singleton
│   ├── dispute_service.py   # Business logic + DB writes
│   ├── agent_runner.py      # Agent stub + run_and_persist
│   ├── sse_manager.py       # SSE pub/sub broadcaster
│   └── mock_ondc.py         # Deterministic mock data generator
├── middleware/
│   └── api_key.py           # X-API-Key enforcement
├── migrations/
│   └── 001_init.sql         # Run once in Supabase SQL editor
└── scripts/
    └── verify_setup.py      # Import + health smoke test
```
