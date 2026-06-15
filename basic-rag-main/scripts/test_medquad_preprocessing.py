from rag.loader import load_documents
from rag.chunker import chunk_documents


def main():
    docs = load_documents()
    print("Loaded docs:", len(docs))
    if not docs:
        print("No documents loaded. Check CSV_PATH and column names.")
        return

    chunks = chunk_documents(docs, chunk_size=500, overlap=100)
    print("Total chunks:", len(chunks))

    print("\nExample document:\n", docs[0].text)
    print("\nExample chunk:\n", chunks[0]["text"])

if __name__ == "__main__":
    main()
