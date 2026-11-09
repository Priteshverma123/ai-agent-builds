# Runs the scripted approval story. Run state lives in /data (mount a volume to keep runs between containers):
#   docker run --rm -v hitl:/data exe404/14-human-in-the-loop-approvals python demo.py pending
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    LLM_PROVIDER=mock \
    HITL_STATE_DIR=/data

RUN useradd --create-home --uid 10001 app && mkdir /data && chown app /data
WORKDIR /app

COPY requirements.txt pyproject.toml ./
COPY src ./src
COPY demo.py ./

USER app
VOLUME ["/data"]
CMD ["python", "demo.py"]
