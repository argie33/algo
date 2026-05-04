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

# Copy database helper (critical)
COPY db_helper.py .

# Copy all refactored loaders
COPY load*.py ./
COPY loader*.py ./

# Copy algo engine (the trading brain — used by algo orchestrator task)
COPY algo_*.py ./

# Copy utility modules
COPY load_state.py ./
COPY loader_safety.py ./
COPY signal_utils.py ./

# Copy configuration files
COPY .env.local* ./
COPY LOADER_BEST_PRACTICES.md ./
COPY AWS_BEST_PRACTICES.md ./

# Set environment variables (can be overridden at runtime)
ENV PYTHONUNBUFFERED=1
ENV AWS_REGION=us-east-1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "from db_helper import DatabaseHelper; print('OK')" || exit 1

# Default entrypoint - runs a loader specified as first argument
# Usage: docker run stocks-loaders:latest loadpricedaily.py
ENTRYPOINT ["python3"]
CMD ["loadpricedaily.py"]
