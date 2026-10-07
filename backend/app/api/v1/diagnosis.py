"""
Diagnosis endpoints — image upload and diagnosis retrieval.

The upload endpoint is synchronous: it accepts the image, saves it,
runs the vision model (~5s), and returns the completed diagnosis.
For MVP this is fine; a background-worker version is a Phase 12 concern.

Security & safety:
- File size limited to 10 MB (blocks memory exhaustion)
- Content types limited to JPEG, PNG, WebP (blocks SVG/XSS, exec, etc.)
- Tenant isolation on disk: data/diagnoses/{tenant_id}/
- Content-Type whitelist enforced before we touch disk
- Tenant-scoped queries — you can only see your own diagnoses
- Feature flag check: 'diagnosis' must be enabled for the tenant
"""
import hashlib
import logging
from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import require_tenant_role, require_feature
from app.db.models.diagnosis import Diagnosis
from app.db.models.plot import Plot
from app.db.models.user import User, TenantRole
from app.db.session import get_db
from app.schemas.diagnosis import DiagnosisRead
from app.services.diagnosis_service import (
    DiagnosisError,
    run_and_store_diagnosis,
)
from app.services.diagnosis_cache import (
    check_budget,
    find_cached_diagnosis,
)


log = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


# --- Constants ---------------------------------------------------------------

MAX_IMAGE_BYTES = 10 * 1024 * 1024   # 10 MB
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# Root for on-disk image storage. Relative to the current working
# directory, which is backend/ when running uvicorn from there.
DATA_ROOT = Path("data/diagnoses")


# --- Helpers -----------------------------------------------------------------

def _save_image_bytes(
    tenant_id: UUID,
    image_bytes: bytes,
    ext: str,
) -> Path:
    """Save image to tenant-isolated storage. Returns the path."""
    tenant_dir = DATA_ROOT / str(tenant_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)

    h = hashlib.sha256(image_bytes).hexdigest()
    filename = f"{h[:16]}{ext}"
    path = tenant_dir / filename

    if not path.exists():
        path.write_bytes(image_bytes)

    return path


async def _read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    """
    Read the file in chunks, rejecting if it exceeds max_bytes.
    Avoids loading an unbounded stream into memory.
    """
    chunks: list[bytes] = []
    total = 0
    chunk_size = 64 * 1024   # 64 KB

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Image exceeds {max_bytes // (1024 * 1024)} MB limit",
            )
        chunks.append(chunk)

    return b"".join(chunks)


# --- Endpoints ---------------------------------------------------------------

@router.post(
    "/upload",
    response_model=DiagnosisRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_diagnosis(
    plot_id: UUID = Form(...),
    notes: str | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(require_tenant_role(TenantRole.OPERATOR)),
    db: Session = Depends(get_db),
):
    """
    Upload a leaf image and receive a diagnosis.

    Form fields:
      plot_id — UUID of the plot this image belongs to
      notes   — optional farmer notes (max 500 chars)
      file    — the image (JPEG/PNG/WebP, max 10 MB)
    """
    require_feature(db, user.tenant_id, "diagnosis")

    # --- Content type check ---
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported content type {content_type!r}. "
                f"Allowed: {sorted(ALLOWED_CONTENT_TYPES)}"
            ),
        )
    ext = ALLOWED_CONTENT_TYPES[content_type]

    # --- Verify plot belongs to caller's tenant ---
    plot = (
        db.query(Plot)
        .filter(Plot.id == plot_id, Plot.tenant_id == user.tenant_id)
        .first()
    )
    if plot is None:
        raise HTTPException(status_code=404, detail="Plot not found")

    # --- Read image bytes with size limit ---
    image_bytes = await _read_upload_limited(file, MAX_IMAGE_BYTES)

    if len(image_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty image file",
        )

    # --- Compute hash early (used by cache + storage) ---
    image_hash = hashlib.sha256(image_bytes).hexdigest()

    # --- Cache lookup: same tenant, same image, already diagnosed? ---
    cached = find_cached_diagnosis(db, user.tenant_id, image_hash)
    if cached is not None:
        log.info(
            f"Cache hit for tenant {user.tenant_id}, "
            f"hash {image_hash[:16]}"
        )
        return cached

    # --- Budget guard: refuse if today's limit is reached ---
    check_budget(db, user.tenant_id)

    # --- Persist to disk (tenant-isolated) ---
    saved_path = _save_image_bytes(user.tenant_id, image_bytes, ext)

    # --- Create the Diagnosis row (pending) ---
    diag = Diagnosis(
        tenant_id=user.tenant_id,
        plot_id=plot.id,
        image_hash=image_hash,
        image_path=str(saved_path),
        image_size_bytes=len(image_bytes),
        status="pending",
    )
    db.add(diag)
    db.commit()
    db.refresh(diag)

    # --- Run the model (synchronous ~5s) ---
    try:
        run_and_store_diagnosis(
            db,
            diag.id,
            image_bytes,
            plot.crop,
            notes,
        )
    except DiagnosisError as e:
        # The row has been marked 'failed' by the service.
        # Return the row with its error message, so the client knows.
        log.warning(f"Diagnosis {diag.id} failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vision model failed: {e}",
        )

    # --- Reload to pick up the completed state ---
    db.refresh(diag)
    return diag


@router.get("", response_model=list[DiagnosisRead])
def list_diagnoses(
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
    plot_id: UUID | None = None,
    status_filter: str | None = None,
    skip: int = 0,
    limit: int = 50,
):
    """List diagnoses for the caller's tenant."""
    require_feature(db, user.tenant_id, "diagnosis")
    q = db.query(Diagnosis).filter(Diagnosis.tenant_id == user.tenant_id)
    if plot_id is not None:
        q = q.filter(Diagnosis.plot_id == plot_id)
    if status_filter is not None:
        q = q.filter(Diagnosis.status == status_filter)

    return (
        q.order_by(Diagnosis.created_at.desc())
        .offset(skip)
        .limit(min(limit, 200))
        .all()
    )


@router.get("/{diagnosis_id}", response_model=DiagnosisRead)
def get_diagnosis(
    diagnosis_id: UUID,
    user: User = Depends(require_tenant_role(TenantRole.VIEWER)),
    db: Session = Depends(get_db),
):
    """Fetch one diagnosis by ID."""
    require_feature(db, user.tenant_id, "diagnosis")
    diag = (
        db.query(Diagnosis)
        .filter(
            Diagnosis.id == diagnosis_id,
            Diagnosis.tenant_id == user.tenant_id,
        )
        .first()
    )
    if diag is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found")
    return diag