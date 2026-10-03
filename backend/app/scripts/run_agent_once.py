"""
Run the agent on a single plot for testing.

Usage:
    ./py.bat -m app.scripts.run_agent_once --plot 0bc335dd-...
"""
import argparse
import json
import sys
from uuid import UUID

from app.db.session import SessionLocal
from app.services.agent_loop import run_agent_for_plot


def _print_section(n: int, total: int, title: str) -> None:
    print(f"[{n}/{total}] {title}")


def main() -> int:
    p = argparse.ArgumentParser(description="Run the agent on one plot.")
    p.add_argument("--plot", required=True, help="Plot UUID")
    args = p.parse_args()

    try:
        plot_id = UUID(args.plot)
    except ValueError:
        print(f"ERROR: invalid UUID {args.plot!r}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        _print_section(1, 6, "Loading plot and building context...")
        result = run_agent_for_plot(db, plot_id)

        ctx = result.context_summary
        print(f"      crop={ctx['crop']} stage={ctx['stage']} "
              f"soil={ctx['soil_type']}")
        print(f"      weather: {ctx['weather']['temp_c']}°C, "
              f"{ctx['weather']['wind_kmh']}km/h wind, "
              f"{ctx['weather']['rain_forecast_mm_6h']}mm rain "
              f"({ctx['weather']['source']})")
        print(f"      sensors: soil_moisture={ctx['sensors']['soil_moisture']} "
              f"({ctx['sensors']['newest_reading_age_s']}s old)")
        print(f"      history: {ctx['history']['events_today']} events today, "
              f"last at {ctx['history']['last_irrigation_at']}")

        _print_section(2, 6, "Agent decision...")
        print(f"      tool: {result.decision['tool']}")
        print(f"      args: {json.dumps(result.decision['args'])}")
        print(f"      reason: {result.decision['reason']}")

        _print_section(3, 6, "Validation through safety gate...")
        status = result.validation["status"]
        if status == "passed":
            print(f"      ✅ PASSED")
        elif status == "noop":
            print(f"      ➖ NOOP (no action proposed)")
        else:
            print(f"      ❌ {status.upper()}: {result.validation.get('reason')}")

        _print_section(4, 6, "Task creation...")
        if result.task_id:
            print(f"      Task created: {result.task_id}")
            print(f"      Status: {result.task_status}")
            if result.validation.get("requires_approval"):
                print(f"      ⏳ Requires human approval")
            else:
                print(f"      ✅ Ready to dispatch (no approval needed)")
        else:
            print(f"      No task created.")

        _print_section(5, 6, "Execution...")
        if result.would_execute and not result.validation.get("requires_approval"):
            print(f"      (Real dispatch is Phase 6d.)")
        elif result.validation.get("requires_approval"):
            print(f"      Waiting for human approval before dispatch.")
        else:
            print(f"      No dispatch.")

        _print_section(6, 6, "Audit log...")
        print(f"      audit_id={result.audit_id}")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())