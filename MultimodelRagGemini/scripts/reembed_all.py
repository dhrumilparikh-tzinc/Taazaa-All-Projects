"""
Re-embed all documents with gemini-embedding-exp-03-07.

Steps:
  1. Delete and recreate the ChromaDB collection (clears all old vectors).
  2. Reset every COMPLETED job back to PENDING in the database.
  3. Print a count so you know what's queued.

Run ONCE after switching GEMINI_EMBEDDING_MODEL in .env.
Then restart the Celery worker — it will pick up all pending jobs automatically.

Usage:
    py scripts/reembed_all.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
DATABASE_URL = os.environ["DATABASE_URL"]

from sqlmodel import Session, create_engine, select
from app.models.db import Job, JobStatus
from app.config import settings

engine = create_engine(DATABASE_URL, echo=False)


def clear_chromadb():
    from app.rag.vectorstore import get_chroma_client, get_or_create_collection
    client = get_chroma_client(settings)
    collection_name = settings.CHROMA_COLLECTION
    try:
        client.delete_collection(collection_name)
        print(f"[OK] Deleted ChromaDB collection: {collection_name}")
    except Exception as e:
        print(f"[WARN] Could not delete collection (may not exist): {e}")
    # Recreate empty
    get_or_create_collection(client, settings)
    print(f"[OK] Recreated empty collection: {collection_name}")


def reset_jobs():
    with Session(engine) as db:
        jobs = db.exec(select(Job)).all()
        requeued = 0
        skipped = 0
        for job in jobs:
            if job.status in (
                JobStatus.completed, JobStatus.partial,
                JobStatus.failed, JobStatus.failed_permanent,
                JobStatus.processing,
            ):
                job.status = JobStatus.pending
                job.step = None
                job.error_message = None
                job.chunk_count = None
                db.add(job)
                requeued += 1
            else:
                skipped += 1
        db.commit()
        print(f"[OK] Reset {requeued} jobs to PENDING  ({skipped} already pending/processing — left as-is)")
        return requeued


if __name__ == "__main__":
    print("=" * 60)
    print("Re-embed all docs: gemini-embedding-exp-03-07")
    print("=" * 60)
    print(f"Embedding model : {settings.GEMINI_EMBEDDING_MODEL}")
    print(f"ChromaDB        : {settings.CHROMA_HOST}:{settings.CHROMA_PORT}  collection={settings.CHROMA_COLLECTION}")
    print()

    clear_chromadb()
    count = reset_jobs()

    print()
    print("=" * 60)
    print(f"Done. {count} jobs queued.")
    print("Next: restart the Celery worker to begin re-processing.")
    print("=" * 60)
