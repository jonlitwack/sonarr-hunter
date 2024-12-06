#!/usr/bin/env python3

import os
import sys
import time
import logging
import schedule
import requests
from datetime import datetime
from typing import List, Dict, Any
import signal

class GracefulKiller:
    kill_now = False
    
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
    
    def exit_gracefully(self, *args):
        logger.info("Shutdown signal received, exiting gracefully...")
        self.kill_now = True

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class SonarrHunter:
    def __init__(self):
        # Get environment variables with validation
        self.sonarr_url = self._get_required_env('SONARR_URL').rstrip('/')
        self.api_key = self._get_required_env('SONARR_API_KEY')
        self.search_interval = int(os.getenv('SEARCH_INTERVAL', '60'))  # Default to 60 minutes
        
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Accept': 'application/json'
        })

    def _get_required_env(self, var_name: str) -> str:
        """Get required environment variable or exit if not found."""
        value = os.getenv(var_name)
        if not value:
            logger.error(f"Required environment variable {var_name} is not set")
            sys.exit(1)
        return value

    def _make_request(self, endpoint: str, method: str = 'GET', data: Dict = None) -> Any:
        """Make an API request with error handling."""
        url = f"{self.sonarr_url}/api/v3/{endpoint}"
        try:
            if method == 'GET':
                response = self.session.get(url, timeout=30)
            elif method == 'POST':
                response = self.session.post(url, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            return None

    def get_missing_episodes(self) -> List[Dict]:
        """Get list of missing episodes from Sonarr."""
        logger.info("Checking for missing episodes...")
        
        try:
            # Get all series
            series = self._make_request('series')
            if not series:
                return []

            missing_episodes = []
            for show in series:
                # Get episodes for each series
                episodes = self._make_request(f'episode?seriesId={show["id"]}')
                if not episodes:
                    continue

                # Filter for missing episodes
                show_missing = [
                    {
                        'episodeId': ep['id'],
                        'seriesTitle': show['title'],
                        'episodeTitle': ep['title'],
                        'seasonNumber': ep['seasonNumber'],
                        'episodeNumber': ep['episodeNumber']
                    }
                    for ep in episodes
                    if ep['monitored'] and not ep.get('hasFile', False)
                ]
                missing_episodes.extend(show_missing)

            return missing_episodes
        except Exception as e:
            logger.error(f"Error getting missing episodes: {str(e)}")
            return []

    def trigger_search(self, episode: Dict) -> None:
        """Trigger a search for a specific episode."""
        try:
            logger.info(
                f"Triggering search for {episode['seriesTitle']} - "
                f"S{episode['seasonNumber']:02d}E{episode['episodeNumber']:02d} - "
                f"{episode['episodeTitle']}"
            )
            
            data = {
                'name': 'EpisodeSearch',
                'episodeIds': [episode['episodeId']]
            }
            
            result = self._make_request('command', method='POST', data=data)
            if result:
                logger.info("Search command sent successfully")
            else:
                logger.error("Failed to send search command")
        except Exception as e:
            logger.error(f"Error triggering search: {str(e)}")

    def run_check(self) -> None:
        """Main function to check for and search missing episodes."""
        try:
            missing = self.get_missing_episodes()
            if not missing:
                logger.info("No missing episodes found")
                return

            logger.info(f"Found {len(missing)} missing episodes")
            for episode in missing:
                self.trigger_search(episode)
                time.sleep(2)  # Small delay between searches to avoid overwhelming the API
        except Exception as e:
            logger.error(f"Error in main run_check: {str(e)}")

def main():
    try:
        killer = GracefulKiller()
        hunter = SonarrHunter()
        logger.info(f"Sonarr Hunter started. Running every {hunter.search_interval} minutes")
        
        # Run initial check
        hunter.run_check()
        
        # Schedule periodic checks
        schedule.every(hunter.search_interval).minutes.do(hunter.run_check)
        
        # Keep the script running until shutdown signal
        while not killer.kill_now:
            schedule.run_pending()
            time.sleep(1)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
