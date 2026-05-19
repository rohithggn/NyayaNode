FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for layer cache optimization
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend
COPY . .

# Railway injects $PORT at runtime
EXPOSE 8000

# Liveness probe — GET /health every 30s, timeout 10s, 3 retries
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/health')"

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
