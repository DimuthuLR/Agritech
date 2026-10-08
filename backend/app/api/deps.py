"""
Authentication and authorization dependencies for FastAPI routes.

Usage in a route:

    from app.api.deps import current_user, require_tenant_role
    from app.db.models.user import User, TenantRole

    @router.get("/farms")
    def list_farms(
        user: User = Depends(current_user),
        _: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    ):
        ...
"""
import logging
import uuid
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_token
from app.db.models.support_session import SupportSession
from app.db.models.tenant import Tenant
from app.db.models.user import User, TenantRole, PlatformRole
from app.db.session import get_db
from app.services import features_service as fs


log = logging.getLogger(__name__)


# OAuth2PasswordBearer tells FastAPI to expect "Authorization: Bearer <token>".
# tokenUrl is only used by Swagger UI's "Authorize" button.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

# Role hierarchies — higher index = more privileges.
TENANT_ROLE_ORDER = {
    TenantRole.VIEWER: 0,
    TenantRole.OPERATOR: 1,
    TenantRole.AGRONOMIST: 2,
    TenantRole.TENANT_ADMIN: 3,
}

PLATFORM_ROLE_ORDER = {
    PlatformRole.SUPPORT_AGENT: 0,
    PlatformRole.PLATFORM_ADMIN: 1,
    PlatformRole.SUPER_ADMIN: 2,
}


# --- Core: authenticated user -------------------------------------------------


def current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve the Bearer token into a User object.

    Accepts both normal access tokens and impersonation tokens.
    Impersonation tokens resolve to the TARGET user, but validate the
    underlying support session is still open and log every request.

    Raises 401 if: no token, bad token, expired, or user not found/inactive.
    Raises 403 if: user inactive, tenant suspended, or session ended.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(
            token, expected_types={"access", "impersonation"}
        )
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = payload.get("sub")
    try:
        user_id = uuid.UUID(user_id_str)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    # --- Impersonation path ---
    # If this is an impersonation token, verify the underlying session
    # is still open. Every impersonated request gets a WARNING log line
    # so the audit trail shows the actual actions taken during a session.
    if payload.get("typ") == "impersonation":
        session_id_str = payload.get("support_session_id")
        try:
            session_id = uuid.UUID(session_id_str)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid impersonation session id",
            )

        session = db.get(SupportSession, session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Impersonation session not found",
            )
        if session.ended_at is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Impersonation session has ended. Start a new one.",
            )
        if session.target_user_id != user.id:
            # Token/session mismatch — should never happen, but be strict.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Impersonation session mismatch",
            )

        log.warning(
            f"[impersonation] session={session.id} "
            f"actor_user={session.platform_user_id} "
            f"acting_as={user.email} ({user.id})"
        )

    return user


# --- Role guards --------------------------------------------------------------


def require_tenant_role(min_role: TenantRole) -> Callable[[User], User]:
    """
    Factory: returns a dependency that ensures the current user is a TENANT
    user with at least the given role. Platform users are rejected.

    Also enforces tenant suspension: if the caller's tenant has
    is_active=False, this returns 403. Auth endpoints (login, /me) bypass
    this check because they use current_user directly, so suspended users
    can still log in and see a "suspended" message.
    """
    min_level = TENANT_ROLE_ORDER[min_role]

    def _dep(
        user: User = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if user.tenant_id is None or user.tenant_role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant user role required",
            )
        if TENANT_ROLE_ORDER[user.tenant_role] < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires tenant role >= {min_role.value}",
            )

        # Tenant suspension check.
        tenant = db.get(Tenant, user.tenant_id)
        if tenant is not None and not tenant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Your account has been suspended. "
                    "Please contact support to restore access."
                ),
            )

        return user

    return _dep


def require_platform_role(min_role: PlatformRole) -> Callable[[User], User]:
    """
    Factory: returns a dependency that ensures the current user is a PLATFORM
    user with at least the given role. Tenant users are rejected.

    Impersonation tokens resolve to the TARGET user (a tenant user), so
    they can never pass this check — platform routes stay locked even
    while a support session is active.
    """
    min_level = PLATFORM_ROLE_ORDER[min_role]

    def _dep(user: User = Depends(current_user)) -> User:
        if user.platform_role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform user role required",
            )
        if PLATFORM_ROLE_ORDER[user.platform_role] < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires platform role >= {min_role.value}",
            )
        return user

    return _dep


# --- Tenant context -----------------------------------------------------------


def current_tenant_id(user: User = Depends(current_user)) -> uuid.UUID:
    """
    Convenience dependency for routes that must operate within a tenant.
    Rejects platform users — they must use platform endpoints instead.
    """
    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires a tenant context",
        )
    return user.tenant_id


def require_feature(db, tenant_id, feature_key: str) -> None:
    if not fs.is_enabled(db, tenant_id, feature_key):
        raise HTTPException(
            status_code=403,
            detail=f"Feature '{feature_key}' is not enabled for this tenant",
        )