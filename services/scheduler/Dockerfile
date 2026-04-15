FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/python:/app

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY python ./python
COPY services ./services
COPY db ./db

RUN pip install --upgrade pip && pip install .

CMD ["python", "-m", "services.scheduler.app.main"]

