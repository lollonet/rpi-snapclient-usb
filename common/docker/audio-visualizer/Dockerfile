FROM python:3.11-slim

WORKDIR /app

# ALSA library for loopback capture
RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir numpy websockets

COPY visualizer.py /app/
RUN chmod +x /app/visualizer.py

CMD ["python3", "/app/visualizer.py"]
