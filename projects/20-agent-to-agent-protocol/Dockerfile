# Small, reproducible image that runs the offline demo by default.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \n    PYTHONPATH=/app/src

WORKDIR /app

RUN useradd --create-home --uid 10001 app

COPY requirements.txt pyproject.toml ./
RUN pip install -r requirements.txt

COPY src ./src
COPY examples ./examples
COPY demo.py ./

USER app

# Override at run time, e.g. `docker run --rm -e LLM_PROVIDER=anthropic -e ANTHROPIC_API_KEY=... `
# Serve one agent instead:
#   docker run --rm -p 8001:8001 -e A2A_HOST=0.0.0.0 agent-to-agent-protocol python -m a2a_local --serve fx
CMD ["python", "demo.py"]
