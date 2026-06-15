# Medical RAG API - For Integration

This is a **shareable Medical RAG API** that can be easily integrated into any application.

## 🎯 What You Get

A production-ready REST API endpoint for medical Q&A using Retrieval-Augmented Generation. Anyone with the API key can integrate this into their application.

---

## 🚀 Quick Integration Guide

### Option 1: Use the Live API Endpoint
If the API is hosted, you can directly integrate using the endpoint URL.

**Base URL:** `http://your-api-host:8000`

### Option 2: Deploy Locally or Self-Hosted

#### Prerequisites
- Python 3.8+
- PostgreSQL (for logging)
- Google Gemini API Key

#### Setup Steps

1. **Clone/Copy the project**
```powershell
cd your-project-path
```

2. **Create virtual environment**
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. **Install dependencies**
```powershell
pip install -r requirements.txt
```

4. **Configure environment**
```powershell
# Copy and fill in your credentials
Copy-Item .env.example .env
# Edit .env with your credentials
```

5. **Initialize database** (optional, for logging)
```powershell
.\.venv\Scripts\python.exe -m scripts.init_db
```

6. **Build FAISS index** (first time only)
```powershell
.\.venv\Scripts\python.exe -m scripts.build_index
```

7. **Start the API server**
```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --host 0.0.0.0 --port 8000
```

---

## 📡 API Endpoints

### POST /ask
**Ask a medical question with full context**

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the symptoms of diabetes?",
    "k": 5
  }'
```

**Request:**
```json
{
  "question": "Your medical question here",
  "k": 5
}
```

**Response:**
```json
{
  "status": "success",
  "question": "What are the symptoms of diabetes?",
  "answer": "Based on retrieved medical context...",
  "num_chunks": 5,
  "chunks": [
    {
      "chunk_id": 0,
      "text": "Symptom details...",
      "distance": 0.1234,
      "metadata": {
        "category": "Endocrinology",
        "source": "Medical Database"
      }
    }
  ]
}
```

---

### POST /ask/simple
**Quick answer without chunk details**

```bash
curl -X POST http://localhost:8000/ask/simple \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How to treat high blood pressure?"
  }'
```

**Response:**
```json
{
  "question": "How to treat high blood pressure?",
  "answer": "Based on retrieved context, treatment options include..."
}
```

---

### GET /health
**Health check**

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "message": "Medical RAG API is operational"
}
```

---

## 💻 Integration Examples

### Python
```python
import requests

BASE_URL = "http://localhost:8000"

def ask_medical_question(question: str, k: int = 5):
    response = requests.post(
        f"{BASE_URL}/ask",
        json={"question": question, "k": k}
    )
    result = response.json()
    
    if result["status"] == "success":
        print(f"Q: {result['question']}")
        print(f"A: {result['answer']}")
        return result
    else:
        print(f"Error: {result}")
        return None

# Usage
ask_medical_question("What are symptoms of diabetes?")
```

### JavaScript/Node.js
```javascript
async function askMedicalQuestion(question, k = 5) {
  const response = await fetch('http://localhost:8000/ask', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      question: question,
      k: k
    })
  });
  
  const result = await response.json();
  console.log(result.answer);
  return result;
}

// Usage
askMedicalQuestion("What causes arthritis?");
```

### cURL
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What are blood pressure symptoms?","k":5}'
```

### Postman
Import the provided `Medical_RAG_API.postman_collection.json` file for pre-configured requests.

---

## 🔐 Configuration

Create a `.env` file with:

```env
# Gemini API
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# PostgreSQL (optional, for logging)
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/basic_rag

# Kaggle (optional, for rebuilding index)
KAGGLE_USERNAME=your_username
KAGGLE_KEY=your_key
```

---

## 📊 Response Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request (invalid input) |
| 500 | Server Error |

---

## 🎯 Usage Tips

1. **First request is slower** (models load on startup)
2. **Reduce `k`** for faster responses (use k=3 instead of k=5)
3. **Use `/ask/simple`** if you only need the answer
4. **Questions are logged** to PostgreSQL automatically (if configured)

---

## 📈 Performance Notes

- **Response Time**: 3-10 seconds (depends on model loading and external API)
- **Concurrent Requests**: Can handle multiple simultaneous requests
- **Database Logging**: Non-blocking (won't slow down responses)

---

## 🆘 Troubleshooting

**Issue:** "Connection refused on port 8000"
- Solution: Make sure the API server is running

**Issue:** "FAISS index not found"
- Solution: Run `python -m scripts.build_index`

**Issue:** "Gemini API quota exceeded"
- Solution: Check your Google Gemini API quota or use a new API key

**Issue:** "Database error" in logs
- Solution: Database logging is optional. Errors won't break the API response.

---

## 📝 API Documentation

For interactive API documentation, once the server is running:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🤝 Sharing This API

To share this API with others:

1. **Self-hosted**: Deploy on your server, share the URL
2. **Docker**: Package it in a container (coming soon)
3. **Cloud**: Deploy to AWS/GCP/Azure

Anyone with the endpoint URL can integrate it into their applications using the examples above.

---

## ✅ What's Included

- ✅ Complete Medical RAG pipeline
- ✅ FastAPI REST endpoints
- ✅ PostgreSQL logging
- ✅ Automatic FAISS indexing
- ✅ Gemini LLM integration
- ✅ Production-ready code
- ✅ Error handling & validation

---

**Version**: 1.0.0  
**Status**: Production Ready
