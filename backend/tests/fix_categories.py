from app.db.session import SessionLocal
from app.db.models.device import Device

db = SessionLocal()

# 1. The Hub should be a 'gateway'
hub = db.query(Device).filter(Device.serial == "B8:1F:3F:DA:0E:24").first()
if hub:
    hub.kind = "gateway"
    print("✅ Hub set to gateway")

# 2. The C3 should be an 'actuator'
c3 = db.query(Device).filter(Device.serial == "48:F6:EE:13:A9:90").first()
if c3:
    c3.kind = "actuator"
    print("✅ C3 set to actuator")

# 3. The Classic ESP32 should be a 'sensor'
classic = db.query(Device).filter(Device.serial == "68:25:DD:47:4F:50").first()
if classic:
    classic.kind = "sensor"
    print("✅ Classic ESP32 set to sensor")

db.commit()
db.close()
print("🎉 Done! Refresh your web browser.")