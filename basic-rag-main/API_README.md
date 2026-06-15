# Medical RAG API - Shareable Endpoint

A **production-ready REST API** for medical Q&A using Retrieval-Augmented Generation.

Integrate this API into your application to provide AI-powered medical question answering powered by retrieved medical knowledge.

---

## 🎯 What This API Does

```
User Question → FAISS Search → Retrieve Context → Gemini LLM → Answer
```

Provides accurate, context-grounded medical answers backed by relevant knowledge base chunks.

---

## 📡 Quick Start

### 1. Get the API Running

```powershell
# Install dependencies
pip install -r requirements.txt

# Configure credentials
Copy-Item .env.example .env
# Edit .env with your credentials

# Build knowledge index (one time)
python -m scripts.build_index

# Start the API
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

### 2. Make Your First Request

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the symptoms of diabetes?", "k": 5}'
```

### 3. Integrate Into Your App

See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for examples in Python, JavaScript, and more.

---

## 📚 Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check |
| `POST` | `/ask` | Full answer with retrieved chunks |
| `POST` | `/ask/simple` | Quick answer only |

---

## 📖 Request & Response

**Request:**
```json
{
  "question": "What are the symptoms of diabetes?",
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
  "chunks": [...]
}
```

---

## 📁 Files to Share

Send these files to integrate the API:

- **`api.py`** - The API endpoint
- **`INTEGRATION_GUIDE.md`** - How to use and integrate
- **`requirements.txt`** - Dependencies
- **`Medical_RAG_API.postman_collection.json`** - Postman collection for testing
- **Full project folder** - For self-hosted deployment

---

## 🛠 Requirements

- Python 3.8+
- PostgreSQL (optional, for logging)
- Google Gemini API Key
- ~2GB disk for models and indexes

---

## 📖 Documentation

- **[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)** - How to integrate into your app
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - How to deploy
- **Interactive Docs**: `http://localhost:8000/docs`

---

## 🔑 Configuration

Create `.env` file:

```env
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-2.0-flash
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/db
```

---

## ✨ Features

✅ **Retrieval-Augmented Generation** - Grounded, factual answers  
✅ **FAISS Vector Search** - Fast similarity search  
✅ **Google Gemini LLM** - State-of-the-art language model  
✅ **PostgreSQL Logging** - Audit trail of all queries  
✅ **REST API** - Easy integration  
✅ **Production Ready** - Error handling, validation, documentation  

---

## 🚀 Next Steps

1. **Setup**: Follow [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)
2. **Test**: Use Postman or cURL
3. **Deploy**: See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
4. **Integrate**: Copy integration examples for your language

---

## 📞 Support

For issues or questions:
- Check `/docs` endpoint for API documentation
- See troubleshooting in INTEGRATION_GUIDE.md
- Verify `.env` configuration

---

**Status**: ✅ Production Ready | **Version**: 1.0.0
