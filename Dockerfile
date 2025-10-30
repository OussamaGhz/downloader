FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY .env ./
COPY startup.sh ./

# Make startup script executable
RUN chmod +x startup.sh

# Expose port
EXPOSE 8000

# Run the startup script
CMD ["./startup.sh"]
