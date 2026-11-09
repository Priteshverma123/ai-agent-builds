# Runs the evals story. As a CI gate:
#   docker run --rm exe404/15-agent-evals-harness python demo.py run --agent v2   # exit code 1 = regression
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    LLM_PROVIDER=mock \
    EVAL_OUT_DIR=/tmp/evals

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir pydantic==2.10.6
COPY src ./src
COPY examples ./examples
COPY demo.py ./

USER app
CMD ["python", "demo.py"]
