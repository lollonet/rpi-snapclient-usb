FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install fonts and build dependencies for evdev
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    gcc \
    libc-dev \
    linux-libc-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN uv pip install --system --no-cache Pillow websockets requests numpy evdev

# Copy renderer and assets
COPY fb_display.py /app/
COPY logo.png /app/
COPY snapforge-text.png /app/

RUN chmod +x /app/fb_display.py

CMD ["python3", "/app/fb_display.py"]
