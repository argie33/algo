FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the source code
COPY . .

# Set environment variables
ENV PYTHONIOENCODING=utf8
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Default command
CMD ["python", "run_script.py", "loadtechnicalsdaily.py"]
