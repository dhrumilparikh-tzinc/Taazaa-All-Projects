from typing import List

import pandas as pd

from config import DATA_DIR
from rag.models import Document

CSV_PATH = DATA_DIR / "medquad.csv"
QUESTION_COL = "question"
ANSWER_COL = "answer"
CATEGORY_COL = "focus_area"
SOURCE_COL = "source"


def load_documents() -> List[Document]:
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found at {CSV_PATH}. Run python -m scripts.download_kaggle_data first."
        )

    df = pd.read_csv(CSV_PATH)
    df = df.dropna(subset=[QUESTION_COL, ANSWER_COL]).copy()
    df[QUESTION_COL] = df[QUESTION_COL].astype(str).str.strip()
    df[ANSWER_COL] = df[ANSWER_COL].astype(str).str.strip()
    df = df[(df[QUESTION_COL] != "") & (df[ANSWER_COL] != "")]

    documents: List[Document] = []
    for row in df.to_dict(orient="records"):
        parts = []
        metadata = {}

        if CATEGORY_COL in row and str(row[CATEGORY_COL]).strip():
            category = str(row[CATEGORY_COL]).strip()
            parts.append(f"Category: {category}")
            metadata["category"] = category

        if SOURCE_COL in row and str(row[SOURCE_COL]).strip():
            metadata["source"] = str(row[SOURCE_COL]).strip()

        question = row[QUESTION_COL]
        answer = row[ANSWER_COL]
        parts.append(f"Question: {question}")
        parts.append(f"Answer: {answer}")

        documents.append(Document(text="\n".join(parts), metadata=metadata))

    return documents


if __name__ == "__main__":
    docs = load_documents()
    print("Loaded", len(docs), "documents")
    print("Example document:\n", docs[0].text)
