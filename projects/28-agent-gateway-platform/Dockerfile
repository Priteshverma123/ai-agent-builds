# Agent gateway API (FastAPI + uvicorn), non-root. `docker run --rm IMAGE python demo.py` runs the demo instead.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app
# Runtime deps only (pytest stays out of the image).
RUN pip install --no-cache-dir fastapi==0.115.8 uvicorn==0.34.0 pydantic==2.10.6 httpx==0.28.1

COPY src ./src
COPY examples ./examples
COPY demo.py ./

# Run as an unprivileged user; /app/out is the only writable place (e.g. GATEWAY_AUDIT_FILE=/app/out/audit.jsonl).
RUN useradd --create-home appuser && mkdir -p /app/out && chown appuser /app/out
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["python", "-m", "gateway.cli", "serve"]
