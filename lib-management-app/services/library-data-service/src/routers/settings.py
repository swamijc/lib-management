"""Router: /api/v1/settings  — LLM config, prompt templates, app settings."""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.orm import LlmConfig, LlmPromptTemplate, AppSetting
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

_PROVIDERS = ("openai", "azure_openai", "anthropic", "ollama")

def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Schemas ────────────────────────────────────────────────────────────────────

class LlmConfigOut(BaseModel):
    id: int | None = None
    provider: str = "openai"
    model_name: str = "gpt-4o"
    api_base_url: str | None = None
    api_key: str | None = None           # internal services only
    api_key_set: bool = False          # never return actual key
    api_version: str | None = None
    temperature: float = 0.3
    max_tokens: int = 1024
    timeout_seconds: int = 30
    enabled: bool = False
    updated_by: str | None = None
    updated_at: str | None = None


class LlmConfigIn(BaseModel):
    provider: str = Field("openai", pattern="^(openai|azure_openai|anthropic|ollama)$")
    model_name: str = Field("gpt-4o", min_length=1)
    api_base_url: str | None = None
    api_key: str | None = None         # None means "keep existing"
    api_version: str | None = None
    temperature: float = Field(0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(1024, ge=64, le=32768)
    timeout_seconds: int = Field(30, ge=5, le=300)
    enabled: bool = False
    updated_by: str | None = None


class PromptTemplateOut(BaseModel):
    id: int
    prompt_key: str
    template_text: str
    variables_hint: str | None
    version: int
    updated_by: str | None
    updated_at: str | None


class PromptTemplateIn(BaseModel):
    template_text: str = Field(min_length=1)
    variables_hint: str | None = None
    updated_by: str | None = None


class AppSettingOut(BaseModel):
    key: str
    value: str
    description: str | None
    is_sensitive: bool
    updated_by: str | None
    updated_at: str | None


class AppSettingIn(BaseModel):
    value: str
    updated_by: str | None = None


# ── LLM Config ─────────────────────────────────────────────────────────────────

@router.get("/llm", response_model=ApiResponse[LlmConfigOut])
async def get_llm_config(request: Request, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(LlmConfig).order_by(LlmConfig.id))).scalars().first()
    is_internal = request.headers.get("X-Internal-Service-Key") == settings.internal_service_key
    if row is None:
        # Return defaults — no row yet
        return ApiResponse(success=True, data=LlmConfigOut(), meta=_meta())
    return ApiResponse(
        success=True,
        data=LlmConfigOut(
            id=row.id,
            provider=row.provider,
            model_name=row.model_name,
            api_base_url=row.api_base_url,
            api_key=(row.api_key_encrypted if is_internal else None),
            api_key_set=bool(row.api_key_encrypted),
            api_version=row.api_version,
            temperature=row.temperature,
            max_tokens=row.max_tokens,
            timeout_seconds=row.timeout_seconds,
            enabled=bool(row.enabled),
            updated_by=row.updated_by,
            updated_at=row.updated_at,
        ),
        meta=_meta(),
    )


@router.put("/llm", response_model=ApiResponse[LlmConfigOut])
async def update_llm_config(body: LlmConfigIn, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(LlmConfig).order_by(LlmConfig.id))).scalars().first()
    now = _now()
    if row is None:
        row = LlmConfig(
            provider=body.provider,
            model_name=body.model_name,
            api_base_url=body.api_base_url,
            api_key_encrypted=body.api_key or "",
            api_version=body.api_version,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            timeout_seconds=body.timeout_seconds,
            enabled=int(body.enabled),
            updated_by=body.updated_by,
            updated_at=now,
        )
        db.add(row)
    else:
        row.provider = body.provider
        row.model_name = body.model_name
        row.api_base_url = body.api_base_url
        if body.api_key is not None:          # only update if explicitly provided
            row.api_key_encrypted = body.api_key
        row.api_version = body.api_version
        row.temperature = body.temperature
        row.max_tokens = body.max_tokens
        row.timeout_seconds = body.timeout_seconds
        row.enabled = int(body.enabled)
        row.updated_by = body.updated_by
        row.updated_at = now

    await db.commit()
    await db.refresh(row)
    return ApiResponse(
        success=True,
        data=LlmConfigOut(
            id=row.id, provider=row.provider, model_name=row.model_name,
            api_base_url=row.api_base_url, api_key_set=bool(row.api_key_encrypted),
            api_version=row.api_version, temperature=row.temperature,
            max_tokens=row.max_tokens, timeout_seconds=row.timeout_seconds,
            enabled=bool(row.enabled), updated_by=row.updated_by, updated_at=row.updated_at,
        ),
        meta=_meta(),
    )


# ── Prompt Templates ───────────────────────────────────────────────────────────

@router.get("/prompts", response_model=ApiResponse[list[PromptTemplateOut]])
async def list_prompts(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(LlmPromptTemplate).order_by(LlmPromptTemplate.prompt_key))).scalars().all()
    return ApiResponse(
        success=True,
        data=[PromptTemplateOut(
            id=r.id, prompt_key=r.prompt_key, template_text=r.template_text,
            variables_hint=r.variables_hint, version=r.version,
            updated_by=r.updated_by, updated_at=r.updated_at,
        ) for r in rows],
        meta=_meta(),
    )


@router.put("/prompts/{prompt_key}", response_model=ApiResponse[PromptTemplateOut])
async def upsert_prompt(prompt_key: str, body: PromptTemplateIn, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(LlmPromptTemplate).where(LlmPromptTemplate.prompt_key == prompt_key))).scalars().first()
    now = _now()
    if row is None:
        row = LlmPromptTemplate(
            prompt_key=prompt_key,
            template_text=body.template_text,
            variables_hint=body.variables_hint,
            version=1,
            updated_by=body.updated_by,
            updated_at=now,
        )
        db.add(row)
    else:
        row.template_text = body.template_text
        row.variables_hint = body.variables_hint
        row.version = row.version + 1
        row.updated_by = body.updated_by
        row.updated_at = now

    await db.commit()
    await db.refresh(row)
    return ApiResponse(
        success=True,
        data=PromptTemplateOut(
            id=row.id, prompt_key=row.prompt_key, template_text=row.template_text,
            variables_hint=row.variables_hint, version=row.version,
            updated_by=row.updated_by, updated_at=row.updated_at,
        ),
        meta=_meta(),
    )


# ── App Settings ───────────────────────────────────────────────────────────────

@router.get("/app", response_model=ApiResponse[list[AppSettingOut]])
async def list_app_settings(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AppSetting).order_by(AppSetting.key))).scalars().all()
    return ApiResponse(
        success=True,
        data=[AppSettingOut(
            key=r.key, value=r.value if not r.is_sensitive else "***",
            description=r.description, is_sensitive=bool(r.is_sensitive),
            updated_by=r.updated_by, updated_at=r.updated_at,
        ) for r in rows],
        meta=_meta(),
    )


@router.put("/app/{key}", response_model=ApiResponse[AppSettingOut])
async def update_app_setting(key: str, body: AppSettingIn, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalars().first()
    if row is None:
        # Upsert: create the key if it doesn't exist (used for custom config like priority_rules)
        row = AppSetting(key=key, value=body.value, updated_by=body.updated_by,
                         updated_at=_now(), is_sensitive=False)
        db.add(row)
    else:
        row.value = body.value
        row.updated_by = body.updated_by
        row.updated_at = _now()
    await db.commit()
    await db.refresh(row)
    return ApiResponse(
        success=True,
        data=AppSettingOut(
            key=row.key, value=row.value if not row.is_sensitive else "***",
            description=row.description, is_sensitive=bool(row.is_sensitive),
            updated_by=row.updated_by, updated_at=row.updated_at,
        ),
        meta=_meta(),
    )
