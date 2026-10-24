from app.db.session import SessionLocal
from app.db.models.device import Device
from app.db.models.plot import Plot

db = SessionLocal()

# Find the plot (Greenhouse 1)
plot = db.query(Plot).filter(Plot.name == "Greenhouse 1").first()
if not plot:
    print("❌ Could not find 'Greenhouse 1' plot.")
else:
    print(f"✅ Found Plot: {plot.name} (ID: {plot.id})")
    
    # Find the devices by serial
    serials = ["68:25:DD:47:4F:50", "48:F6:EE:13:A9:90"]
    for serial in serials:
        device = db.query(Device).filter(Device.serial == serial).first()
        if device:
            device.plot_id = plot.id
            print(f"✅ Linked {device.serial} to {plot.name}")
        else:
            print(f"❌ Could not find device with serial {serial}")
    
    db.commit()
    print("🎉 Done! Devices linked to plot.")
db.close()