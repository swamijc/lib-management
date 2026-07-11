"""
LLM recommendation generator — uses litellm for provider-agnostic LLM calls.

At runtime the generator first tries to load system_prompt / user_template from
the llm_prompt_templates table in the shared SQLite DB (written by the Settings
UI).  If those rows are absent it falls back to the hardcoded defaults below.
"""
from __future__ import annotations
import json
import os
import re
import sqlite3
from collections import defaultdict
from urllib.parse import urljoin

import structlog

from ..config import settings
from ..models.schemas import (
    GeneratorType,
    RecommendationRequest,
    RecommendationResult,
    UpgradeDecision,
)
from .base import RecommendationGenerator
from .rule_based import RuleBasedGenerator

logger = structlog.get_logger(__name__)


def _infer_priority(decision: UpgradeDecision, summary: str) -> str | None:
    m = re.match(r"^\[(CRITICAL|HIGH|MODERATE|LOW|NONE)\]", summary or "")
    if m:
        return m.group(1)
    if "manual review" in (summary or "").lower():
        return "MANUAL_REVIEW"
    if decision == UpgradeDecision.SUFFICIENT:
        return "NONE"
    if decision == UpgradeDecision.YES:
        return "HIGH"
    return "MANUAL_REVIEW"

_DEFAULT_SYSTEM_PROMPT = (
    "You are a software library upgrade advisor for enterprise mobile SDK teams. "
    "Analyse the library details provided and return ONLY a strict JSON object with exactly "
    "these keys: upgrade_recommended (one of: Yes, No, Sufficient), "
    "upgrade_pros (list of strings), upgrade_cons (list of strings), "
    "no_upgrade_pros (list of strings), no_upgrade_cons (list of strings), "
    "recommendation_summary (concise paragraph). "
    "Be specific and technical. Do not include markdown, explanations, or code fences."
)

_DEFAULT_USER_TEMPLATE = """\
Library: {package}
Platform: {platform}
Current version: {current}
Latest version: {latest}
Update priority: {update_needed}
Library status: {lib_status}
New version released: {new_version}
Version compare status: {version_status}
Needs manual review: {needs_manual_review}
Version window summary: {version_window_summary}
Release notes: {release_notes}
Deprecation notes: {deprecation_notes}

Generate the JSON recommendation object."""

_REC_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "upgrade_recommended",
        "upgrade_pros",
        "upgrade_cons",
        "no_upgrade_pros",
        "no_upgrade_cons",
        "recommendation_summary",
    ],
    "properties": {
        "upgrade_recommended": {
            "type": "string",
            "enum": ["Yes", "No", "Sufficient"],
        },
        "upgrade_pros": {"type": "array", "items": {"type": "string"}},
        "upgrade_cons": {"type": "array", "items": {"type": "string"}},
        "no_upgrade_pros": {"type": "array", "items": {"type": "string"}},
        "no_upgrade_cons": {"type": "array", "items": {"type": "string"}},
        "recommendation_summary": {"type": "string"},
    },
}


def _load_prompt_from_db(key: str, default: str) -> str:
    """Reads a prompt template from llm_prompt_templates table; returns default on any error."""
    try:
        db_url = getattr(settings, "database_url", "")
        if "sqlite" in db_url:
            db_path = db_url.split("///", 1)[-1]
        else:
            return default
        conn = sqlite3.connect(db_path, timeout=2.0)
        row = conn.execute(
            "SELECT template_text FROM llm_prompt_templates WHERE prompt_key=?", (key,)
        ).fetchone()
        conn.close()
        if row and row[0]:
            logger.info("llm_prompt_loaded_from_db", key=key)
            return row[0]
    except Exception as exc:
        logger.debug("llm_prompt_db_load_failed", key=key, error=str(exc))
    return default


async def _log_usage_async(
    library_id: int | None,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    run_id: str | None = None,
) -> None:
    """Fire-and-forget: POST usage stats to library-data-service. Never raises."""
    try:
        import httpx
        payload = {
            "library_id": library_id,
            "run_id": run_id,
            "model": model,
            "prompt_key": "recommendation",
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "latency_ms": latency_ms,
        }
        base = settings.library_data_service_url
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{base}/api/v1/llm/log",
                json=payload,
                headers={"X-Internal-Service-Key": settings.internal_service_key},
            )
    except Exception as exc:
        logger.debug("llm_usage_log_failed", error=str(exc))


class LLMGenerator(RecommendationGenerator):
    """
    Calls the configured LLM via litellm.
    Falls back to RuleBasedGenerator if LLM parsing fails.
    """

    def __init__(self) -> None:
        self._fallback = RuleBasedGenerator()

    @property
    def generator_type(self) -> str:
        return GeneratorType.LLM

    async def _load_runtime_llm_config(self) -> dict:
        """Load effective LLM config from library-data settings; fallback to env config."""
        cfg = {
            "enabled": settings.llm_enabled,
            "provider": (settings.llm_provider or "").strip().lower(),
            "model": settings.llm_model,
            "api_key": settings.llm_api_key or "",
            "api_base": settings.llm_api_base or "",
            "temperature": settings.llm_temperature,
            "max_tokens": settings.llm_max_tokens,
            "timeout": settings.llm_timeout_seconds,
        }
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{settings.library_data_service_url}/api/v1/settings/llm",
                    headers={"X-Internal-Service-Key": settings.internal_service_key},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    cfg.update({
                        "enabled": bool(data.get("enabled", False)),
                        "provider": str(data.get("provider") or cfg["provider"]).strip().lower(),
                        "model": data.get("model_name") or cfg["model"],
                        "api_key": data.get("api_key") or cfg["api_key"],
                        "api_base": data.get("api_base_url") or cfg["api_base"],
                        "temperature": data.get("temperature", cfg["temperature"]),
                        "max_tokens": data.get("max_tokens", cfg["max_tokens"]),
                        "timeout": data.get("timeout_seconds", cfg["timeout"]),
                    })
        except Exception as exc:
            logger.debug("llm_runtime_config_load_failed", error=str(exc))

        # Env fallback/override support for local .env usage.
        # Accept both LLM_API_KEY and LLM_KEY for backward compatibility.
        env_key = (os.getenv("LLM_API_KEY") or os.getenv("LLM_KEY") or "").strip()
        env_provider = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()
        env_model = (os.getenv("LLM_MODEL") or "").strip()

        if not cfg.get("api_key") and env_key:
            cfg["api_key"] = env_key
        if not cfg.get("provider") and env_provider:
            cfg["provider"] = env_provider
        if not cfg.get("model") and env_model:
            cfg["model"] = env_model

        # If DB has LLM disabled/unset but env key exists, allow env-based runtime.
        if not cfg.get("enabled") and cfg.get("provider") and cfg.get("api_key"):
            cfg["enabled"] = True
        return cfg

    async def _call_openai_responses_api(self, model: str, api_key: str, api_base: str,
                                         system_prompt: str, user_prompt: str,
                                         temperature: float, max_tokens: int, timeout_s: float) -> tuple[str, int, int]:
        import httpx
        if settings.llm_ssl_verify:
            try:
                import certifi
                verify = certifi.where()
            except Exception:
                verify = True
        else:
            verify = False

        base = (api_base or "https://api.openai.com/v1/").strip()
        if not base.endswith("/"):
            base += "/"
        endpoint = urljoin(base, "responses")

        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "library_recommendation",
                    "schema": _REC_JSON_SCHEMA,
                    "strict": True,
                }
            },
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "store": False,
        }

        async with httpx.AsyncClient(timeout=timeout_s, verify=verify) as client:
            resp = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        text = data.get("output_text") or ""
        if not text:
            output = data.get("output") or []
            for item in output:
                for content in item.get("content") or []:
                    txt = content.get("text")
                    if txt:
                        text += txt
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("input_tokens") or 0)
        completion_tokens = int(usage.get("output_tokens") or 0)
        return text, prompt_tokens, completion_tokens

    async def _repair_to_json(self, runtime: dict, raw_text: str) -> dict | None:
        """Best-effort one-shot repair: convert non-JSON model output to strict JSON."""
        repair_system = (
            "Convert the user text into strict JSON for a library recommendation. "
            "Return ONLY JSON with keys: upgrade_recommended, upgrade_pros, upgrade_cons, "
            "no_upgrade_pros, no_upgrade_cons, recommendation_summary."
        )
        repair_user = f"Text to convert:\n{raw_text}"
        try:
            if runtime["provider"] == "openai":
                repaired, _, _ = await self._call_openai_responses_api(
                    model=runtime["model"],
                    api_key=runtime["api_key"],
                    api_base=runtime.get("api_base") or "",
                    system_prompt=repair_system,
                    user_prompt=repair_user,
                    temperature=0.0,
                    max_tokens=min(int(runtime["max_tokens"]), 700),
                    timeout_s=float(runtime["timeout"]),
                )
            else:
                import litellm
                resp = await litellm.acompletion(
                    model=runtime["model"],
                    messages=[
                        {"role": "system", "content": repair_system},
                        {"role": "user", "content": repair_user},
                    ],
                    temperature=0.0,
                    max_tokens=min(int(runtime["max_tokens"]), 700),
                    timeout=runtime["timeout"],
                    api_key=runtime["api_key"] or None,
                    api_base=runtime.get("api_base") or None,
                )
                repaired = resp.choices[0].message.content or ""
            return self._parse_llm_response(repaired)
        except Exception:
            return None

    async def generate(self, req: RecommendationRequest) -> RecommendationResult:
        runtime = await self._load_runtime_llm_config()
        if not runtime.get("enabled") or not runtime.get("provider") or not runtime.get("api_key"):
            return await self._fallback.generate(req)

        import litellm  # imported here so missing package doesn't break service startup

        system_prompt = _load_prompt_from_db("system_prompt", _DEFAULT_SYSTEM_PROMPT)
        user_template = _load_prompt_from_db("user_template", _DEFAULT_USER_TEMPLATE)

        prompt_values = defaultdict(
            str,
            {
                "package": req.package,
                "platform": req.platform,
                "current": req.current_version,
                "latest": req.latest_version,
                "update_needed": req.update_needed or "Unknown",
                "lib_status": req.library_status or "Unknown",
                "new_version": str(req.new_version_released),
                "version_status": req.version_status or "unknown",
                "needs_manual_review": str(req.needs_manual_review),
                "version_window_summary": (req.version_window_summary or "none")[:700],
                "release_notes": (req.release_notes or "Not available")[:2000],
                "deprecation_notes": (req.deprecation_notes or "None")[:500],
            },
        )
        user_prompt = user_template.format_map(prompt_values)

        kwargs: dict = dict(
            model=runtime["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=runtime["temperature"],
            max_tokens=runtime["max_tokens"],
            timeout=runtime["timeout"],
            api_key=runtime["api_key"] or None,
        )
        if runtime.get("api_base"):
            kwargs["api_base"] = runtime["api_base"]

        logger.info("llm_call_start", package=req.package, model=runtime["model"], provider=runtime["provider"])
        t0 = __import__("time").monotonic()
        if runtime["provider"] == "openai":
            raw_text, prompt_tokens, completion_tokens = await self._call_openai_responses_api(
                model=runtime["model"],
                api_key=runtime["api_key"],
                api_base=runtime.get("api_base") or "",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=float(runtime["temperature"]),
                max_tokens=int(runtime["max_tokens"]),
                timeout_s=float(runtime["timeout"]),
            )
        else:
            response = await litellm.acompletion(**kwargs)
            raw_text = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        latency_ms = int((__import__("time").monotonic() - t0) * 1000)
        logger.info("llm_call_done", package=req.package, chars=len(raw_text),
                    tokens=prompt_tokens + completion_tokens, latency_ms=latency_ms)

        # Log usage asynchronously — best effort, never blocks recommendation
        import asyncio
        asyncio.ensure_future(_log_usage_async(
            library_id=req.library_id,
            model=runtime["model"],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        ))

        parsed = self._parse_llm_response(raw_text)
        if parsed is None:
            logger.warning("llm_parse_failed_using_fallback", package=req.package)
            repaired = await self._repair_to_json(runtime, raw_text)
            if repaired is None:
                return await self._fallback.generate(req)
            parsed = repaired

        decision_raw = parsed.get("upgrade_recommended", "No")
        try:
            decision = UpgradeDecision(decision_raw)
        except ValueError:
            decision = UpgradeDecision.NO

        return RecommendationResult(
            library_id=req.library_id,
            package=req.package,
            platform=req.platform,
            current_version=req.current_version,
            latest_version=req.latest_version,
            priority=_infer_priority(decision, parsed.get("recommendation_summary", "")),
            upgrade_recommended=decision,
            upgrade_pros=parsed.get("upgrade_pros", []),
            upgrade_cons=parsed.get("upgrade_cons", []),
            no_upgrade_pros=parsed.get("no_upgrade_pros", []),
            no_upgrade_cons=parsed.get("no_upgrade_cons", []),
            recommendation_summary=parsed.get("recommendation_summary", ""),
            generator_used=GeneratorType.LLM,
        )

    @staticmethod
    def _parse_llm_response(text: str) -> dict | None:
        """Extract and parse JSON from LLM response (handles markdown code fences)."""
        stripped = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group())
            required = {"upgrade_recommended", "upgrade_pros", "upgrade_cons",
                        "no_upgrade_pros", "no_upgrade_cons", "recommendation_summary"}
            if not required.issubset(data.keys()):
                return None
            if data.get("upgrade_recommended") not in {"Yes", "No", "Sufficient"}:
                return None
            for k in ("upgrade_pros", "upgrade_cons", "no_upgrade_pros", "no_upgrade_cons"):
                if not isinstance(data.get(k), list) or any(not isinstance(i, str) for i in data.get(k, [])):
                    return None
            if not isinstance(data.get("recommendation_summary"), str):
                return None
            return data
        except (json.JSONDecodeError, TypeError):
            return None
