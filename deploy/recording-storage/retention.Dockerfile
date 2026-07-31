FROM python:3.12.11-slim@sha256:47ae396f09c1303b8653019811a8498470603d7ffefc29cb07c88f1f8cb3d19f

RUN useradd --system --uid 10421 --no-create-home recording-retention
WORKDIR /app
COPY app/core/recording_retention.py /app/recording_retention.py
USER 10421:10421
ENTRYPOINT ["python", "/app/recording_retention.py"]
