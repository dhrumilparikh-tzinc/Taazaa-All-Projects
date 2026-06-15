# Deploy Medical RAG API

This guide explains how to deploy the Medical RAG API for sharing with others.

---

## 🚀 Deployment Options

### Option 1: Local Deployment (Development)

**For testing and development purposes**

1. **Activate virtual environment**
```powershell
.\.venv\Scripts\Activate.ps1
```

2. **Start the API**
```powershell
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

3. **Share the URL**
```
http://your-machine-ip:8000
```

---

### Option 2: Systemd Service (Linux)

**For production Linux deployment**

Create `/etc/systemd/system/medical-rag.service`:

```ini
[Unit]
Description=Medical RAG API
After=network.target

[Service]
Type=notify
User=your-user
WorkingDirectory=/path/to/basic_rag_assignment
ExecStart=/path/to/basic_rag_assignment/.venv/bin/python -m uvicorn api:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl start medical-rag
sudo systemctl enable medical-rag
```

---

### Option 3: Docker (Recommended for Production)

**Coming soon**: Docker containerization for easy cross-platform deployment

---

### Option 4: Cloud Deployment

#### AWS EC2
1. Launch an EC2 instance
2. Install Python and PostgreSQL
3. Clone the repo
4. Run the setup steps from INTEGRATION_GUIDE.md
5. Use a load balancer (ALB) in front

#### Google Cloud Run
1. Create a `Dockerfile` (will be added)
2. Push to Container Registry
3. Deploy to Cloud Run

#### Heroku
1. Add Procfile:
```
web: python -m uvicorn api:app --host 0.0.0.0 --port $PORT
```
2. Deploy via git

---

## 🔧 Production Configuration

### Gunicorn + Uvicorn (Multiple workers)

```powershell
pip install gunicorn

gunicorn api:app `
  --workers 4 `
  --worker-class uvicorn.workers.UvicornWorker `
  --bind 0.0.0.0:8000 `
  --access-logfile - `
  --error-logfile -
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 📋 Deployment Checklist

- [ ] Database configured and running
- [ ] Environment variables set in `.env`
- [ ] FAISS index built (`scripts/build_index.py`)
- [ ] API tested locally
- [ ] Gemini API key is valid
- [ ] Logging configured
- [ ] Firewall rules allow port 8000
- [ ] HTTPS configured (for production)

---

## 🔐 Production Security

1. **Use environment variables** for all secrets
2. **Enable HTTPS/TLS** in production
3. **Add rate limiting** (example below)
4. **Add authentication** if needed
5. **Use strong database credentials**
6. **Keep dependencies updated**

---

## 📊 Monitoring

Add monitoring to track:
- API response times
- Error rates
- Database query performance
- Gemini API usage

---

## ✅ Verification

After deployment, verify the API:

```bash
# Health check
curl http://your-deployment-url:8000/health

# Test endpoint
curl -X POST http://your-deployment-url:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is diabetes?", "k": 3}'
```

---

## 🎯 Sharing the API

Once deployed, share:
1. **API URL**: `http://your-host:8000`
2. **Documentation**: Point to `/docs` endpoint
3. **Integration Guide**: Share `INTEGRATION_GUIDE.md`
4. **Postman Collection**: Share `Medical_RAG_API.postman_collection.json`

---

**That's it!** Your API is now ready to be integrated by others.
