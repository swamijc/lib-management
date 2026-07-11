"""
Unit tests for RuleBasedGenerator — all 6 recommendation rules.
"""
from __future__ import annotations
import pytest
from src.models.schemas import RecommendationRequest, UpgradeDecision
from src.generators.rule_based import RuleBasedGenerator


def _req(**overrides) -> RecommendationRequest:
    base = dict(
        library_id=1,
        package="com.example:lib",
        platform="Android",
        current_version="1.0.0",
        latest_version="2.0.0",
        update_needed="Mandatory",
        library_status="Active",
        new_version_released=True,
        version_status="newer",
    )
    return RecommendationRequest(**(base | overrides))


@pytest.fixture
def gen():
    return RuleBasedGenerator()


class TestRuleBasedGenerator:

    @pytest.mark.asyncio
    async def test_deprecated_library_returns_yes(self, gen):
        result = await gen.generate(_req(library_status="Deprecated"))
        assert result.upgrade_recommended == UpgradeDecision.YES
        assert len(result.upgrade_pros) >= 1
        assert "deprecated" in result.recommendation_summary.lower()

    @pytest.mark.asyncio
    async def test_mandatory_newer_returns_yes(self, gen):
        result = await gen.generate(_req(update_needed="Mandatory", new_version_released=True))
        assert result.upgrade_recommended == UpgradeDecision.YES
        assert result.upgrade_cons  # has at least one con

    @pytest.mark.asyncio
    async def test_recommended_newer_returns_yes(self, gen):
        result = await gen.generate(_req(update_needed="Recommended", new_version_released=True))
        assert result.upgrade_recommended == UpgradeDecision.YES

    @pytest.mark.asyncio
    async def test_up_to_date_returns_sufficient(self, gen):
        result = await gen.generate(
            _req(current_version="2.0.0", latest_version="2.0.0", new_version_released=False)
        )
        assert result.upgrade_recommended == UpgradeDecision.SUFFICIENT
        assert "up-to-date" in result.recommendation_summary.lower()

    @pytest.mark.asyncio
    async def test_update_needed_none_returns_no(self, gen):
        result = await gen.generate(_req(update_needed="None", new_version_released=False))
        assert result.upgrade_recommended == UpgradeDecision.SUFFICIENT

    @pytest.mark.asyncio
    async def test_manual_review_returns_no(self, gen):
        result = await gen.generate(
            _req(current_version="ViaSPM", needs_manual_review=True)
        )
        assert result.upgrade_recommended == UpgradeDecision.NO
        assert "manual review" in result.recommendation_summary.lower()

    @pytest.mark.asyncio
    async def test_result_has_all_required_fields(self, gen):
        result = await gen.generate(_req())
        assert result.library_id == 1
        assert result.package == "com.example:lib"
        assert result.recommendation_summary
        assert result.generator_used == "rule_based"

    @pytest.mark.asyncio
    async def test_deprecation_notes_included_in_pros(self, gen):
        result = await gen.generate(
            _req(library_status="Deprecated", deprecation_notes="Use NewLib instead")
        )
        combined = " ".join(result.upgrade_pros)
        assert "Use NewLib" in combined
