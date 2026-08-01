# Docker Official Image Python 3.12.13 / Debian 12 slim-bookworm.
ARG PYTHON_BASE=docker.io/library/python:3.12.13-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b
ARG VCS_REF=unknown
ARG BUILD_REVISION=unknown
ARG BUILD_CREATED=unknown
ARG BUILD_VERSION=unknown

FROM ${PYTHON_BASE} AS builder
ARG VCS_REF
ARG BUILD_REVISION
ARG BUILD_CREATED
ARG BUILD_VERSION
LABEL org.opencontainers.image.source="https://github.com/Codestra-SRL/codestra-middleware" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      io.codestra.build.revision="${BUILD_REVISION}" \
      io.codestra.python.base.repository="docker.io/library/python" \
      io.codestra.python.base.digest="sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b" \
      io.codestra.python.version="3.12.13"
USER root
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.lock requirements-test.lock ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
      --require-hashes -r requirements.lock

FROM builder AS test
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssl \
 && rm -rf /var/lib/apt/lists/*
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
ARG BUILD_CREATED
ARG BUILD_VERSION
LABEL org.opencontainers.image.source="https://github.com/Codestra-SRL/codestra-middleware" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      io.codestra.build.revision="${BUILD_REVISION}" \
      io.codestra.python.base.repository="docker.io/library/python" \
      io.codestra.python.base.digest="sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b" \
      io.codestra.python.version="3.12.13"
USER root
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=10001:10001 alembic.ini app.py ./
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 migrations ./migrations
COPY --chown=10001:10001 schemas ./schemas
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8095
CMD ["python", "-m", "app.entrypoints.integration_api"]
