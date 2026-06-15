from pathlib import Path
from typing import List, Dict, Any, Tuple

import faiss
import numpy as np
import pickle

FAISS_DIR = Path("faiss_index")
FAISS_DIR.mkdir(exist_ok=True)

INDEX_PATH = FAISS_DIR / "index.faiss"
META_PATH = FAISS_DIR / "index.pkl"


def build_faiss_index(embeddings: np.ndarray) -> faiss.Index:
    """
    Build a FAISS index from a 2D numpy array of embeddings.
    """
    n_vectors, dim = embeddings.shape
    index = faiss.IndexFlatL2(dim)  # simple L2 index
    index.add(embeddings.astype(np.float32))
    assert index.ntotal == n_vectors
    return index


def save_faiss_index(index: faiss.Index, path: Path = INDEX_PATH) -> None:
    faiss.write_index(index, str(path))


def load_faiss_index(path: Path = INDEX_PATH) -> faiss.Index:
    if not path.exists():
        raise FileNotFoundError(f"FAISS index not found at {path}")
    return faiss.read_index(str(path))


def save_metadata(metadata: List[Dict[str, Any]], path: Path = META_PATH) -> None:
    with open(path, "wb") as f:
        pickle.dump(metadata, f)


def load_metadata(path: Path = META_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Metadata file not found at {path}")
    with open(path, "rb") as f:
        return pickle.load(f)


def search_index(
    index: faiss.Index,
    query_vector: np.ndarray,
    k: int = 5
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Search the FAISS index. query_vector should be shape (1, dim).
    Returns (distances, indices).
    """
    distances, indices = index.search(query_vector.astype(np.float32), k)
    return distances, indices