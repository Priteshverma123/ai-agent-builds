# Runs the offline demo by default. Pass env vars (see .env.example) to use a real provider.
#   docker build -t toolcall .                                    # offline (MockLLM)
#   docker build -t toolcall --build-arg PROVIDER_SDK=anthropic .  # bake in a provider SDK
#   docker run --rm toolcall [CLI args...]
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

ARG PROVIDER_SDK=""
RUN if [ -n "$PROVIDER_SDK" ]; then pip install --no-cache-dir "$PROVIDER_SDK"; fi

RUN useradd --create-home --uid 10001 app

COPY pyproject.toml README.md demo.py ./
COPY src ./src
COPY examples ./examples

USER app
ENTRYPOINT ["python", "demo.py"]
