#!/bin/bash
set -e

# Verify required environment variables
required_vars=("SONARR_URL" "SONARR_API_KEY")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Error: Required environment variable $var is not set"
        exit 1
    fi
done

# Set timezone if provided
if [ ! -z "$TZ" ]; then
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime
    echo $TZ > /etc/timezone
fi

# Start the Python script
echo "Starting Sonarr Hunter..."
exec python3 /app/sonarr_hunter.py
