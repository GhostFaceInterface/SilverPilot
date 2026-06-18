FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin silverpilot

COPY pyproject.toml ROADMAP.md ./
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install .

USER silverpilot

EXPOSE 8000

CMD ["uvicorn", "silverpilot.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
