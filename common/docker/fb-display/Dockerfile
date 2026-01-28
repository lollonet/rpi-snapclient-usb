FROM python:3.11-slim

WORKDIR /app

# Install font for text rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir Pillow websockets requests numpy

# Copy renderer
COPY fb_display.py /app/

RUN chmod +x /app/fb_display.py

CMD ["python3", "/app/fb_display.py"]
