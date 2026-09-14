FROM python:3.11-slim

WORKDIR /app

# Install system packages
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend app
COPY backend/ ./backend/

WORKDIR /app/backend

# Railway injects $PORT dynamically
ENV PORT=8000
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
