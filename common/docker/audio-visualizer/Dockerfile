FROM python:3.13-slim

WORKDIR /app

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ALSA library for loopback capture
RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

RUN uv pip install --system --no-cache numpy websockets

COPY visualizer.py /app/
RUN chmod +x /app/visualizer.py

CMD ["python3", "/app/visualizer.py"]
