"""
MQTT ack subscriber.

Listens to `agra/devices/+/ack` and `agra/devices/+/error`, converts
each message to a DeviceEvent row, and stores it.

Runs as a background thread. Started by the FastAPI lifespan hook.
One subscriber handles all devices and all tenants.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.device import Device
from app.db.models.device_event import DeviceEvent
from app.db.session import SessionLocal


log = logging.getLogger(__name__)


_topic_ack = "agra/devices/+/ack"
_topic_error = "agra/devices/+/error"


def _handle_ack(db: Session, device: Device, payload: dict) -> None:
    event = DeviceEvent(
        tenant_id=device.tenant_id,
        device_id=device.id,
        event_type="ack",
        cmd_id=str(payload.get("cmd_id", ""))[:64] or None,
        action=None,
        status=str(payload.get("status", "unknown"))[:32],
        error=payload.get("error"),
        duration_ms=int(payload["duration_ms"]) if "duration_ms" in payload else None,
        occurred_at=datetime.now(timezone.utc),
        metadata_={"raw": payload},
    )
    db.add(event)


def _handle_error(db: Session, device: Device, payload: dict) -> None:
    event = DeviceEvent(
        tenant_id=device.tenant_id,
        device_id=device.id,
        event_type="error",
        cmd_id=None,
        action=str(payload.get("code", ""))[:64] or None,
        status="error",
        error=str(payload.get("message", "")) or None,
        duration_ms=None,
        occurred_at=datetime.now(timezone.utc),
        metadata_={"raw": payload},
    )
    db.add(event)

    device.last_error_code = event.action
    device.last_error_message = event.error[:500] if event.error else None
    device.last_error_at = event.occurred_at


def _extract_device_id(topic: str) -> uuid.UUID | None:
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != "agra" or parts[1] != "devices":
        return None
    try:
        return uuid.UUID(parts[2])
    except ValueError:
        return None


def _process_message(topic: str, raw_payload: bytes) -> None:
    device_id = _extract_device_id(topic)
    if device_id is None:
        log.warning(f"[iot-ack] malformed topic: {topic}")
        return

    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except Exception as e:
        log.warning(f"[iot-ack] bad json from {topic}: {e}")
        return

    db = SessionLocal()
    try:
        device = db.get(Device, device_id)
        if device is None:
            log.debug(f"[iot-ack] unknown device {device_id}, skipping")
            return

        if topic.endswith("/ack"):
            _handle_ack(db, device, payload)
        elif topic.endswith("/error"):
            _handle_error(db, device, payload)

        db.commit()

        if topic.endswith("/ack"):
            log.info(
                f"[iot-ack] {device.serial} ack cmd={payload.get('cmd_id')} "
                f"status={payload.get('status')}"
            )
        else:
            log.warning(
                f"[iot-ack] {device.serial} error "
                f"code={payload.get('code')}: {payload.get('message')}"
            )
    except Exception as e:
        db.rollback()
        log.error(f"[iot-ack] failed to persist: {e}")
    finally:
        db.close()


def _on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        client.subscribe([(_topic_ack, 1), (_topic_error, 1)])
        log.info(f"[iot-ack] subscribed to {_topic_ack} and {_topic_error}")
    else:
        log.error(f"[iot-ack] connect failed: {reason_code}")


def _on_message(client, userdata, msg):
    _process_message(msg.topic, msg.payload)


def _on_disconnect(client, userdata, flags, reason_code, properties=None):
    log.warning(f"[iot-ack] disconnected from broker: {reason_code}")


class AckSubscriber:
    """Background MQTT ack subscriber. Start once at app boot."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._client: mqtt.Client | None = None

    def start(self) -> None:
        if self._thread is not None:
            return

        client = mqtt.Client(
            client_id="agra-iot-ack-subscriber",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        client.on_connect = _on_connect
        client.on_message = _on_message
        client.on_disconnect = _on_disconnect

        try:
            client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
        except Exception as e:
            log.error(f"[iot-ack] initial connect failed: {e}")
            return

        self._client = client
        self._thread = threading.Thread(
            target=client.loop_forever,
            daemon=True,
            name="iot-ack-subscriber",
        )
        self._thread.start()
        log.info("[iot-ack] subscriber thread started")

    def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
        self._thread = None


subscriber = AckSubscriber()