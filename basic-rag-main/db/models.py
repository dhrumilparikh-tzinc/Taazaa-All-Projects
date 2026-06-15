from sqlalchemy import Column, Integer, Text, DateTime
from sqlalchemy.sql import func

from db.db import Base


class Interaction(Base):
    __tablename__ = "qa_logs"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    context = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)

    # server_default=func.now() lets PostgreSQL set the current timestamp
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Optional fields as plain text (you can store JSON strings here)
    similarity_scores = Column(Text, nullable=True)
    chunk_ids = Column(Text, nullable=True)