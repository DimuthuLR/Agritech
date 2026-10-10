"""
Integration tests for IoT endpoints.

Uses a TestClient (in-process) and creates test data directly via
the DB session, so no running server is required.
"""
import hashlib
import hmac as hmac_lib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db.models.device import Device
from app.db.models.device_claim_code import DeviceClaimCode
from app.db.models.tenant import Tenant
from app.db.session import SessionLocal
from app.main import app
from app.services.iot_service import generate_claim_code


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture
def tenant(db_session):
    t = Tenant(
        name=f"Test Tenant {uuid.uuid4().hex[:6]}",
        slug=f"test-{uuid.uuid4().hex[:8]}",
        region="EU",
        timezone="UTC",
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    yield t
    # Cleanup: cascade deletes claim codes and devices
    db_session.delete(t)
    db_session.commit()


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _create_claim(db, tenant_id, ttl_hours=24):
    code = generate_claim_code()
    row = DeviceClaimCode(
        tenant_id=tenant_id,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
    )
    db.add(row)
    db.commit()
    return row


def _sign(secret: str, serial: str, ts: int, body: bytes) -> str:
    canonical = f"{serial}.{ts}.".encode("utf-8") + body
    return hmac_lib.new(
        secret.encode("utf-8"), canonical, hashlib.sha256
    ).hexdigest()


# =========================================================================
# Registration
# =========================================================================

class TestRegistration:
    def test_successful_registration(self, client, db_session, tenant):
        code = _create_claim(db_session, tenant.id)

        resp = client.post(
            "/api/v1/iot/register",
            json={
                "mac": "AA:BB:CC:11:22:33",
                "hw_version": "hub-v1.0",
                "fw_version": "1.0.0",
                "chip": "esp32s3",
                "claim_code": code.code,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()

        assert body["device_serial"] == "AA:BB:CC:11:22:33"
        assert len(body["hmac_secret"]) == 64
        assert body["mqtt"] is None
        assert body["tls"] is None

        # Code is now used
        db_session.refresh(code)
        assert code.used_at is not None
        assert str(code.used_by_device_id) == body["device_id"]

    def test_rejects_unknown_code(self, client):
        resp = client.post(
            "/api/v1/iot/register",
            json={
                "mac": "AA:BB:CC:99:99:99",
                "hw_version": "hub-v1.0",
                "fw_version": "1.0.0",
                "chip": "esp32s3",
                "claim_code": "ZZZZ-ZZZZ-ZZZZ",
            },
        )
        assert resp.status_code == 400
        assert "Invalid or expired" in resp.json()["detail"]

    def test_rejects_expired_code(self, client, db_session, tenant):
        code = _create_claim(db_session, tenant.id, ttl_hours=-1)

        resp = client.post(
            "/api/v1/iot/register",
            json={
                "mac": "AA:BB:CC:44:55:66",
                "hw_version": "hub-v1.0",
                "fw_version": "1.0.0",
                "chip": "esp32s3",
                "claim_code": code.code,
            },
        )
        assert resp.status_code == 400
        assert "Invalid or expired" in resp.json()["detail"]

    def test_rejects_reused_code(self, client, db_session, tenant):
        code = _create_claim(db_session, tenant.id)

        # First registration uses the code
        r1 = client.post(
            "/api/v1/iot/register",
            json={
                "mac": "AA:BB:CC:77:88:99",
                "hw_version": "hub-v1.0",
                "fw_version": "1.0.0",
                "chip": "esp32s3",
                "claim_code": code.code,
            },
        )
        assert r1.status_code == 201

        # Second attempt with same code + different MAC must fail
        r2 = client.post(
            "/api/v1/iot/register",
            json={
                "mac": "AA:BB:CC:77:88:AA",
                "hw_version": "hub-v1.0",
                "fw_version": "1.0.0",
                "chip": "esp32s3",
                "claim_code": code.code,
            },
        )
        assert r2.status_code == 400

    def test_rejects_duplicate_mac(self, client, db_session, tenant):
        code1 = _create_claim(db_session, tenant.id)
        code2 = _create_claim(db_session, tenant.id)

        # First device registers fine
        r1 = client.post(
            "/api/v1/iot/register",
            json={
                "mac": "AA:BB:CC:DE:AD:01",
                "hw_version": "hub-v1.0",
                "fw_version": "1.0.0",
                "chip": "esp32s3",
                "claim_code": code1.code,
            },
        )
        assert r1.status_code == 201

        # Second registration with same MAC fails
        r2 = client.post(
            "/api/v1/iot/register",
            json={
                "mac": "AA:BB:CC:DE:AD:01",
                "hw_version": "hub-v1.0",
                "fw_version": "1.0.0",
                "chip": "esp32s3",
                "claim_code": code2.code,
            },
        )
        assert r2.status_code == 400
        assert "already registered" in r2.json()["detail"]


# =========================================================================
# Heartbeat
# =========================================================================

class TestHeartbeat:
    def _registered_device(self, client, db_session, tenant):
        code = _create_claim(db_session, tenant.id)
        resp = client.post(
            "/api/v1/iot/register",
            json={
                "mac": "AA:BB:CC:HB:HB:01",
                "hw_version": "hub-v1.0",
                "fw_version": "1.0.0",
                "chip": "esp32s3",
                "claim_code": code.code,
            },
        )
        assert resp.status_code == 201
        return resp.json()

    def test_heartbeat_updates_device(self, client, db_session, tenant):
        reg = self._registered_device(client, db_session, tenant)
        secret = reg["hmac_secret"]
        serial = reg["device_serial"]

        body = {
            "uptime_sec": 3600,
            "free_heap_kb": 142,
            "rssi_dbm": -67,
            "battery_v": 3.82,
            "fw_version": "1.0.0",
            "ts": int(time.time()),
        }
        raw = json.dumps(body).encode("utf-8")
        ts = str(int(time.time()))
        sig = _sign(secret, serial, int(ts), raw)

        resp = client.post(
            "/api/v1/iot/heartbeat",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Device-Serial": serial,
                "X-Timestamp": ts,
                "X-Signature": sig,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "ok"

        # Verify DB was updated
        device = db_session.query(Device).filter(Device.serial == serial).first()
        assert device is not None
        assert device.uptime_sec == 3600
        assert device.rssi_dbm == -67
        assert device.free_heap_kb == 142
        assert float(device.battery_v) == 3.82

    def test_heartbeat_rejects_bad_signature(self, client, db_session, tenant):
        reg = self._registered_device(client, db_session, tenant)

        body = {
            "uptime_sec": 1,
            "free_heap_kb": 1,
            "rssi_dbm": -1,
            "ts": int(time.time()),
        }
        raw = json.dumps(body).encode("utf-8")

        resp = client.post(
            "/api/v1/iot/heartbeat",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Device-Serial": reg["device_serial"],
                "X-Timestamp": str(int(time.time())),
                "X-Signature": "deadbeef" * 8,
            },
        )
        assert resp.status_code == 401

    def test_heartbeat_rejects_unknown_device(self, client):
        body = {"uptime_sec": 1, "free_heap_kb": 1, "rssi_dbm": -1, "ts": int(time.time())}
        raw = json.dumps(body).encode("utf-8")
        resp = client.post(
            "/api/v1/iot/heartbeat",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Device-Serial": "FF:FF:FF:FF:FF:FF",
                "X-Timestamp": str(int(time.time())),
                "X-Signature": "deadbeef" * 8,
            },
        )
        assert resp.status_code == 401