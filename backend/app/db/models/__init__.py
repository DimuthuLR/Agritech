"""
Import all model modules here so Alembic and the rest of the app
can access them from a single place.
"""
from app.db.models.tenant import Tenant
from app.db.models.tenant_feature import TenantFeature
from app.db.models.user import User, TenantRole, PlatformRole
from app.db.models.farm import Farm
from app.db.models.plot import Plot
from app.db.models.crop_batch import CropBatch
from app.db.models.device import Device
from app.db.models.sensor_reading import SensorReading
from app.db.models.task import Task, TaskStatus
from app.db.models.actuator_command import ActuatorCommand
from app.db.models.diagnosis import Diagnosis
from app.db.models.input_price import InputPrice, InputCategory
from app.db.models.financial_ledger import FinancialLedger, LedgerCategory
from app.db.models.field_event import FieldEvent, FieldEventType, FieldEventOutcome
from app.db.models.audit_log import AuditLog

__all__ = [
    "Tenant", "TenantFeature",
    "User", "TenantRole", "PlatformRole",
    "Farm", "Plot", "CropBatch",
    "Device", "SensorReading",
    "Task", "TaskStatus",
    "ActuatorCommand",
    "Diagnosis",
    "InputPrice", "InputCategory",
    "FinancialLedger", "LedgerCategory",
    "FieldEvent", "FieldEventType", "FieldEventOutcome",
    "AuditLog",
]