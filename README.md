# Sonarr Hunter

Automatically searches for missing episodes in your Sonarr library.

## Features
- Automatically scans your Sonarr library for missing episodes
- Triggers searches for any missing episodes it finds
- Configurable search interval
- Clean logging and error handling
- Proper timezone support
- Easy integration with CasaOS and Sonarr

## Installation
1. Open your CasaOS dashboard
2. Navigate to the App Store
3. Search for "Sonarr Hunter"
4. Click Install

## Configuration
1. Get your Sonarr API key:
   - Open Sonarr
   - Go to Settings > General
   - Copy your API key
2. Configure Sonarr Hunter in CasaOS:
   - SONARR_API_KEY: Paste your Sonarr API key
   - SONARR_URL: URL to your Sonarr instance (if using CasaOS, usually `http://sonarr:8989`)
   - SEARCH_INTERVAL: How often to check for missing episodes (in minutes)
   - TZ: Your timezone (e.g., America/New_York)

## Usage
Once configured, Sonarr Hunter will automatically:
1. Scan your Sonarr library at the specified interval
2. Identify any missing episodes
3. Trigger searches for those episodes in Sonarr

You can monitor its activity through:
- CasaOS dashboard
- Container logs in CasaOS
- Direct access at `http://your-casaos-ip:3000`

## Troubleshooting
1. Verify your Sonarr URL is correct and accessible
2. Check that your API key is entered correctly
3. View the logs in CasaOS for any error messages
4. Ensure Sonarr is running and accessible

## Support
If you encounter any issues:
1. Check the logs in CasaOS
2. Visit our GitHub repository for known issues
3. Open a new issue if you need additional help

## License
MIT License
