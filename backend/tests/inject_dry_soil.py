from app.db.session import SessionLocal
from app.db.models.sensor_reading import SensorReading
from app.db.models.device import Device
from datetime import datetime, timezone
import uuid

db = SessionLocal()

# 1. Find the Classic ESP32 sensor
device = db.query(Device).filter(Device.serial == "68:25:DD:47:4F:50").first()
if not device:
    print("Device not found!")
    exit()

# 2. Insert a fake low moisture reading (20%)
reading = SensorReading(
    time=datetime.now(timezone.utc),
    device_id=device.id,
    tenant_id=device.tenant_id,
    plot_id=device.plot_id,
    metric="soil_moisture",
    value=0.20  # 20% - This is below the 0.30 threshold!
)
db.add(reading)
db.commit()
print(f"✅ Injected dry soil reading (20%) for plot {device.plot_id}")
db.close()