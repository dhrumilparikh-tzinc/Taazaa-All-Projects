FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs

EXPOSE 7860

CMD ["uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "7860"]
