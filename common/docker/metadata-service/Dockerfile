FROM python:3.13-slim

WORKDIR /app

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies: mDNS discovery + WebSocket server
RUN uv pip install --system --no-cache zeroconf websockets

# Copy metadata service
COPY metadata-service.py /app/

# Create public directory
RUN mkdir -p /app/public

# Make script executable
RUN chmod +x /app/metadata-service.py

# Run the service
CMD ["python3", "/app/metadata-service.py"]
