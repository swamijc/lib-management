"""
API Gateway — auth router.

Endpoints:
  POST /auth/token            — login → JWT
  GET  /auth/me               — current user info
  GET  /auth/users            — list all users (admin only)
  POST /auth/users            — create user (admin only)
  PUT  /auth/users/{id}       — update user (admin: all fields; self: limited)
  DELETE /auth/users/{id}     — deactivate user (admin only)
  POST /auth/change-password  — change own password
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from ..auth.dependencies import get_current_user
from ..auth.jwt_handler import create_access_token
from ..auth.user_db import (
    authenticate_user, change_password, create_user, list_users, update_user,
)
from ..config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    expires_in_minutes: int


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    password: str = Field(..., min_length=8)
    full_name: str | None = None
    role: str = Field("viewer", pattern="^(admin|viewer)$")


class UserUpdateRequest(BaseModel):
    email: str | None = None
    full_name: str | None = None
    role: str | None = Field(None, pattern="^(admin|viewer)$")
    is_active: bool | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)


# ── Auth endpoints ─────────────────────────────────────────────────────────────

@router.post("/token", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    user = authenticate_user(form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=user["username"], role=user["role"])
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
        expires_in_minutes=settings.jwt_expire_minutes,
    )


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)) -> dict:
    return {"username": user["username"], "role": user["role"]}


# ── User Management (admin only) ───────────────────────────────────────────────

@router.get("/users")
async def get_users(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"users": list_users()}


@router.post("/users", status_code=201)
async def add_user(
    body: UserCreateRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    result = create_user(
        username=body.username,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        role=body.role,
    )
    if isinstance(result, str):
        raise HTTPException(status_code=400, detail=result)
    return {"user": result}


@router.put("/users/{user_id}")
async def edit_user(
    user_id: int,
    body: UserUpdateRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    fields = body.model_dump(exclude_none=True)
    if "is_active" in fields:
        fields["is_active"] = int(fields["is_active"])
    result = update_user(user_id, **fields)
    if isinstance(result, str):
        raise HTTPException(status_code=400 if "not found" not in result.lower() else 404, detail=result)
    return {"user": result}


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    result = update_user(user_id, is_active=0)
    if isinstance(result, str):
        raise HTTPException(status_code=404 if "not found" in result.lower() else 400, detail=result)
    return {"deactivated": user_id}


@router.delete("/users/{user_id}/permanent")
async def delete_user_permanent(
    user_id: int,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Permanently delete a user. Cannot delete root admin or yourself."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    # Look up target user to enforce guards
    users = list_users()
    target = next((u for u in users if u["id"] == user_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target["username"] == "admin":
        raise HTTPException(status_code=400, detail="Root admin account cannot be deleted")
    if target["username"] == current_user["username"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    from ..auth.user_db import delete_user
    result = delete_user(user_id)
    if isinstance(result, str):
        raise HTTPException(status_code=400, detail=result)
    return {"deleted": user_id}


@router.post("/change-password")
async def do_change_password(
    body: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Any authenticated user can change their own password."""
    users = list_users()
    user_row = next((u for u in users if u["username"] == current_user["username"]), None)
    if user_row is None:
        raise HTTPException(status_code=404, detail="User not found")
    result = change_password(user_row["id"], body.old_password, body.new_password)
    if result is not True:
        raise HTTPException(status_code=400, detail=str(result))
    return {"message": "Password changed successfully"}

