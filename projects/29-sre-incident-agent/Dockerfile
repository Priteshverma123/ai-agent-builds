# SRE incident agent: replays ALERT-5521 with scripted on-call answers and writes the postmortem.
# Interactive approvals: docker run -it --rm IMAGE python demo.py --interactive
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SRE_OUT_DIR=/app/out

WORKDIR /app
# Runtime is stdlib only; httpx is installed so a real LLM provider can be switched on with env vars.
RUN pip install --no-cache-dir httpx==0.28.1

COPY src ./src
COPY examples ./examples
COPY demo.py ./

# Run as an unprivileged user that may write only the output folder.
RUN useradd --create-home appuser && mkdir -p /app/out && chown appuser /app/out
USER appuser

CMD ["python", "demo.py"]
