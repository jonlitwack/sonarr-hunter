FROM python:3.9-slim

# Install tzdata for timezone support
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY sonarr_hunter.py .
COPY entrypoint.sh .

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Default environment variables
ENV SONARR_URL=http://sonarr:8989 \
    SONARR_API_KEY=your_api_key_here \
    SEARCH_INTERVAL=60 \
    TZ=UTC \
    PYTHONUNBUFFERED=1

# Entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]