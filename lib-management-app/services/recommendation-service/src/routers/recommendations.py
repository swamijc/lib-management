"""
Recommendation Service — routers.

Endpoints:
  POST /api/v1/recommendations/generate/{library_id}  — generate for one library
  POST /api/v1/recommendations/generate/batch          — generate for all
  GET  /api/v1/recommendations                         — list all cached
  GET  /api/v1/recommendations/{library_id}            — get cached for one library
  POST /api/v1/recommendations/test-llm                — test LLM connectivity
"""
from __future__ import annotations
import time
from urllib.parse import urljoin

from fastapi import APIRouter, HTTPException
import httpx
import litellm

from ..config import settings
from ..models.schemas import (
    BatchRecommendationRequest,
    BatchRecommendationResult,
    LLMTestRequest,
    LLMTestResult,
    RecommendationChatRequest,
    RecommendationChatResult,
    RecommendationRequest,
    RecommendationResult,
)
from ..services.recommendation_service import RecommendationService
from ..generators.llm_generator import LLMGenerator
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])
_svc = RecommendationService()
_llm_gen = LLMGenerator()


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


async def _log_chat_usage(
    library_id: int,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int | None,
) -> None:
    try:
        payload = {
            "library_id": library_id,
            "prompt_key": "recommendation_chat",
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "latency_ms": latency_ms,
        }
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{settings.library_data_service_url}/api/v1/llm/log",
                json=payload,
                headers={"X-Internal-Service-Key": settings.internal_service_key},
            )
    except Exception:
        # Usage logging is best effort and should never block chat responses.
        return


@router.post(
    "/generate/batch",
    response_model=ApiResponse[BatchRecommendationResult],
)
async def generate_batch(req: BatchRecommendationRequest) -> ApiResponse[BatchRecommendationResult]:
    """Generate recommendations for a batch of libraries."""
    result = await _svc.generate_batch(req)
    return ApiResponse.ok(data=result, meta=_meta())


@router.post(
    "/generate/{library_id}",
    response_model=ApiResponse[RecommendationResult],
)
async def generate_one(
    library_id: int, req: RecommendationRequest
) -> ApiResponse[RecommendationResult]:
    """Generate a recommendation for a single library."""
    req = req.model_copy(update={"library_id": library_id})
    result = await _svc.generate_one(req)
    return ApiResponse.ok(data=result, meta=_meta())


@router.get("", response_model=ApiResponse[list[RecommendationResult]])
async def list_recommendations() -> ApiResponse[list[RecommendationResult]]:
    """Return all cached recommendation results."""
    return ApiResponse.ok(data=_svc.list_all_cached(), meta=_meta())


@router.get("/{library_id}", response_model=ApiResponse[RecommendationResult])
async def get_recommendation(library_id: int) -> ApiResponse[RecommendationResult]:
    """Return the cached recommendation for a specific library."""
    result = _svc.get_cached(library_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No recommendation found for library_id={library_id}",
        )
    return ApiResponse.ok(data=result, meta=_meta())


@router.post("/test-llm", response_model=ApiResponse[LLMTestResult])
async def test_llm(req: LLMTestRequest) -> ApiResponse[LLMTestResult]:
    """Test LLM connectivity with a sample payload."""
    test_req = RecommendationRequest(
        library_id=0,
        package=req.package,
        platform=req.platform,
        current_version=req.current_version,
        latest_version=req.latest_version,
        update_needed="Mandatory",
        new_version_released=True,
    )

    runtime = await _llm_gen._load_runtime_llm_config()

    if not runtime.get("enabled") or not runtime.get("provider") or not runtime.get("api_key"):
        return ApiResponse.ok(
            data=LLMTestResult(
                llm_enabled=False,
                provider=str(runtime.get("provider") or "not configured"),
                model=str(runtime.get("model") or settings.llm_model),
                success=False,
                message="LLM is not enabled — configure provider/model/key in Settings.",
            ),
            meta=_meta(),
        )

    try:
        from ..generators.llm_generator import LLMGenerator
        gen = LLMGenerator()
        sample = await gen.generate(test_req)
        return ApiResponse.ok(
            data=LLMTestResult(
                llm_enabled=True,
                provider=str(runtime.get("provider") or "unknown"),
                model=str(runtime.get("model") or settings.llm_model),
                success=True,
                message="LLM call succeeded.",
                sample_output=sample,
            ),
            meta=_meta(),
        )
    except Exception as exc:
        return ApiResponse.ok(
            data=LLMTestResult(
                llm_enabled=True,
                provider=str(runtime.get("provider") or "unknown"),
                model=str(runtime.get("model") or settings.llm_model),
                success=False,
                message=f"LLM call failed: {exc}",
            ),
            meta=_meta(),
        )


@router.post("/chat/ask", response_model=ApiResponse[RecommendationChatResult])
async def ask_chat(req: RecommendationChatRequest) -> ApiResponse[RecommendationChatResult]:
    """LLM-powered ask-doubt endpoint for SDK recommendation detail view."""
    runtime = await _llm_gen._load_runtime_llm_config()
    if not runtime.get("enabled") or not runtime.get("provider") or not runtime.get("api_key"):
        raise HTTPException(status_code=503, detail="LLM chat is not configured")

    sdk_name = req.sdk_name or req.package
    context_lines = [
        f"SDK: {sdk_name}",
        f"Package: {req.package}",
        f"Platform: {req.platform}",
        f"Current version: {req.current_version or 'Unknown'}",
        f"Latest version: {req.latest_version or 'Unknown'}",
        f"Update needed: {req.update_needed or 'Unknown'}",
        f"Status: {req.status or 'Unknown'}",
        f"Recommendation decision: {req.upgrade_recommended or 'Unknown'}",
        f"Recommendation summary: {req.recommendation_summary or 'Not available'}",
        "Upgrade pros: " + ("; ".join(req.upgrade_pros[:3]) if req.upgrade_pros else "None"),
        "Upgrade cons: " + ("; ".join(req.upgrade_cons[:3]) if req.upgrade_cons else "None"),
    ]

    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are an enterprise SDK upgrade assistant. Answer only from provided SDK context. "
                "If context is missing, state uncertainty clearly. Keep responses concise and actionable."
            ),
        },
        {"role": "user", "content": "SDK Context:\n" + "\n".join(context_lines)},
    ]
    for turn in req.history[-6:]:
        messages.append({"role": turn.role, "content": turn.text})
    messages.append({"role": "user", "content": req.question})

    t0 = time.monotonic()
    provider = str(runtime.get("provider") or "").strip().lower()
    try:
        if provider == "openai":
            base = str(runtime.get("api_base") or "https://api.openai.com/v1").strip()
            if not base.endswith("/"):
                base += "/"
            endpoint = urljoin(base, "responses")

            if settings.llm_ssl_verify:
                try:
                    import certifi
                    verify = certifi.where()
                except Exception:
                    verify = True
            else:
                verify = False

            input_items = []
            for msg in messages:
                input_items.append({
                    "role": msg["role"],
                    "content": [{"type": "input_text", "text": msg["content"]}],
                })

            payload = {
                "model": runtime["model"],
                "input": input_items,
                "temperature": float(runtime["temperature"]),
                "max_output_tokens": int(min(int(runtime["max_tokens"]), 700)),
                "store": False,
            }

            async with httpx.AsyncClient(timeout=float(runtime["timeout"]), verify=verify) as client:
                r = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {runtime['api_key']}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()

            answer = (data.get("output_text") or "").strip()
            if not answer:
                out = data.get("output") or []
                text_parts: list[str] = []
                for item in out:
                    for content in item.get("content") or []:
                        txt = content.get("text")
                        if txt:
                            text_parts.append(txt)
                answer = "\n".join(text_parts).strip()

            usage = data.get("usage") or {}
            prompt_tokens = int(usage.get("input_tokens") or 0)
            completion_tokens = int(usage.get("output_tokens") or 0)
        else:
            kwargs: dict = {
                "model": runtime["model"],
                "messages": messages,
                "temperature": float(runtime["temperature"]),
                "max_tokens": int(min(int(runtime["max_tokens"]), 700)),
                "timeout": float(runtime["timeout"]),
                "api_key": runtime["api_key"] or None,
                "custom_llm_provider": runtime["provider"],
            }
            if runtime.get("api_base"):
                kwargs["api_base"] = runtime["api_base"]
            resp = await litellm.acompletion(**kwargs)
            answer = (resp.choices[0].message.content or "").strip()
            usage = getattr(resp, "usage", None)
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM chat call failed: {exc}") from exc

    latency_ms = int((time.monotonic() - t0) * 1000)

    await _log_chat_usage(
        library_id=req.library_id,
        model=runtime["model"],
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
    )

    return ApiResponse.ok(
        data=RecommendationChatResult(
            answer=answer or "I could not generate a response for this SDK right now.",
            model=runtime["model"],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
        ),
        meta=_meta(),
    )
