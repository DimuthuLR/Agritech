"""
Pydantic schemas for IoT device endpoints.

Registration is unauthenticated (device has no credentials yet — the
claim code IS the auth). Heartbeat is HMAC-authenticated.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class DeviceRegisterRequest(BaseModel):
    """Body for POST /iot/register."""
    mac: str = Field(..., min_length=12, max_length=64)
    hw_version: str = Field(..., max_length=64)
    fw_version: str = Field(..., max_length=64)
    chip: str = Field(..., max_length=32)
    claim_code: str = Field(..., min_length=4, max_length=32)


class MQTTBundle(BaseModel):
    """MQTT credentials issued at registration. Null until IoT-8."""
    host: str
    port: int
    username: str
    password: str


class TLSBundle(BaseModel):
    """mTLS material issued at registration. Null until IoT-8."""
    ca_pem: str
    client_cert_pem: str
    client_key_pem: str


class DeviceRegisterResponse(BaseModel):
    """Returned once, on successful registration. Device must store
    hmac_secret in encrypted NVS — the server cannot re-issue it."""
    model_config = ConfigDict(from_attributes=True)

    device_id: uuid.UUID
    device_serial: str
    hmac_secret: str
    provisioned_at: datetime

    # Placeholders for later phases
    mqtt: MQTTBundle | None = None
    tls: TLSBundle | None = None


class DeviceHeartbeatRequest(BaseModel):
    """Body for POST /iot/heartbeat. HMAC-signed like readings."""
    uptime_sec: int = Field(..., ge=0)
    free_heap_kb: int = Field(..., ge=0)
    rssi_dbm: int = Field(..., ge=-120, le=0)
    battery_v: float | None = Field(None, ge=0, le=10)
    fw_version: str | None = Field(None, max_length=64)
    ts: int = Field(..., description="Unix timestamp (seconds)")


class DeviceHeartbeatResponse(BaseModel):
    status: str = "ok"
    server_time: datetime