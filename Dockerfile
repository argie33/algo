FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for database connectivity
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY loaders/ ./loaders/
COPY utils/ ./utils/
COPY config/ ./config/
COPY algo/ ./algo/

# Create entrypoint script that executes whatever command ECS passes
RUN echo '#!/bin/sh\nexec "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh

# Run as non-root user to limit container blast radius
RUN useradd -r -u 1001 -g root appuser && chown -R appuser:root /app
USER appuser

# ENTRYPOINT executes the command array passed by ECS task definition
# Task definition command: ["python3", "-u", "loaders/load_income_statement.py"]
ENTRYPOINT ["/entrypoint.sh"]
