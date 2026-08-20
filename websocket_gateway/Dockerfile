FROM python:3.13.15-alpine3.23@sha256:7ea3f82de8ea6d4fb7e5d2bbe3fe3c9d931700b7a529f1fe5769e42abe514ca1 AS builder
WORKDIR /build
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
 && pip uninstall -y pip setuptools wheel

FROM alpine@sha256:48b0309ca019d89d40f670aa1bc06e426dc0931948452e8491e3d65087abc07d
ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://github.com/Codestra-SRL/codestra-middleware" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.title="Codestra WebSocket Gateway"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apk add --no-cache \
      ca-certificates=20260413-r0 \
      gdbm=1.24-r0 \
      libbz2=1.0.8-r6 \
      libffi=3.4.7-r0 \
      libuuid=2.40.4-r1 \
      ncurses-libs=6.5_p20241006-r3 \
      openssl=3.3.7-r0 \
      readline=8.2.13-r0 \
      xz-libs=5.8.3-r0 \
      zlib=1.3.2-r0 \
 && addgroup -S -g 10001 codestra \
 && adduser -S -D -H -u 10001 -G codestra codestra
COPY --from=builder /usr/local /usr/local
WORKDIR /app
COPY app.py migrate.py ./
COPY migrations ./migrations
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--ws-ping-interval", "25", "--ws-ping-timeout", "10", "--timeout-graceful-shutdown", "10", "--no-access-log"]
