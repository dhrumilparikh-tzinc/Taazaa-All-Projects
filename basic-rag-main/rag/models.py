from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Document:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnswerResult:
    question: str
    answer: str
    chunks: List[Dict[str, Any]]
