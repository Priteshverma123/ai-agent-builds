# Runs the offline demo by default. Pass env vars (see .env.example) to use a real provider.
#   docker build -t structured-extractor .                                    # offline (MockLLM)
#   docker build -t structured-extractor --build-arg PROVIDER_SDK=anthropic .  # bake in a provider SDK
#   docker run --rm structured-extractor [CLI args...]
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir pydantic==2.10.6

ARG PROVIDER_SDK=""
RUN if [ -n "$PROVIDER_SDK" ]; then pip install --no-cache-dir "$PROVIDER_SDK"; fi

RUN useradd --create-home --uid 10001 app

COPY pyproject.toml README.md demo.py ./
COPY src ./src
COPY examples ./examples

USER app
ENTRYPOINT ["python", "demo.py"]
