"""
User management endpoints — tenant-scoped.

Only tenant_admins can manage users. Rules enforced here:
  1. Tenant scoping — you can only see/manage users in your own tenant.
  2. Role gate — only tenant_admin can do any of this.
  3. No self-deactivation — prevents lockout.
  4. No self-demotion — same reason.
  5. Email uniqueness — enforced at the DB level, returned cleanly.

Feature flag: 'users' gates every endpoint in this file. A tenant on a
plan without user management can only ever have the accounts created
for them at onboarding.
"""
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_tenant_role, require_feature
from app.core.security import hash_password
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.schemas.user import UserRead, UserCreate, UserUpdate


log = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("", response_model=list[UserRead])
def list_users(
    user: User = Depends(require_tenant_role(TenantRole.TENANT_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    List all users in the caller's tenant, oldest first.
    Only tenant_admins can call this.
    """
    require_feature(db, user.tenant_id, "users")

    return (
        db.query(User)
        .filter(User.tenant_id == user.tenant_id)
        .order_by(User.created_at.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    user: User = Depends(require_tenant_role(TenantRole.TENANT_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Create a new user in the caller's tenant.

    The new user's tenant_id is derived from the caller's token — the
    client cannot place a user in a different tenant.
    """
    require_feature(db, user.tenant_id, "users")

    # Fast path: check email uniqueness before hitting the DB constraint
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email {payload.email!r} already exists",
        )

    new_user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_active=True,
        is_verified=True,           # admin-created; no email flow yet
        tenant_id=user.tenant_id,   # derived from token
        tenant_role=payload.role,
        platform_role=None,          # tenants can't create platform users
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        log.warning(f"create_user integrity error: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already in use",
        )
    db.refresh(new_user)
    return new_user


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    current: User = Depends(require_tenant_role(TenantRole.TENANT_ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Update a user's role, name, or active status.

    Self-lockout protection: you cannot deactivate or demote yourself.
    """
    require_feature(db, current.tenant_id, "users")

    target = (
        db.query(User)
        .filter(User.id == user_id, User.tenant_id == current.tenant_id)
        .first()
    )
    if target is None:
        # 404 whether the user doesn't exist OR belongs to another tenant.
        # This prevents cross-tenant enumeration.
        raise HTTPException(status_code=404, detail="User not found")

    # Self-protection
    if target.id == current.id:
        if payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account",
            )
        if payload.role is not None and payload.role != TenantRole.TENANT_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot change your own role from tenant_admin",
            )

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "role":
            target.tenant_role = value
        elif key == "full_name":
            target.full_name = value
        elif key == "is_active":
            target.is_active = value

    db.commit()
    db.refresh(target)
    return target