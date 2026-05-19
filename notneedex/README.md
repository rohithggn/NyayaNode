# NyayaNode — Decentralized AI Dispute Arbitration for ONDC

> Micro-arbitrator AI agents that resolve buyer-seller disputes on India's Open Network for Digital Commerce (ONDC) in real-time, within a ₹5 inference budget per case.

## Team

| # | Role | Domain | Deploy Target |
|---|------|---------|---------------|
| 1 | Lead AI Architect | `agents/` | Railway |
| 2 | Cascadeflow Integration | `agents/cascadeflow/` | Railway |
| 3 | Backend / FastAPI | `backend/` | Railway |
| 4 | Frontend | `frontend/` | Vercel |
| 5 | QA | `qa/` | — |
| 6 | Media / Demo | `media/` | — |

## Quick Start (All Members)

```bash
# 1. Clone
git clone https://github.com/your-org/nyayanode.git
cd nyayanode

# 2. Copy env file and fill in your keys
cp .env.example .env
# Edit .env with your assigned API keys

# 3. Go to your domain
cd agents/   # Member 1 & 2
cd backend/  # Member 3
cd frontend/ # Member 4
```

## Member 1 — Agent Setup

```bash
cd agents/
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Verify schemas load correctly
cd ..
python -m shared.schemas

# Run agent service
cd agents/
uvicorn core.arbitrator:app --host 0.0.0.0 --port 8001 --reload
```

## Architecture

```
ONDC Buyer → FastAPI Backend → LangGraph Agent
                                     │
                    ┌────────────────┤
                    ▼                ▼
              Hindsight          Cascadeflow
           (Memory/Rollback)   (Budget Router)
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
     Logistics   Evidence  Negotiation
       Tool       Tool       Tool
          │
          └──→ Groq LLM (llama-3.3-70b / llama-3.1-8b)
                          │
                    DisputeResponse
```

## API Contract

### POST `/agents/arbitrate`
Initiates dispute arbitration. See `shared/schemas.py → DisputeRequest`.

### GET `/agents/dispute/{dispute_id}/status`
Poll for resolution status. Returns `DisputeStatusResponse`.

### GET `/agents/dispute/{dispute_id}/audit_trail`
Full audit trail for a dispute. Returns `list[AuditEntry]`.

## Shared Schemas

All members import from `shared/schemas.py`:

```python
from shared.schemas import DisputeRequest, DisputeResponse, AuditEntry
```

Print JSON schema for frontend type generation:
```bash
python -m shared.schemas
```

## Sponsor Integration

- **Hindsight**: `agents/hindsight/` — memory persistence, 90-day session TTL, rollback
- **Cascadeflow**: `agents/cascadeflow/` — ₹5/dispute budget cap, model routing

## Environment Variables

See `.env.example` for all required variables. Each member only needs to fill in their section.
