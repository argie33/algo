# Test environment for stock data loading scripts
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Set up PostgreSQL local for testing
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql \
    postgresql-contrib \
    && rm -rf /var/lib/apt/lists/*

# Create a directory for the scripts
RUN mkdir -p /app/loadfundamentals

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DB_SECRET_ARN=test-db-secret

# Add startup script and test runner
COPY startup.sh /app/
COPY test-runner.sh /app/
RUN chmod +x /app/startup.sh
RUN chmod +x /app/test-runner.sh

# Add entry point
ENTRYPOINT ["/app/startup.sh"]
