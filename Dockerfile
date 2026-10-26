FROM python:3.11-slim

WORKDIR /app

# Disable Python output buffering for real-time container logs
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /app/data

CMD ["python", "src/main.py"]
