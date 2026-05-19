"""OpenAPI response models for health and stats endpoints."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: str = Field(example="healthy")
    supabase: str = Field(example="connected", description="connected | error")
    agent_module: str = Field(example="not_loaded", description="loaded | not_loaded")
    version: str = Field(example="1.0.0")


class StatsResponse(BaseModel):
    """Dashboard aggregate metrics."""

    total_disputes: int = Field(example=0)
    resolved_today: int = Field(example=0)
    avg_cost_inr: float = Field(example=0.0)
    avg_resolution_time_seconds: int = Field(example=0)
    escalated_count: int = Field(example=0)
