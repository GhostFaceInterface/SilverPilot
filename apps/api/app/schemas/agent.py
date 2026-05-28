from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class LLMTraceCreate(BaseModel):
    agent_name: str = Field(min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=100)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_cost_usd: Decimal = Field(default=Decimal("0.000000"), ge=Decimal("0.0"))
    latency_ms: int = Field(default=0, ge=0)
    status: Literal["SUCCESS", "FAILED"]
    prompt_raw: str | None = None
    response_raw: str | None = None
    error_message: str | None = None


class LLMTraceResponse(LLMTraceCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentMemoryCreate(BaseModel):
    agent_name: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=256)
    value_json: dict = Field(default_factory=dict)


class AgentMemoryResponse(AgentMemoryCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RiskCritiqueRequest(BaseModel):
    signal_id: int | None = None


class ReportResponse(BaseModel):
    id: int
    report_type: str
    period_start: datetime
    period_end: datetime
    payload_json: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrchestrateRunRequest(BaseModel):
    signal_id: int | None = None
