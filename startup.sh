#!/bin/bash
set -e

echo "Starting Telegram Scraper Backend..."

# Wait for Prefect Orion to be ready
echo "Waiting for Prefect Orion to be ready..."
for i in {1..30}; do
    if curl -f http://orion:4200/api/health > /dev/null 2>&1; then
        echo "✓ Prefect Orion is ready"
        break
    fi
    echo "  Waiting for Prefect Orion... (attempt $i/30)"
    sleep 2
done

# Verify Prefect connection
echo "Verifying Prefect connection..."
cd /app
python -m app.register_flow || echo "Warning: Could not verify Prefect connection"

echo "✓ Prefect verification complete"

# Start the FastAPI application
echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
