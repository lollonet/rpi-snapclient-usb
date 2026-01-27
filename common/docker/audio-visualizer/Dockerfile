FROM debian:bookworm-slim

# Install CAVA and Python dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    cava \
    python3 \
    python3-pip \
    python3-websockets \
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy visualizer script
COPY visualizer.py /app/
COPY cava-config /app/

RUN chmod +x /app/visualizer.py

CMD ["python3", "/app/visualizer.py"]
