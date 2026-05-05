# Unified Stock Analytics Data Loaders
# Includes all 54+ refactored loaders with DatabaseHelper for optimal AWS performance

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ALL Python sources at the repo root. Loaders share several utility
# modules (optimal_loader.py, db_helper.py, signal_utils.py, data_source_router.py,
# bloom_dedup.py, _patch_dotenv.py, etc.) that are not covered by a single glob.
# A single COPY of *.py keeps the image consistent without per-module COPY drift.
COPY *.py ./

# Copy configuration files (optional .env.local for dev)
COPY .env.local* ./

# Set environment variables (can be overridden at runtime)
ENV PYTHONUNBUFFERED=1
ENV AWS_REGION=us-east-1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "from db_helper import DatabaseHelper; print('OK')" || exit 1

# Smart entrypoint:
#   1. If LOADER_FILE env var is set, exec it (preferred path; ECS task defs set it).
#   2. Else if a positional arg is supplied (docker run image foo.py), exec that.
#   3. Else error helpfully — no silent default to loadpricedaily.py masking misconfig.
COPY entrypoint.sh /usr/local/bin/loader-entrypoint
RUN chmod +x /usr/local/bin/loader-entrypoint
ENTRYPOINT ["/usr/local/bin/loader-entrypoint"]
