FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir numpy websockets

COPY visualizer.py /app/
RUN chmod +x /app/visualizer.py

CMD ["python3", "/app/visualizer.py"]
