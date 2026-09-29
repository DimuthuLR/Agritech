"""
Import all model modules here so Alembic and the rest of the app
can access them from a single place:

    from app.db import models
    models.Farm
"""
from app.db.models.tenant import Tenant
from app.db.models.tenant_feature import TenantFeature
from app.db.models.user import User, TenantRole, PlatformRole
from app.db.models.farm import Farm
from app.db.models.plot import Plot
from app.db.models.device import Device
from app.db.models.audit_log import AuditLog

__all__ = [
    "Tenant",
    "TenantFeature",
    "User",
    "TenantRole",
    "PlatformRole",
    "Farm",
    "Plot",
    "Device",
    "AuditLog",
]