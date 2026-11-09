# Runs the tracing demo. Traces go to /data; mount it to open trace.html on the host:
#   docker run --rm -v "$PWD/out:/data" exe404/16-agent-tracing-observability
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    LLM_PROVIDER=mock \
    TRACE_OUT_DIR=/data

RUN useradd --create-home --uid 10001 app && mkdir /data && chown app /data
WORKDIR /app

COPY requirements.txt pyproject.toml ./
COPY src ./src
COPY examples ./examples
COPY demo.py ./

USER app
CMD ["python", "demo.py"]
