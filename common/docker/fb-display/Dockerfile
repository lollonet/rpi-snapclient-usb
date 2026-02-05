FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install font for text rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN uv pip install --system --no-cache Pillow websockets requests numpy

# Copy renderer and assets
COPY fb_display.py /app/
COPY logo.png /app/

RUN chmod +x /app/fb_display.py

CMD ["python3", "/app/fb_display.py"]
