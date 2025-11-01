#!/bin/bash
# Run this script when containers are running to add channel_title column
# Usage: ./migrate_channel_title.sh

echo "Adding channel_title column to sources table..."

docker exec telegram_scraper_db psql -U user -d app -c "ALTER TABLE sources ADD COLUMN IF NOT EXISTS channel_title VARCHAR;"

echo "Verifying column was added..."
docker exec telegram_scraper_db psql -U user -d app -c "\d sources"

echo "Migration complete!"
