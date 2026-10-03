"""Dump the exact prompt sent to the model for a plot."""
import sys
from uuid import UUID

from app.db.session import SessionLocal
from app.db.models.plot import Plot
from app.services.context_builder import build_safety_context
from app.services.agent_llm import _format_context


def main():
    plot_id = UUID(sys.argv[1])
    db = SessionLocal()
    try:
        ctx = build_safety_context(db, plot_id)
        print("=" * 70)
        print("USER PROMPT AS SENT TO MODEL:")
        print("=" * 70)
        print(_format_context(ctx))
        print("=" * 70)
    finally:
        db.close()


if __name__ == "__main__":
    main()