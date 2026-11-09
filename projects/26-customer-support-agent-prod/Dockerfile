# Customer support agent API (FastAPI + uvicorn), non-root.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SUPPORT_TODAY=2026-10-20

# Runtime deps only (pytest stays out of the image).
RUN pip install --no-cache-dir fastapi==0.115.8 uvicorn==0.34.0 pydantic==2.10.6 httpx==0.28.1

COPY src ./src
COPY examples ./examples

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "support_agent.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
