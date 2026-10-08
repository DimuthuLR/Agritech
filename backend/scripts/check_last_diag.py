"""
Debug: show what RAG retrieves for the diagnosis query.
"""
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s: %(levelname)s: %(message)s",
)

from app.db.session import SessionLocal
from app.services import rag_service


def main():
    db = SessionLocal()
    try:
        # Simulate the query the diagnosis pipeline builds
        plot_crop = "Tomato"
        notes = None
        query = rag_service.build_query(plot_crop, notes)
        print(f"\n=== QUERY ===\n{query}\n")

        hits = rag_service.search(db, query, top_k=8)
        print(f"=== {len(hits)} CHUNKS ===\n")

        for i, c in enumerate(hits, 1):
            print(f"--- [{i}] {c.source}  (similarity: {c.similarity:.3f}, lang: {c.language}) ---")
            # Print first 500 chars to see what's in them
            snippet = c.content.strip()[:500].replace("\n", " ")
            print(snippet)
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()