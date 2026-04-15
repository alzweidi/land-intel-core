FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/python:/app

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY python ./python
COPY services ./services
COPY db ./db

# TODO(spec Phase 2): install the `.[worker-geo]` extra once spatial workflows begin.
RUN pip install --upgrade pip && pip install .

EXPOSE 9101

CMD ["python", "-m", "services.worker.app.main"]

