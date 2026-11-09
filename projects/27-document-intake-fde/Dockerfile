# Document intake pipeline: runs the batch over the sample inbox (override CMD for `run` or `eval`).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    INTAKE_OUT_DIR=/app/out

WORKDIR /app
# Runtime deps only (pytest stays out of the image).
RUN pip install --no-cache-dir pydantic==2.10.6

COPY src ./src
COPY examples ./examples
COPY run.py demo.py ./

# Run as an unprivileged user that may write only the output folder.
RUN useradd --create-home appuser && mkdir -p /app/out && chown appuser /app/out
USER appuser

CMD ["python", "run.py", "demo"]
