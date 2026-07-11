"""
Unit tests for LLMGenerator — mocked litellm calls + parser.
litellm is injected into sys.modules so tests run without installing the package.
"""
from __future__ import annotations
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Inject a mock litellm module so patch("litellm.acompletion") works without
# requiring the real package to be installed in the test environment.
if "litellm" not in sys.modules:
    sys.modules["litellm"] = MagicMock()

import pytest

from src.models.schemas import RecommendationRequest, UpgradeDecision
from src.generators.llm_generator import LLMGenerator


def _req(**overrides) -> RecommendationRequest:
    base = dict(
        library_id=1, package="com.example:lib", platform="Android",
        current_version="1.0.0", latest_version="2.0.0",
        update_needed="Mandatory", library_status="Active",
        new_version_released=True,
    )
    return RecommendationRequest(**(base | overrides))


def _llm_response(body: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(body)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


_VALID_LLM_BODY = {
    "upgrade_recommended": "Yes",
    "upgrade_pros": ["Security fix", "Performance improvement"],
    "upgrade_cons": ["Requires testing"],
    "no_upgrade_pros": ["Stable"],
    "no_upgrade_cons": ["Missing security patch"],
    "recommendation_summary": "Upgrade recommended due to security improvements.",
}


class TestLLMGenerator:

    @pytest.fixture
    def gen(self):
        return LLMGenerator()

    @pytest.fixture(autouse=True)
    def _force_llm_runtime(self):
        cfg = {
            "enabled": True,
            "provider": "litellm",
            "model": "gpt-4o-mini",
            "api_key": "test-key",
            "api_base": "",
            "temperature": 0.1,
            "max_tokens": 600,
            "timeout": 10,
        }
        with patch.object(LLMGenerator, "_load_runtime_llm_config", new_callable=AsyncMock) as mock_cfg:
            mock_cfg.return_value = cfg
            yield

    @pytest.mark.asyncio
    async def test_valid_llm_response_parsed_correctly(self, gen):
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _llm_response(_VALID_LLM_BODY)
            result = await gen.generate(_req())

        assert result.upgrade_recommended == UpgradeDecision.YES
        assert "Security fix" in result.upgrade_pros
        assert result.generator_used == "llm"
        assert result.recommendation_summary

    @pytest.mark.asyncio
    async def test_llm_response_with_markdown_fences(self, gen):
        body_str = "```json\n" + json.dumps(_VALID_LLM_BODY) + "\n```"
        msg = MagicMock()
        msg.content = body_str
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = resp
            result = await gen.generate(_req())

        assert result.upgrade_recommended == UpgradeDecision.YES

    @pytest.mark.asyncio
    async def test_invalid_llm_response_falls_back_to_rule_based(self, gen):
        msg = MagicMock()
        msg.content = "This is not JSON at all."
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = resp
            result = await gen.generate(_req(update_needed="Mandatory", new_version_released=True))

        # Falls back to rule-based result on invalid LLM content
        assert result.generator_used == "rule_based"
        assert result.upgrade_recommended == UpgradeDecision.YES  # rule-based: mandatory

    @pytest.mark.asyncio
    async def test_llm_exception_bubbles_up(self, gen):
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("API unreachable")
            with pytest.raises(RuntimeError):
                await gen.generate(_req())

    def test_parse_valid_json(self, gen):
        result = gen._parse_llm_response(json.dumps(_VALID_LLM_BODY))
        assert result is not None
        assert result["upgrade_recommended"] == "Yes"

    def test_parse_missing_keys_returns_none(self, gen):
        result = gen._parse_llm_response(json.dumps({"upgrade_recommended": "Yes"}))
        assert result is None

    def test_parse_non_json_returns_none(self, gen):
        result = gen._parse_llm_response("Sorry, I cannot help with that.")
        assert result is None
