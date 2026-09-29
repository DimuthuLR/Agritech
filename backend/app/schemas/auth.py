"""
Pydantic schemas for authentication endpoints.

These define what the API accepts and returns. They are intentionally
separate from ORM models so we can control exactly what's exposed.
"""
import uuid
from pydantic import BaseModel, EmailStr, Field

from app.db.models.user import TenantRole, PlatformRole


# --- Requests -----------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=256)


# --- Responses ----------------------------------------------------------------


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class MeResponse(BaseModel):
    """
    Public view of the current user. NEVER includes hashed_password.
    """
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_verified: bool

    # Exactly one of these pairs is populated: tenant user OR platform user.
    tenant_id: uuid.UUID | None
    tenant_role: TenantRole | None
    platform_role: PlatformRole | None

    model_config = {"from_attributes": True}  # allows .model_validate(orm_user)


class LoginResponse(TokenResponse):
    """Token response plus the user it belongs to — convenient for the frontend."""
    user: MeResponse