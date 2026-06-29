FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y \
    postgresql-client \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    libgbm1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libglib2.0-0 \
    libcairo2 \
    libasound2 \
    libexpat1 \
    libfontconfig1 \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium

COPY loaders/ ./loaders/
COPY utils/ ./utils/
COPY config/ ./config/
COPY monitoring/ ./monitoring/
COPY algo/ ./algo/
COPY migrations/ ./migrations/

RUN useradd -r -u 1001 -g root appuser && chown -R appuser:root /app
USER appuser

ENTRYPOINT ["python3", "-u"]
