from typing import Dict, List

from rag.models import Document


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """
    Split a string into overlapping character chunks.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap < 0:
        raise ValueError("overlap must be at least 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunks.append(text[start:end])
        if end >= text_length:
            break
        start = end - overlap

    return chunks


def chunk_documents(
    documents: List[Document],
    chunk_size: int = 500,
    overlap: int = 100,
) -> List[Dict[str, object]]:
    all_chunks: List[Dict[str, object]] = []
    for doc_id, doc in enumerate(documents):
        doc_chunks = chunk_text(doc.text, chunk_size=chunk_size, overlap=overlap)
        for chunk_index, chunk in enumerate(doc_chunks):
            all_chunks.append(
                {
                    "text": chunk,
                    "doc_id": doc_id,
                    "chunk_in_doc": chunk_index,
                    "metadata": dict(doc.metadata),
                }
            )
    return all_chunks


if __name__ == "__main__":
    sample = "This is a sample long text. " * 50
    cs = chunk_text(sample, chunk_size=100, overlap=20)
    print("Chunks:", len(cs))
    print(cs[0])
