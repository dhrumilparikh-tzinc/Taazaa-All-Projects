from datetime import datetime, timezone
import json

from db.db import SessionLocal
from db.models import Interaction


def log_interaction(question: str, answer: str, chunks) -> None:
    """
    Save one Q&A interaction into PostgreSQL.
    chunks is the list returned by generate_answer()['chunks'].
    """
    # Prepare text context
    context_texts = [c["text"] for c in chunks]
    context = "\n---\n".join(context_texts)

    # Optional debugging fields
    similarity_scores = [float(c.get("distance", 0.0)) for c in chunks]
    chunk_ids = [c.get("chunk_id", idx) for idx, c in enumerate(chunks)]

    # Use timezone-aware UTC datetime
    now_utc = datetime.now(timezone.utc)

    session = SessionLocal()
    try:
        row = Interaction(
            question=question,
            context=context,
            answer=answer,
            timestamp=now_utc,
            similarity_scores=json.dumps(similarity_scores),
            chunk_ids=json.dumps(chunk_ids),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        print(f"[DB] Logged interaction with id {row.id}")
    except Exception as exc:
        session.rollback()
        print(f"[DB] Failed to log interaction: {exc}")
    finally:
        session.close()
