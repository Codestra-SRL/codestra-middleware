FROM python:3.12.11-slim
WORKDIR /srv/codestra
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && useradd --system --uid 12001 --home /nonexistent codestra
COPY app /srv/codestra/app
USER 12001
ENV PYTHONPATH=/srv/codestra PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.email.runtime:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
