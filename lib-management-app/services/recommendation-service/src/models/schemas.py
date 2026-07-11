"""Recommendation Service — Pydantic v2 DTOs."""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UpgradeDecision(str, Enum):
    YES = "Yes"            # Upgrade strongly recommended / forced
    NO = "No"              # No upgrade needed
    SUFFICIENT = "Sufficient"  # Library is up-to-date


class GeneratorType(str, Enum):
    RULE_BASED = "rule_based"
    LLM = "llm"


# ── Inbound ───────────────────────────────────────────────────────────────────

class RecommendationRequest(BaseModel):
    library_id: int
    package: str
    platform: str
    current_version: str
    latest_version: str
    update_needed: str | None = None
    library_status: str | None = None      # Active / Deprecated / Legacy / ...
    new_version_released: bool = False
    version_status: str | None = None      # newer / same / older / unknown
    release_notes: str | None = None
    version_window_summary: str | None = None
    deprecation_notes: str | None = None
    needs_manual_review: bool = False

    model_config = {"json_schema_extra": {"example": {
        "library_id": 1,
        "package": "com.google.firebase:firebase-bom",
        "platform": "Android",
        "current_version": "33.1.0",
        "latest_version": "33.5.0",
        "update_needed": "Mandatory",
        "library_status": "Active",
        "new_version_released": True,
        "version_status": "newer",
    }}}


class BatchRecommendationRequest(BaseModel):
    libraries: list[RecommendationRequest] = Field(..., min_length=1, max_length=500)


# ── Outbound ──────────────────────────────────────────────────────────────────

class RecommendationResult(BaseModel):
    library_id: int
    package: str
    platform: str
    current_version: str
    latest_version: str
    priority: str | None = None  # CRITICAL|HIGH|MODERATE|LOW|NONE|MANUAL_REVIEW
    upgrade_recommended: UpgradeDecision
    upgrade_pros: list[str] = []
    upgrade_cons: list[str] = []
    no_upgrade_pros: list[str] = []
    no_upgrade_cons: list[str] = []
    recommendation_summary: str
    generator_used: GeneratorType
    generated_at: datetime = Field(default_factory=_utcnow)

    model_config = {"use_enum_values": True}


class BatchRecommendationResult(BaseModel):
    total: int
    yes_count: int
    no_count: int
    sufficient_count: int
    results: list[RecommendationResult]
    generated_at: datetime = Field(default_factory=_utcnow)


class LLMTestRequest(BaseModel):
    """Payload for POST /recommendations/test-llm."""
    package: str = "com.example:test-lib"
    platform: str = "Android"
    current_version: str = "1.0.0"
    latest_version: str = "2.0.0"


class LLMTestResult(BaseModel):
    llm_enabled: bool
    provider: str
    model: str
    success: bool
    message: str
    sample_output: RecommendationResult | None = None


class RecommendationChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class RecommendationChatRequest(BaseModel):
    library_id: int
    package: str
    sdk_name: str | None = None
    platform: str
    current_version: str | None = None
    latest_version: str | None = None
    update_needed: str | None = None
    status: str | None = None
    recommendation_summary: str | None = None
    upgrade_recommended: str | None = None
    upgrade_pros: list[str] = Field(default_factory=list)
    upgrade_cons: list[str] = Field(default_factory=list)
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[RecommendationChatTurn] = Field(default_factory=list, max_length=8)


class RecommendationChatResult(BaseModel):
    answer: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int | None = None
