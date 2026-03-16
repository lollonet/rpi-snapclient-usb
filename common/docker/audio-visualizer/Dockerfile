FROM python:3.13-slim

WORKDIR /app

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:0.6.3 /uv /usr/local/bin/uv

# ALSA library for loopback capture
RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

RUN uv pip install --system --no-cache numpy websockets

RUN groupadd -r -g 1000 app && useradd -r -u 1000 -g app -d /app -s /sbin/nologin app

COPY --chown=1000:1000 visualizer.py /app/
RUN chmod +x /app/visualizer.py

USER app

CMD ["python3", "/app/visualizer.py"]
