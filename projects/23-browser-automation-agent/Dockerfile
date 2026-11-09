# Small, reproducible image that runs the offline demo by default.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 10001 app

COPY requirements.txt pyproject.toml ./
RUN pip install -r requirements.txt

COPY src ./src
COPY examples ./examples
COPY demo.py ./

USER app

# Override at run time, e.g. `docker run --rm -e LLM_PROVIDER=anthropic -e ANTHROPIC_API_KEY=... `
CMD ["python", "demo.py"]
