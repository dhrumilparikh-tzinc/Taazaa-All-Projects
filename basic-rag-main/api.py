from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="Medical RAG API",
    description="Medical Q&A API",
    version="1.0.0"
)


# ============ Request Model ============
class AskRequest(BaseModel):
    question: str
    k: Optional[int] = 5


# ============ Endpoints ============
@app.get("/")
def root():
    return {"message": "Medical RAG API is running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "healthy", "message": "API is operational"}


@app.post("/ask")
def ask_question(request: AskRequest):
    """Ask a medical question"""
    try:
        from rag.generator import generate_answer
        
        result = generate_answer(request.question, k=request.k)
        
        # Try to log but don't fail if it errors
        try:
            from db.logger import log_interaction
            log_interaction(
                question=request.question,
                answer=result.get("answer", ""),
                chunks=result.get("chunks", [])
            )
        except:
            pass
        
        return {
            "status": "success",
            "question": request.question,
            "answer": result.get("answer", ""),
            "chunks": result.get("chunks", []),
            "num_chunks": len(result.get("chunks", []))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ask/simple")
def ask_simple(request: AskRequest):
    """Ask a question - simple response"""
    try:
        from rag.generator import generate_answer
        
        result = generate_answer(request.question, k=request.k)
        return {
            "question": request.question,
            "answer": result.get("answer", "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
