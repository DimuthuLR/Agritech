"""
Authentication endpoints: login and current-user info.

- POST /auth/login        → JSON body {email, password}      (frontend)
- POST /auth/token        → OAuth2 form {username, password} (Swagger)
- GET  /auth/me           → Bearer token → user profile
- GET  /auth/me/features  → Bearer token → feature map for the caller's tenant
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse, TokenResponse
from app.services import features_service as fs


router = APIRouter(prefix="/auth", tags=["auth"])


# --- Internals ----------------------------------------------------------------


def _authenticate(db: Session, email: str, password: str) -> User:
    """
    Look up a user and verify the password.

    Returns the User on success. Raises 401 on any failure.
    Uniform error message prevents "user enumeration" — an attacker
    can't tell if an email exists by comparing error responses.
    """
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )
    return user


def _issue_token(user: User) -> str:
    """
    Create a JWT for the user, embedding role and tenant info.
    Keeping these claims in the token means dependencies don't need
    an extra DB query to know what the caller can do.
    """
    claims = {
        "email": user.email,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "tenant_role": user.tenant_role.value if user.tenant_role else None,
        "platform_role": user.platform_role.value if user.platform_role else None,
    }
    return create_access_token(subject=str(user.id), extra_claims=claims)


# --- Endpoints ----------------------------------------------------------------


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    JSON login for the frontend. Returns a token plus the user's public profile.
    """
    user = _authenticate(db, email=payload.email, password=payload.password)
    token = _issue_token(user)
    return LoginResponse(
        access_token=token,
        expires_in=settings.jwt_access_ttl_min * 60,
        user=MeResponse.model_validate(user),
    )


@router.post("/token", response_model=TokenResponse)
def token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    OAuth2 form login. Used by Swagger's Authorize button.
    `username` is treated as the email.
    """
    user = _authenticate(db, form_data.username, form_data.password)
    token = _issue_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_access_ttl_min * 60,
    )


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(current_user)):
    """
    Return the authenticated user's public profile. Requires Bearer token.
    """
    return MeResponse.model_validate(user)


@router.get("/me/features")
def my_features(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """
    Return a flat {feature_key: enabled} map for the caller's tenant.

    Used by the frontend to hide menu items and routes when a feature
    is off. Platform users (no tenant_id) get an empty map — the
    frontend treats missing keys as enabled, so platform users see
    everything (they use separate platform routes anyway).
    """
    if user.tenant_id is None:
        return {}
    features = fs.list_features(db, user.tenant_id)
    return {key: info["enabled"] for key, info in features.items()}