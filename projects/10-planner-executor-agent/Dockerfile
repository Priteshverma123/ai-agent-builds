# 10-planner-executor-agent: runs the offline demo by default (MockLLM, no API key needed).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
RUN useradd --create-home --uid 10001 app

COPY requirements.txt pyproject.toml ./
COPY src ./src
COPY examples ./examples
COPY demo.py ./

USER app
CMD ["python", "demo.py"]
