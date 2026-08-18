FROM python:3.13-alpine@sha256:540c7d91f98ff6880174c40e99067bf5941eb54d818a7a5e094d188b196a934d
ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://github.com/Codestra-SRL/codestra-middleware" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.title="Codestra WebSocket Gateway"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apk upgrade --no-cache \
 && addgroup -S -g 10001 codestra \
 && adduser -S -D -H -u 10001 -G codestra codestra
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
 && pip uninstall -y pip setuptools wheel
COPY app.py migrate.py ./
COPY migrations ./migrations
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--ws-ping-interval", "25", "--ws-ping-timeout", "10", "--timeout-graceful-shutdown", "10", "--no-access-log"]
