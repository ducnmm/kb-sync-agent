# Use official lightweight Python runtime
FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr and writing pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Entrypoint: runs synchronization once, outputs logs, and exits code 0
ENTRYPOINT ["python", "main.py"]
