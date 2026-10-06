"""
Pydantic schemas for tenant user management (admin-only endpoints).
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.db.models.user import TenantRole


class UserRead(BaseModel):
    """Public view of a tenant user. Never includes hashed_password."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_verified: bool
    tenant_id: uuid.UUID | None
    tenant_role: TenantRole | None
    created_at: datetime
    last_login_at: datetime | None


class UserCreate(BaseModel):
    """Body for POST /users — tenant admin creates a new user."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(None, max_length=200)
    role: TenantRole = TenantRole.VIEWER


class UserUpdate(BaseModel):
    """Body for PATCH /users/{id}. All fields optional."""
    full_name: str | None = Field(None, max_length=200)
    role: TenantRole | None = None
    is_active: bool | None = None