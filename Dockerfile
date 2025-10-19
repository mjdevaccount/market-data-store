# Production-ready Dockerfile for market-data-store
# Compatible with market_data_infra centralized compose setup

FROM python:3.11-slim

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml README.md ./

# Install Python dependencies as root (for system packages)
RUN pip install --no-cache-dir -U pip wheel && \
    pip install --no-cache-dir -e .

# Copy application code
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# Change ownership to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose service port (8082 per infra hub spec)
ENV PORT=8082
EXPOSE 8082

# Health check
HEALTHCHECK --interval=10s --timeout=3s --retries=3 --start-period=20s \
  CMD curl -fsS http://localhost:8082/health || exit 1

# Start service with uvicorn
CMD ["uvicorn", "datastore.service.app:app", "--host", "0.0.0.0", "--port", "8082"]
