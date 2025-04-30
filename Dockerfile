# Dockerfile

# 1) Base image with Python 3.9
FROM python:3.9-slim

# 2) Set working dir
WORKDIR /app

# 3) Copy & install dependencies
COPY requirements-loadfinancialdata.txt .
RUN pip install --no-cache-dir -r requirements-loadfinancialdata.txt

# 4) Copy the loader script
COPY loadfinancialdata.py .

# 5) Default command
CMD ["python", "loadfinancialdata.py"]
