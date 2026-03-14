FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bundle_analyzer/ bundle_analyzer/

CMD uvicorn bundle_analyzer.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
