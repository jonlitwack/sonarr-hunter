# Sonarr Hunter

Automatically searches for missing episodes in your Sonarr library.

## Features
- Automatically scans your Sonarr library for missing episodes
- Triggers searches for any missing episodes it finds
- Configurable search interval
- Clean logging and error handling
- Proper timezone support

## Configuration
1. Get your Sonarr API key from Settings > General
2. Install the app through CasaOS
3. Configure:
   - SONARR_API_KEY: Your Sonarr API key
   - SONARR_URL: URL to your Sonarr instance (default usually works if using CasaOS)
   - SEARCH_INTERVAL: How often to check (in minutes)
   - TZ: Your timezone

## Logs
View logs through the CasaOS interface or using:
```bash
docker logs sonarr-hunter
```

## Support
If you encounter any issues, please open an issue on GitHub.