# CPython 3.12.14 built on Alpine 3.21. OpenSSL 3.3 avoids the OpenSSL 3.5-only
# QUIC listener vulnerability while retaining the supported Python 3.12 line.
ARG PYTHON_BASE=docker.io/library/alpine@sha256:48b0309ca019d89d40f670aa1bc06e426dc0931948452e8491e3d65087abc07d
ARG VCS_REF=unknown
ARG BUILD_REVISION=unknown
ARG BUILD_CREATED=unknown

FROM ${PYTHON_BASE} AS python-builder
USER root
ARG PYTHON_SOURCE_SHA256=5c8462af5790baf43a321a1559dbe0db06d1be4300fb85fb53c40060668e548a
WORKDIR /usr/src
RUN apk add --no-cache \
      build-base=0.5-r3 \
      bzip2-dev=1.0.8-r6 \
      curl=8.14.1-r2 \
      expat-dev=2.8.3-r0 \
      gdbm-dev=1.24-r0 \
      libffi-dev=3.4.7-r0 \
      linux-headers=6.6-r1 \
      ncurses-dev=6.5_p20241006-r3 \
      openssl-dev=3.3.7-r0 \
      patch=2.7.6-r10 \
      readline-dev=8.2.13-r0 \
      tar=1.35-r2 \
      xz-dev=5.8.3-r0 \
      zlib-dev=1.3.2-r0
COPY security/python312/*.patch /usr/src/patches/
RUN curl --fail --location --proto '=https' --tlsv1.2 \
      --output Python-3.12.14.tar.xz \
      https://www.python.org/ftp/python/3.12.14/Python-3.12.14.tar.xz \
 && echo "${PYTHON_SOURCE_SHA256}  Python-3.12.14.tar.xz" | sha256sum -c - \
 && mkdir upstream-patches \
 && while read -r commit checksum; do \
      curl --fail --location --proto '=https' --tlsv1.2 \
        --output "upstream-patches/${commit}.patch" \
        "https://github.com/python/cpython/commit/${commit}.patch"; \
      echo "${checksum}  upstream-patches/${commit}.patch" | sha256sum -c -; \
    done <<'PATCHES'
dae4b1a21f8df4570e30986affd61bbe4ade4cef da243766f48c8f78cc292559df5baedab3046ffcee3f754fb716b27e13952a7c
642865ddf4b232da1f3b1f7abcfa3254c4bfe785 afcdbd51c751170f703451aef3cfdd40a61bce2c05180cfcf87ff19c2c99f865
fc9b11ff49cbc82e6f917d07a61517a2b5f3145f e24d1474438cce8df94b8b5e336599326956e6f8cc1cf211932349230fd3ef28
PATCHES
RUN tar -xJf Python-3.12.14.tar.xz \
 && awk 'found || index($0, "diff --git a/Include/pyexpat.h") == 1 { found=1; print }' \
      upstream-patches/fc9b11ff49cbc82e6f917d07a61517a2b5f3145f.patch \
      > upstream-patches/fc9b11ff49cbc82e6f917d07a61517a2b5f3145f-3.12-rest.patch \
 && cd Python-3.12.14 \
 && for patch_file in \
      ../upstream-patches/dae4b1a21f8df4570e30986affd61bbe4ade4cef.patch \
      ../upstream-patches/642865ddf4b232da1f3b1f7abcfa3254c4bfe785.patch \
      ../upstream-patches/fc9b11ff49cbc82e6f917d07a61517a2b5f3145f-3.12-rest.patch \
      ../patches/expat-hash-salt-3.12.patch; do \
        patch -p1 --batch < "${patch_file}"; \
    done \
 && ./configure \
      --enable-loadable-sqlite-extensions \
      --enable-option-checking=fatal \
      --enable-shared \
      --with-ensurepip \
      --with-system-expat \
 && make -j"$(nproc)" \
 && make install

FROM ${PYTHON_BASE} AS patched-python
USER root
RUN apk add --no-cache \
      expat=2.8.3-r0 \
      gdbm=1.24-r0 \
      libbz2=1.0.8-r6 \
      libffi=3.4.7-r0 \
      ncurses-libs=6.5_p20241006-r3 \
      openssl=3.3.7-r0 \
      readline=8.2.13-r0 \
      tzdata=2026c-r0 \
      xz-libs=5.8.3-r0 \
      zlib=1.3.2-r0
RUN rm -rf /usr/local/*
COPY --from=python-builder /usr/local /usr/local
RUN ln -s python3 /usr/local/bin/python

FROM patched-python AS builder
ARG VCS_REF
ARG BUILD_REVISION
ARG BUILD_CREATED
LABEL org.opencontainers.image.source="https://github.com/Codestra-SRL/codestra-middleware" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_CREATED}" \
      io.codestra.build.revision="${BUILD_REVISION}" \
      io.codestra.python.base.repository="docker.io/library/alpine" \
      io.codestra.python.base.digest="sha256:48b0309ca019d89d40f670aa1bc06e426dc0931948452e8491e3d65087abc07d" \
      io.codestra.python.version="3.12.14"
USER root
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.lock requirements-test.lock ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
      --require-hashes -r requirements.lock

FROM builder AS test
RUN apk add --no-cache bash=5.2.37-r0 git=2.47.3-r0 openssl=3.3.7-r0
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
      --require-hashes -r requirements-test.lock
WORKDIR /app
COPY --chown=10001:10001 . /app
ENV PYTHONPATH=/app
USER 10001:10001
ENTRYPOINT ["pytest"]

FROM patched-python AS runtime
ARG VCS_REF
ARG BUILD_REVISION
ARG BUILD_CREATED
LABEL org.opencontainers.image.source="https://github.com/Codestra-SRL/codestra-middleware" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_CREATED}" \
      io.codestra.build.revision="${BUILD_REVISION}" \
      io.codestra.python.base.repository="docker.io/library/alpine" \
      io.codestra.python.base.digest="sha256:48b0309ca019d89d40f670aa1bc06e426dc0931948452e8491e3d65087abc07d" \
      io.codestra.python.version="3.12.14"
USER root
RUN grep -q '^app:' /etc/group || addgroup -S -g 10001 app \
 && grep -q '^app:' /etc/passwd || adduser -S -D -H -u 10001 -G app app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=10001:10001 alembic.ini app.py ./
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 migrations ./migrations
COPY --chown=10001:10001 schemas ./schemas
COPY --chown=10001:10001 scripts ./scripts
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8095
CMD ["python", "-m", "app.entrypoints.integration_api"]

FROM patched-python AS qwen-auth-verifier-runtime
ARG VCS_REF
ARG BUILD_REVISION
LABEL org.opencontainers.image.title="Codestra Qwen Authentication Verifier" \
      org.opencontainers.image.description="Read-only private mTLS and HMAC authentication verifier" \
      org.opencontainers.image.source="https://github.com/Codestra-SRL/codestra-middleware" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="1.0.0-rc1" \
      io.codestra.build.revision="${BUILD_REVISION}" \
      io.codestra.python.base.repository="docker.io/library/alpine" \
      io.codestra.python.base.digest="sha256:48b0309ca019d89d40f670aa1bc06e426dc0931948452e8491e3d65087abc07d" \
      io.codestra.python.version="3.12.14"
USER root
RUN grep -q '^app:' /etc/group || addgroup -S -g 10001 app \
 && grep -q '^app:' /etc/passwd || adduser -S -D -H -u 10001 -G app app
COPY --from=builder /opt/venv /opt/venv
RUN /opt/venv/bin/python -m pip uninstall -y \
      alembic asyncpg greenlet httpcore httpx mako markupsafe prometheus-client \
      pyjwt python-dotenv redis sqlalchemy pydantic-settings \
 && /opt/venv/bin/python -m pip uninstall -y pip setuptools
WORKDIR /app
COPY --chown=10001:10001 app/qwen_auth_verifier.py /app/app/qwen_auth_verifier.py
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8095
CMD ["uvicorn", "app.qwen_auth_verifier:create_app", "--factory", "--host", "0.0.0.0", "--port", "8095", "--no-server-header", "--no-date-header"]
