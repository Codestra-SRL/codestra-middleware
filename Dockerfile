FROM python:3.12.11-slim
RUN useradd --system --uid 10001 --create-home app
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir --disable-pip-version-check \
    'fastapi==0.116.1' 'uvicorn[standard]==0.35.0' \
    'pydantic-settings==2.10.1' 'sqlalchemy==2.0.43' \
    'asyncpg==0.30.0' 'alembic==1.16.4' \
    'redis==6.4.0' 'httpx==0.28.1' 'pytest==8.4.1' 'ruff==0.12.10' 'mypy==1.17.1'
USER app
EXPOSE 8095
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8095"]
