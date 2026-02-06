# Telemetry API Service - Production Docker Image
FROM python:3.11-slim

LABEL maintainer="Telemetry API Service"
LABEL description="Single-writer telemetry collection service"
LABEL version="3.0.0"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY telemetry_service.py .
COPY src/ ./src/
COPY schema/ ./schema/

# Create data directory for database
RUN mkdir -p /data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV TELEMETRY_DB_PATH=/data/telemetry.sqlite
ENV TELEMETRY_LOCK_FILE=/data/telemetry.lock
ENV TELEMETRY_DB_JOURNAL_MODE=DELETE
ENV TELEMETRY_DB_SYNCHRONOUS=FULL
ENV TELEMETRY_DB_BUSY_TIMEOUT_MS=30000
ENV TELEMETRY_DB_CONNECT_TIMEOUT_SECONDS=30
ENV TELEMETRY_DB_MAX_RETRIES=3
ENV TELEMETRY_DB_RETRY_BASE_DELAY_SECONDS=0.1
ENV TELEMETRY_API_HOST=0.0.0.0
ENV TELEMETRY_API_PORT=8765
ENV TELEMETRY_API_WORKERS=1
ENV TELEMETRY_LOG_LEVEL=INFO

# Expose API port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

# Run as non-root user for security
RUN useradd -m -u 1000 telemetry && \
    chown -R telemetry:telemetry /app /data
USER telemetry

# Start service
CMD ["uvicorn", "telemetry_service:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1", "--log-level", "info"]
