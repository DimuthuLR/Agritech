"""
Background Worker — Deterministic Rules Engine.

Runs independently of the LLM Agent Loop.
Checks real-time sensor data against hardcoded rules (e.g., soil < 30%).
Creates PENDING_APPROVAL tasks for the farmer.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import SessionLocal
from app.db.models.plot import Plot
from app.db.models.sensor_reading import SensorReading
from app.db.models.task import Task, TaskStatus
from app.services.context_builder import build_safety_context
from app.services.task_service import create_task_from_agent

log = logging.getLogger(__name__)

# Safety thresholds
SOIL_MOISTURE_MIN = 0.30  # 30%
COOLDOWN_HOURS = 2        # Don't spam the same alert if one is pending

async def run_rule_engine():
    """Main background loop."""
    log.info("[Worker] Starting Rule Engine...")
    while True:
        try:
            # Run the synchronous DB logic in a thread so it doesn't block FastAPI
            await asyncio.to_thread(_check_all_plots)
        except Exception as e:
            log.error(f"[Worker] Error in rule engine: {e}")
        
        # Sleep for 5 minutes
        await asyncio.sleep(300)

def _check_all_plots():
    db = SessionLocal()
    try:
        plots = db.query(Plot).all()
        for plot in plots:
            _check_soil_moisture(db, plot)
    finally:
        db.close()

def _check_soil_moisture(db: Session, plot: Plot):
    # 1. Get the latest soil moisture reading
    latest = (
        db.query(SensorReading)
        .filter(
            SensorReading.plot_id == plot.id,
            SensorReading.metric == "soil_moisture"
        )
        .order_by(desc(SensorReading.time))
        .first()
    )
    
    if not latest or latest.value >= SOIL_MOISTURE_MIN:
        return # Soil is fine, or no data

    # 2. Check if we already have a pending task for this plot
    recent_task = (
        db.query(Task)
        .filter(
            Task.plot_id == plot.id,
            Task.tool == "control_irrigation",
            Task.status.in_([TaskStatus.PENDING_APPROVAL, TaskStatus.APPROVED])
        )
        .first()
    )

    if recent_task:
        return # Already waiting for farmer approval, don't spam

    # 3. Build context and create the task
    log.info(f"[Worker] Soil moisture low ({latest.value}) on Plot {plot.name}. Creating task.")
    
    try:
        ctx = build_safety_context(db, plot.id)
        
        create_task_from_agent(
            db,
            ctx,
            decision_tool="control_irrigation",
            decision_args={"duration_sec": 120},
            decision_reason=f"Automated Rule: Soil moisture dropped to {latest.value:.1%}, below the {SOIL_MOISTURE_MIN:.1%} threshold.",
            requires_approval=True,
        )
        log.info(f"[Worker] Successfully created irrigation task for {plot.name}.")
    except Exception as e:
        log.error(f"[Worker] Failed to create task for {plot.name}: {e}")