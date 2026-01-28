FROM python:3.11-slim

WORKDIR /app

# Install mDNS discovery dependency
RUN pip install --no-cache-dir zeroconf

# Copy metadata service
COPY metadata-service.py /app/

# Create public directory
RUN mkdir -p /app/public

# Make script executable
RUN chmod +x /app/metadata-service.py

# Run the service
CMD ["python3", "/app/metadata-service.py"]
