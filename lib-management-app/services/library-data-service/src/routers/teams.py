"""Router: /api/v1/teams — squad/team management and library ownership."""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.orm import ApplicationTeam, Library, LibraryOwnership
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Schemas ────────────────────────────────────────────────────────────────────

class TeamCreate(BaseModel):
    team_name: str = Field(..., min_length=1)
    team_email: str | None = None
    teams_channel: str | None = None


class TeamUpdate(BaseModel):
    team_email: str | None = None
    teams_channel: str | None = None


class OwnershipAssign(BaseModel):
    library_id: int
    team_id: int
    is_primary: bool = True
    assigned_by: str


# ── Teams CRUD ─────────────────────────────────────────────────────────────────

@router.get("", response_model=ApiResponse[list[dict]])
async def list_teams(db: AsyncSession = Depends(get_db)) -> ApiResponse[list[dict]]:
    """List all teams with library counts."""
    teams = (await db.execute(
        select(ApplicationTeam).order_by(ApplicationTeam.team_name)
    )).scalars().all()
    result = []
    for t in teams:
        owns = (await db.execute(
            select(LibraryOwnership).where(LibraryOwnership.team_id == t.id)
        )).scalars().all()
        result.append({
            "id": t.id, "team_name": t.team_name,
            "team_email": t.team_email, "teams_channel": t.teams_channel,
            "created_at": t.created_at, "library_count": len(owns),
        })
    return ApiResponse.ok(data=result, meta=_meta())


@router.get("/{team_id}", response_model=ApiResponse[dict])
async def get_team(team_id: int, db: AsyncSession = Depends(get_db)) -> ApiResponse[dict]:
    team = await db.get(ApplicationTeam, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    owns = (await db.execute(
        select(LibraryOwnership, Library.package, Library.sdk_name,
               Library.platform, Library.current_version, Library.update_needed,
               Library.status, Library.alert_priority)
        .join(Library, Library.id == LibraryOwnership.library_id, isouter=True)
        .where(LibraryOwnership.team_id == team_id)
    )).all()
    libraries = [
        {
            "library_id":   r.LibraryOwnership.library_id,
            "package":      r.package, "sdk_name": r.sdk_name,
            "platform":     r.platform, "current_version": r.current_version,
            "update_needed":r.update_needed, "status": r.status,
            "alert_priority":r.alert_priority,
            "is_primary":   bool(r.LibraryOwnership.is_primary),
            "assigned_by":  r.LibraryOwnership.assigned_by,
            "assigned_at":  r.LibraryOwnership.assigned_at,
        }
        for r in owns
    ]
    mandatory = sum(1 for l in libraries if (l.get("update_needed") or "").lower() == "mandatory")
    recommended = sum(1 for l in libraries if (l.get("update_needed") or "").lower() == "recommended")
    return ApiResponse.ok(
        data={
            "id": team.id, "team_name": team.team_name,
            "team_email": team.team_email, "teams_channel": team.teams_channel,
            "created_at": team.created_at,
            "library_count": len(libraries),
            "mandatory_count": mandatory, "recommended_count": recommended,
            "libraries": libraries,
        },
        meta=_meta()
    )


@router.post("", response_model=ApiResponse[dict], status_code=201)
async def create_team(body: TeamCreate, db: AsyncSession = Depends(get_db)) -> ApiResponse[dict]:
    existing = (await db.execute(
        select(ApplicationTeam).where(ApplicationTeam.team_name == body.team_name)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"Team '{body.team_name}' already exists")
    team = ApplicationTeam(
        team_name=body.team_name, team_email=body.team_email,
        teams_channel=body.teams_channel, created_at=_now(),
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return ApiResponse.ok(
        data={"id": team.id, "team_name": team.team_name,
              "team_email": team.team_email, "teams_channel": team.teams_channel,
              "created_at": team.created_at, "library_count": 0},
        meta=_meta()
    )


@router.put("/{team_id}", response_model=ApiResponse[dict])
async def update_team(team_id: int, body: TeamUpdate, db: AsyncSession = Depends(get_db)) -> ApiResponse[dict]:
    team = await db.get(ApplicationTeam, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    if body.team_email is not None:  team.team_email = body.team_email
    if body.teams_channel is not None: team.teams_channel = body.teams_channel
    await db.commit()
    return ApiResponse.ok(
        data={"id": team.id, "team_name": team.team_name,
              "team_email": team.team_email, "teams_channel": team.teams_channel},
        meta=_meta()
    )


@router.delete("/{team_id}", response_model=ApiResponse[dict])
async def delete_team(team_id: int, db: AsyncSession = Depends(get_db)) -> ApiResponse[dict]:
    team = await db.get(ApplicationTeam, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    await db.delete(team)
    await db.commit()
    return ApiResponse.ok(data={"deleted": team_id}, meta=_meta())


# ── Library Ownership ──────────────────────────────────────────────────────────

@router.post("/assign", response_model=ApiResponse[dict], status_code=201)
async def assign_library(body: OwnershipAssign, db: AsyncSession = Depends(get_db)) -> ApiResponse[dict]:
    """Assign a library to a team."""
    lib = await db.get(Library, body.library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail=f"Library {body.library_id} not found")
    team = await db.get(ApplicationTeam, body.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team {body.team_id} not found")
    existing = (await db.execute(
        select(LibraryOwnership)
        .where(LibraryOwnership.library_id == body.library_id)
        .where(LibraryOwnership.team_id == body.team_id)
    )).scalar_one_or_none()
    if existing:
        existing.is_primary = int(body.is_primary)
        existing.assigned_by = body.assigned_by
        existing.assigned_at = _now()
    else:
        db.add(LibraryOwnership(
            library_id=body.library_id, team_id=body.team_id,
            is_primary=int(body.is_primary), assigned_by=body.assigned_by,
            assigned_at=_now(),
        ))
    await db.commit()
    return ApiResponse.ok(
        data={"library_id": body.library_id, "team_id": body.team_id,
              "team_name": team.team_name, "package": lib.package,
              "is_primary": body.is_primary},
        meta=_meta()
    )


@router.delete("/assign/{library_id}/{team_id}", response_model=ApiResponse[dict])
async def unassign_library(library_id: int, team_id: int, db: AsyncSession = Depends(get_db)) -> ApiResponse[dict]:
    own = (await db.execute(
        select(LibraryOwnership)
        .where(LibraryOwnership.library_id == library_id)
        .where(LibraryOwnership.team_id == team_id)
    )).scalar_one_or_none()
    if own is None:
        raise HTTPException(status_code=404, detail="Ownership not found")
    await db.delete(own)
    await db.commit()
    return ApiResponse.ok(data={"removed": {"library_id": library_id, "team_id": team_id}}, meta=_meta())


@router.get("/library/{library_id}", response_model=ApiResponse[list[dict]])
async def get_library_teams(library_id: int, db: AsyncSession = Depends(get_db)) -> ApiResponse[list[dict]]:
    """Get all teams owning a specific library."""
    rows = (await db.execute(
        select(LibraryOwnership, ApplicationTeam.team_name, ApplicationTeam.team_email)
        .join(ApplicationTeam, ApplicationTeam.id == LibraryOwnership.team_id, isouter=True)
        .where(LibraryOwnership.library_id == library_id)
    )).all()
    data = [
        {"team_id": r.LibraryOwnership.team_id, "team_name": r.team_name,
         "team_email": r.team_email, "is_primary": bool(r.LibraryOwnership.is_primary),
         "assigned_by": r.LibraryOwnership.assigned_by, "assigned_at": r.LibraryOwnership.assigned_at}
        for r in rows
    ]
    return ApiResponse.ok(data=data, meta=_meta())
