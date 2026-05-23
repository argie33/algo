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
COPY run-all-loaders.py ./

# Run as non-root user to limit container blast radius
RUN useradd -r -u 1001 -g root appuser && chown -R appuser:root /app
USER appuser

# Dispatcher reads LOADER_NAME env var from Terraform and runs correct loader
# Loaders read from environment: LOADER_NAME, LOADER_INTERVALS, LOADER_ASSET_CLASSES, LOADER_PARALLELISM
CMD ["python3", "-u", "-m", "loaders"]
