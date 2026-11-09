# Runs the offline demo. Override the command to pick one scenario:
#   docker run --rm exe404/13-guardrails-prompt-injection python demo.py --scenario 3
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    LLM_PROVIDER=mock

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY requirements.txt pyproject.toml ./
COPY src ./src
COPY examples ./examples
COPY demo.py ./

USER app
CMD ["python", "demo.py"]
