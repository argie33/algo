FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY loaders/ ./loaders/
COPY utils/ ./utils/
COPY config/ ./config/
COPY monitoring/ ./monitoring/
COPY algo/ ./algo/
COPY migrations/ ./migrations/

RUN useradd -r -u 1001 -g root appuser && chown -R appuser:root /app
USER appuser
