"""
Recommendation Service — orchestrator.

Selects LLM or rule-based generator, runs generation, handles LLM fallback.
"""
from __future__ import annotations

import structlog

from ..config import settings
from ..generators.llm_generator import LLMGenerator
from ..generators.rule_based import RuleBasedGenerator
from ..models.schemas import (
    BatchRecommendationRequest,
    BatchRecommendationResult,
    RecommendationRequest,
    RecommendationResult,
    UpgradeDecision,
)

logger = structlog.get_logger(__name__)

# In-memory cache: library_id → latest result (reset on restart)
_results_cache: dict[int, RecommendationResult] = {}


class RecommendationService:

    def __init__(self) -> None:
        self._rule_gen = RuleBasedGenerator()
        self._llm_gen = LLMGenerator()

    async def generate_one(self, req: RecommendationRequest) -> RecommendationResult:
        # LLMGenerator now resolves effective runtime config from Settings API.
        # It self-fallbacks when disabled/unconfigured, and may still raise on
        # provider/runtime errors (network/auth), which we guard here.
        try:
            result = await self._llm_gen.generate(req)
        except Exception as exc:
            logger.warning(
                "llm_generation_failed_using_fallback",
                package=req.package,
                error=str(exc),
            )
            result = await self._rule_gen.generate(req)

        window_summary = (req.version_window_summary or "").strip()
        if window_summary:
            rs = (result.recommendation_summary or "").strip()
            if rs and not rs.startswith(window_summary):
                result = result.model_copy(
                    update={"recommendation_summary": f"{window_summary} | {rs}"}
                )

        _results_cache[req.library_id] = result
        logger.info(
            "recommendation_generated",
            library_id=req.library_id,
            package=req.package,
            decision=result.upgrade_recommended,
            generator=result.generator_used,
        )
        return result

    async def generate_batch(
        self, req: BatchRecommendationRequest
    ) -> BatchRecommendationResult:
        results: list[RecommendationResult] = []
        for lib in req.libraries:
            result = await self.generate_one(lib)
            results.append(result)

        yes = sum(1 for r in results if r.upgrade_recommended == UpgradeDecision.YES)
        no = sum(1 for r in results if r.upgrade_recommended == UpgradeDecision.NO)
        suf = sum(1 for r in results if r.upgrade_recommended == UpgradeDecision.SUFFICIENT)

        return BatchRecommendationResult(
            total=len(results),
            yes_count=yes,
            no_count=no,
            sufficient_count=suf,
            results=results,
        )

    def get_cached(self, library_id: int) -> RecommendationResult | None:
        return _results_cache.get(library_id)

    def list_all_cached(self) -> list[RecommendationResult]:
        return list(_results_cache.values())
