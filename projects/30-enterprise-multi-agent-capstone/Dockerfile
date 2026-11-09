# Enterprise assistant: FastAPI front door + orchestrator + in-process MCP tools.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DOCS_DIR=/app/examples/docs \
    TRACE_FILE=/app/out/traces.jsonl

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY examples ./examples
COPY run_evals.py demo.py ./

# Run as an unprivileged user.
RUN useradd --create-home appuser && mkdir -p /app/out && chown -R appuser /app/out
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "capstone.serve:app", "--host", "0.0.0.0", "--port", "8000"]
