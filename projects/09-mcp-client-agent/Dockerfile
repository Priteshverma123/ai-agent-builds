# 09-mcp-client-agent: runs the offline demo (MockLLM, no API key needed).
# The demo launches ../08-mcp-server-from-scratch/server.py, so build from the projects/ folder:
#   cd projects && docker build -f 09-mcp-client-agent/Dockerfile -t mcp-client-agent .
#   docker run --rm mcp-client-agent
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/09-mcp-client-agent/src

RUN useradd --create-home --uid 10001 app

# Keep the sibling layout so examples/servers.json (../../08-.../server.py) still resolves.
COPY 08-mcp-server-from-scratch/server.py /app/08-mcp-server-from-scratch/server.py
COPY 08-mcp-server-from-scratch/src /app/08-mcp-server-from-scratch/src
COPY 08-mcp-server-from-scratch/examples /app/08-mcp-server-from-scratch/examples
COPY 09-mcp-client-agent/requirements.txt 09-mcp-client-agent/pyproject.toml 09-mcp-client-agent/demo.py /app/09-mcp-client-agent/
COPY 09-mcp-client-agent/src /app/09-mcp-client-agent/src
COPY 09-mcp-client-agent/examples /app/09-mcp-client-agent/examples

WORKDIR /app/09-mcp-client-agent
USER app
CMD ["python", "demo.py"]
