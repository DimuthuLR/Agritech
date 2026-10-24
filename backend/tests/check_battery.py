from app.db.session import SessionLocal
from app.db.models.device import Device

db = SessionLocal()
for d in db.query(Device).all():
    print(f"{d.serial} ({d.kind}): Battery = {d.battery_v}, Last Seen = {d.last_seen_at}")
db.close()