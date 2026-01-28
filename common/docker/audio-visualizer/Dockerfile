FROM python:3.11-slim

WORKDIR /app

# Install numpy for FFT and websockets for broadcasting
RUN pip install --no-cache-dir numpy websockets

# Copy visualizer script
COPY visualizer.py /app/

RUN chmod +x /app/visualizer.py

CMD ["python3", "/app/visualizer.py"]
