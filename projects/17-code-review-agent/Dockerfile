# Reviews the bundled example diff. To review your own repo, mount it and pipe a diff in:
#   git diff | docker run --rm -i -v "$PWD:/repo:ro" exe404/17-code-review-agent python demo.py --diff - --base /repo
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    LLM_PROVIDER=mock

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir pydantic==2.10.6
COPY src ./src
COPY examples ./examples
COPY demo.py ./

USER app
CMD ["python", "demo.py"]
