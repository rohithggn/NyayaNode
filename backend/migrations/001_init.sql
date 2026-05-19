-- NyayaNode initial schema
-- Run against your Supabase Postgres database (SQL editor or CLI).

CREATE TABLE IF NOT EXISTS disputes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    buyer_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    logistics_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    dispute_type TEXT NOT NULL,  -- DAMAGED_ITEM|WRONG_ITEM|NOT_DELIVERED|REFUND_DENIED
    status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING|EVIDENCE_COLLECTION|NEGOTIATION|RESOLVED|ESCALATED
    decision TEXT,  -- FULL_REFUND|PARTIAL_REFUND|REJECTED|PENDING
    dispute_amount_inr NUMERIC(10, 2) NOT NULL,
    refund_amount_inr NUMERIC(10, 2),
    reasoning TEXT,
    confidence_score NUMERIC(4, 3),
    hindsight_session_id TEXT,
    total_cost_inr NUMERIC(8, 4),
    budget_inr NUMERIC(8, 2) DEFAULT 5.00,
    escalated_to_human BOOLEAN DEFAULT FALSE,
    agent_run_id UUID
);

CREATE TABLE IF NOT EXISTS evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dispute_id UUID REFERENCES disputes(id),
    submitted_by TEXT NOT NULL,  -- buyer|seller|logistics
    evidence_type TEXT NOT NULL,  -- image_url|text|tracking_data
    content TEXT NOT NULL,
    submitted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dispute_id UUID REFERENCES disputes(id),
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,  -- agent|buyer|seller|logistics|system
    payload JSONB,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dispute_id UUID REFERENCES disputes(id),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'RUNNING',
    cascadeflow_audit JSONB
);

-- Health-check RPC for backend test_connection() (SELECT 1)
CREATE OR REPLACE FUNCTION nyaya_select_one()
RETURNS integer
LANGUAGE sql
STABLE
AS $$
  SELECT 1;
$$;
