"""Router: /api/v1/llm  — usage logging and analytics."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.orm import LLMUsageLog
from ..models.schemas import LLMUsageCreate, LLMUsageLogResponse, LLMUsageStats
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/llm", tags=["llm-analytics"])

# Model pricing per 1,000 tokens (USD) — prompt, completion
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o":              (0.005,  0.015),
    "gpt-4o-mini":         (0.00015, 0.0006),
    "gpt-4-turbo":         (0.010,  0.030),
    "gpt-3.5-turbo":       (0.0005, 0.0015),
    "claude-3-5-sonnet-20241022": (0.003, 0.015),
    "claude-3-5-haiku-20241022":  (0.0008, 0.004),
    "claude-3-opus-20240229":     (0.015, 0.075),
    "gpt-35-turbo":        (0.0005, 0.0015),
}

_DEFAULT_PRICE_PER_1K = (0.001, 0.002)   # conservative default for unknown models


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prompt_price, comp_price = _MODEL_PRICING.get(model, _DEFAULT_PRICE_PER_1K)
    return round((prompt_tokens / 1000 * prompt_price) + (completion_tokens / 1000 * comp_price), 6)


@router.post("/log", response_model=ApiResponse[dict])
async def log_usage(
    body: LLMUsageCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """
    Record one LLM call's token usage. Called by recommendation-service
    after each successful LLM completion.
    Cost is estimated here if not provided (based on model pricing table).
    """
    cost = body.estimated_cost_usd
    if cost == 0.0 and body.total_tokens > 0:
        cost = estimate_cost(body.model, body.prompt_tokens, body.completion_tokens)

    entry = LLMUsageLog(
        run_id=body.run_id,
        library_id=body.library_id,
        prompt_key=body.prompt_key,
        model=body.model,
        prompt_tokens=body.prompt_tokens,
        completion_tokens=body.completion_tokens,
        total_tokens=body.total_tokens,
        estimated_cost_usd=cost,
        latency_ms=body.latency_ms,
        logged_at=_now(),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return ApiResponse.ok(data={"id": entry.id, "cost_usd": cost}, meta=_meta())


@router.get("/usage", response_model=ApiResponse[dict])
async def get_usage(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """
    Returns aggregate stats + recent log entries for the analytics page.
    """
    # Aggregate stats
    agg = (await db.execute(
        select(
            func.count(LLMUsageLog.id).label("total_calls"),
            func.sum(LLMUsageLog.total_tokens).label("total_tokens"),
            func.sum(LLMUsageLog.prompt_tokens).label("total_prompt_tokens"),
            func.sum(LLMUsageLog.completion_tokens).label("total_completion_tokens"),
            func.sum(LLMUsageLog.estimated_cost_usd).label("total_cost"),
            func.avg(LLMUsageLog.latency_ms).label("avg_latency"),
        )
    )).one()

    # This month stats
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
    month_agg = (await db.execute(
        select(
            func.count(LLMUsageLog.id).label("calls"),
            func.sum(LLMUsageLog.estimated_cost_usd).label("cost"),
        ).where(LLMUsageLog.logged_at >= month_start)
    )).one()

    # Models used
    models_result = await db.execute(
        select(
            LLMUsageLog.model,
            func.count(LLMUsageLog.id).label("cnt"),
            func.sum(LLMUsageLog.total_tokens).label("tokens"),
            func.sum(LLMUsageLog.estimated_cost_usd).label("cost"),
            func.avg(LLMUsageLog.latency_ms).label("avg_latency"),
            func.max(LLMUsageLog.logged_at).label("last_used_at"),
        )
        .group_by(LLMUsageLog.model)
        .order_by(func.count(LLMUsageLog.id).desc())
    )
    models = [{
        "model": r.model,
        "calls": r.cnt,
        "tokens": int(r.tokens or 0),
        "cost": round(r.cost or 0, 6),
        "avg_latency_ms": round(r.avg_latency, 1) if r.avg_latency else None,
        "last_used_at": r.last_used_at,
    } for r in models_result.all()]

    # Per-library cost (top 10 most expensive)
    lib_cost_result = await db.execute(
        select(LLMUsageLog.library_id, func.sum(LLMUsageLog.estimated_cost_usd).label("cost"),
               func.sum(LLMUsageLog.total_tokens).label("tokens"), func.count().label("calls"))
        .where(LLMUsageLog.library_id.isnot(None))
        .group_by(LLMUsageLog.library_id)
        .order_by(func.sum(LLMUsageLog.estimated_cost_usd).desc())
        .limit(10)
    )
    per_library = [{"library_id": r.library_id, "cost_usd": round(r.cost or 0, 6),
                    "total_tokens": r.tokens or 0, "calls": r.calls} for r in lib_cost_result.all()]

    # Recent entries
    recent = (await db.execute(
        select(LLMUsageLog).order_by(LLMUsageLog.logged_at.desc()).limit(limit)
    )).scalars().all()

    stats = LLMUsageStats(
        total_calls=agg.total_calls or 0,
        total_tokens=agg.total_tokens or 0,
        total_prompt_tokens=agg.total_prompt_tokens or 0,
        total_completion_tokens=agg.total_completion_tokens or 0,
        total_cost_usd=round(agg.total_cost or 0, 6),
        avg_latency_ms=round(agg.avg_latency, 1) if agg.avg_latency else None,
        models_used=[m["model"] for m in models],
        calls_this_month=month_agg.calls or 0,
        cost_this_month=round(month_agg.cost or 0, 6),
    )

    return ApiResponse.ok(
        data={
            "stats": stats.model_dump(),
            "models_breakdown": models,
            "per_library_cost": per_library,
            "recent_entries": [
                LLMUsageLogResponse.model_validate(r).model_dump() for r in recent
            ],
        },
        meta=_meta(),
    )
