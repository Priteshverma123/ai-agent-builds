# Durable agent workflows: runs the four-act crash/resume demo.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DURABLE_DATA_DIR=/app/data

WORKDIR /app
# Runtime is stdlib only, so there is nothing to pip install.
COPY src ./src
COPY demo.py ./

# Run as an unprivileged user that owns only the data directory.
RUN useradd --create-home appuser && mkdir -p /app/data && chown appuser /app/data
USER appuser

CMD ["python", "demo.py"]
