"""
BM25 index — removed in Gemini-only re-architecture.

rank-bm25 has been uninstalled. This module is a no-op stub kept so that any
import from old code paths doesn't cause an ImportError crash.
"""


def build_bm25(collection, settings) -> dict:
    return {}


def load_bm25(settings) -> dict | None:
    return None


def invalidate_bm25(settings) -> None:
    pass


def search_bm25(index_data: dict, query: str, top_k: int, job_ids=None) -> list:
    return []
