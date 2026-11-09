# 08-mcp-server-from-scratch: runs the offline demo by default (MockLLM, no API key needed).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
RUN useradd --create-home --uid 10001 app

COPY requirements.txt pyproject.toml ./
COPY src ./src
COPY examples ./examples
COPY server.py demo.py ./

USER app
# Serve MCP instead: docker run -i --rm <image> python server.py
CMD ["python", "demo.py"]
