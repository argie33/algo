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
COPY entrypoint.sh ./
COPY run-all-loaders.py ./

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Run as non-root user to limit container blast radius
RUN useradd -r -u 1001 -g root appuser && chown -R appuser:root /app
USER appuser

# Set up entry point for ECS loader execution
# ECS passes LOADER_FILE env var to specify which loader to run
ENTRYPOINT ["./entrypoint.sh"]
