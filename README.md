# NyayaNode

Decentralized multi-agent dispute arbitration for India's ONDC network.

A neutral AI arbitrator that resolves buyer-seller-logistics disputes on ONDC
without a central authority. Built for a 15-hour hackathon.

---

## Repo structure

```
nyayanode/
├── backend/          # FastAPI API server (Member 3)
├── agents/           # AI arbitration agent (Member 1)
├── scripts/
│   ├── run.ps1       # Start the backend (Windows)
│   ├── verify.ps1    # Smoke-test imports + health
│   └── test_checklist.ps1  # Full requirement checklist (27 checks)
├── .env.example      # Copy to backend/.env and fill in credentials
└── .gitignore
```

---

## Quick start (backend only)

```powershell
# 1. Clone
git clone <repo-url>
cd nyayanode

# 2. Copy env template
Copy-Item .env.example backend\.env
# Open backend\.env and fill in SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY

# 3. Install dependencies
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 4. Run Supabase migration
# Paste backend/migrations/001_init.sql into Supabase SQL Editor and run it

# 5. Verify setup
python scripts\verify_setup.py

# 6. Seed sample data
python seed_data.py

# 7. Start server
cd ..
.\scripts\run.ps1
```

Server: http://localhost:8000
Swagger UI: http://localhost:8000/docs

---

## Credentials needed

| Credential | Where to get it | Which file |
|---|---|---|
| `SUPABASE_URL` | Supabase dashboard → Settings → API | `backend/.env` |
| `SUPABASE_ANON_KEY` | Supabase dashboard → Settings → API | `backend/.env` |
| `SUPABASE_SERVICE_KEY` | Supabase dashboard → Settings → API | `backend/.env` |
| `BACKEND_API_KEY` | Any string you choose | `backend/.env` |

See `backend/README.md` for the full setup guide.

---

## Run the requirement checklist

With the server running:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test_checklist.ps1
```

Expected: `27 passed, 0 failed, 0 warnings`

---

## Deploy

- **Backend** → Railway (auto-detects `backend/railway.toml` + `Dockerfile`)
- **Frontend** → Vercel

Set the four Supabase + API key variables in the Railway dashboard.
Railway injects `PORT` automatically.
