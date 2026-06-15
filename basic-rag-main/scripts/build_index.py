from typing import List, Dict, Any

from rag.loader import load_documents
from rag.chunker import chunk_documents
from rag.embedder import Embedder
from rag.faiss_store import (
    build_faiss_index,
    save_faiss_index,
    save_metadata,
    FAISS_DIR,
)


def main():
    print("Loading documents...")
    documents = load_documents()
    print(f"Loaded {len(documents)} documents")

    print("Chunking documents...")
    chunks: List[Dict[str, Any]] = chunk_documents(documents, chunk_size=500, overlap=100)
    print(f"Total chunks: {len(chunks)}")

    metadata: List[Dict[str, Any]] = []
    chunk_texts: List[str] = []
    for idx, chunk in enumerate(chunks):
        metadata.append(
            {
                "chunk_id": idx,
                "text": chunk["text"],
                "doc_id": chunk["doc_id"],
                "chunk_in_doc": chunk["chunk_in_doc"],
                "metadata": chunk["metadata"],
            }
        )
        chunk_texts.append(chunk["text"])

    print("Embedding chunks...")
    embedder = Embedder()
    embeddings = embedder.embed_texts(chunk_texts)
    print(f"Embeddings shape: {embeddings.shape}")

    print("Building FAISS index...")
    index = build_faiss_index(embeddings)

    print("Saving index and metadata...")
    FAISS_DIR.mkdir(exist_ok=True)
    save_faiss_index(index)
    save_metadata(metadata)

    print("Done. Index and metadata saved in", FAISS_DIR)


if __name__ == "__main__":
    main()
