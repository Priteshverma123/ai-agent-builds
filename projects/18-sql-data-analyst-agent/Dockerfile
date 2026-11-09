# Runs the SQL analyst demo. Ask your own question:
#   docker run --rm exe404/18-sql-data-analyst-agent python demo.py --json "How many customers do we have?"
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    LLM_PROVIDER=mock \
    SQL_DB_PATH=/tmp/sql_analyst_shop.db

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir pydantic==2.10.6
COPY src ./src
COPY examples ./examples
COPY demo.py ./

USER app
CMD ["python", "demo.py"]
