# Python 3.12.13 / Alpine 3.24 (Docker Official Image).
ARG PYTHON_BASE=docker.io/library/python@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df
ARG VCS_REF=unknown
ARG BUILD_REVISION=unknown

FROM ${PYTHON_BASE} AS builder
ARG VCS_REF
ARG BUILD_REVISION
LABEL org.opencontainers.image.source="https://github.com/Codestra-SRL/codestra-middleware" \
      org.opencontainers.image.revision="${VCS_REF}" \
      io.codestra.build.revision="${BUILD_REVISION}" \
      io.codestra.python.base.repository="docker.io/library/python" \
      io.codestra.python.base.digest="sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df" \
      io.codestra.python.version="3.12.13"
USER root
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.lock requirements-test.lock ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
      --require-hashes -r requirements.lock

FROM builder AS test
RUN apk add --no-cache openssl=3.5.7-r0
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
      --require-hashes -r requirements-test.lock
WORKDIR /app
COPY --chown=10001:10001 . /app
ENV PYTHONPATH=/app
USER 10001:10001
ENTRYPOINT ["pytest"]

FROM ${PYTHON_BASE} AS runtime
ARG VCS_REF
ARG BUILD_REVISION
LABEL org.opencontainers.image.source="https://github.com/Codestra-SRL/codestra-middleware" \
      org.opencontainers.image.revision="${VCS_REF}" \
      io.codestra.build.revision="${BUILD_REVISION}" \
      io.codestra.python.base.repository="docker.io/library/python" \
      io.codestra.python.base.digest="sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df" \
      io.codestra.python.version="3.12.13"
USER root
RUN grep -q '^app:' /etc/group || addgroup -S -g 10001 app \
 && grep -q '^app:' /etc/passwd || adduser -S -D -H -u 10001 -G app app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=10001:10001 alembic.ini app.py ./
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 migrations ./migrations
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8095
CMD ["python", "-m", "app.entrypoints.integration_api"]
