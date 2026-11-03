FROM python:3.11-slim

WORKDIR /app

# Disable Python output buffering for real-time container logs
ENV PYTHONUNBUFFERED=1

# Install procps so pkill and kill commands are available for hot-reloading
RUN apt-get update && apt-get install -y --no-install-recommends procps openssh-client git && rm -rf /var/lib/apt/lists/*

# Configure Git safe directory and system identity for containerized repository workflows
RUN git config --global --add safe.directory "*" && \
    git config --global user.name "AI Project Mentor" && \
    git config --global user.email "mentor@local"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /app/data

CMD ["python", "src/main.py"]
