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

EXPOSE 8000

CMD ["uvicorn", "services.api.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

