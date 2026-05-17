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

# Set up entry point for loader execution
# Usage: docker run IMAGE loaders.load_stock_symbols or similar
ENTRYPOINT ["python", "-m"]
CMD ["loaders.load_stock_symbols"]
