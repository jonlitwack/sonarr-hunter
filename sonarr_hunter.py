import eventlet
eventlet.monkey_patch()

import os
import sys
import time
import schedule
import logging
import signal
import json
from flask import Flask, render_template_string, request, redirect, send_from_directory
from flask_socketio import SocketIO, emit
from threading import Thread, Lock
from datetime import datetime
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)
app.debug = True  # Enable debug mode
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*', logger=True, engineio_logger=True)
status = {
    'last_check': None,
    'missing_count': 0,
    'recent_logs': [],
    'connection_status': 'Unknown'
}
status_lock = Lock()

def load_settings():
    try:
        with open('settings.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Create default settings
        settings = {
            'sonarr_url': os.environ.get('SONARR_URL', 'http://sonarr:8989'),
            'api_key': os.environ.get('SONARR_API_KEY', '')
        }
        save_settings(settings)
        return settings

def save_settings(settings):
    with open('settings.json', 'w') as f:
        json.dump(settings, f, indent=2)

class GracefulKiller:
    kill_now = False
    
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
    
    def exit_gracefully(self, *args):
        self.kill_now = True

class SonarrHunter:
    def __init__(self):
        settings = load_settings()
        self.sonarr_url = settings['sonarr_url'].rstrip('/')  # Remove trailing slash if present
        self.api_key = settings['api_key']
        self.search_interval = int(os.environ.get('SEARCH_INTERVAL', 60))
        self.test_connection()

    def reload_settings(self):
        settings = load_settings()
        self.sonarr_url = settings['sonarr_url'].rstrip('/')
        self.api_key = settings['api_key']
        self.test_connection()

    def test_connection(self):
        """Test connection to Sonarr and update status accordingly"""
        if not self.api_key:
            self.update_status("No API key configured", connection_status="Not Configured")
            return False

        try:
            headers = {'X-Api-Key': self.api_key}
            response = requests.get(f"{self.sonarr_url}/api/v3/system/status", 
                                 headers=headers, 
                                 timeout=10)
            
            logger.info(f"Connection test response: {response.status_code}")
            if response.status_code == 200:
                self.update_status("Successfully connected to Sonarr", connection_status="Connected")
                return True
            elif response.status_code == 401:
                self.update_status("Invalid API key", connection_status="Invalid API Key")
                return False
            else:
                self.update_status(f"Unexpected response from Sonarr: {response.status_code}", 
                                 connection_status="Error")
                return False

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error details: {str(e)}")
            self.update_status("Failed to connect to Sonarr - Connection refused", 
                             connection_status="Connection Failed")
            return False
        except requests.exceptions.Timeout:
            self.update_status("Connection to Sonarr timed out", 
                             connection_status="Timeout")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during connection test: {str(e)}")
            self.update_status(f"Error connecting to Sonarr: {str(e)}", 
                             connection_status="Error")
            return False

    def update_status(self, message, count=None, connection_status=None):
        with status_lock:
            status['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if count is not None:
                status['missing_count'] = count
            if connection_status is not None:
                status['connection_status'] = connection_status
            status['recent_logs'].insert(0, f"{datetime.now().strftime('%H:%M:%S')} - {message}")
            status['recent_logs'] = status['recent_logs'][:100]  # Keep last 100 logs
            
            # Emit status update via websocket
            socketio.emit('status_update', {
                'last_check': status['last_check'],
                'missing_count': status['missing_count'],
                'connection_status': status['connection_status'],
                'log': status['recent_logs'][0]
            })

    def get_missing_episodes(self):
        if not self.test_connection():
            return []
            
        try:
            headers = {'X-Api-Key': self.api_key}
            url = f"{self.sonarr_url}/api/v3/wanted/missing"
            params = {
                'pageSize': 100,
                'includeImages': False,
                'includeSeries': True  # Explicitly request series information
            }
            
            logger.info(f"Making request to: {url}")
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Missing episodes response keys: {data.keys()}")
            
            if not isinstance(data, dict):
                logger.error(f"Unexpected response type: {type(data)}")
                return []
                
            records = data.get('records', [])
            if not isinstance(records, list):
                logger.error(f"Records is not a list: {type(records)}")
                return []
            
            # Debug: Print first record structure
            if records:
                first_record = records[0]
                logger.info("First record structure:")
                logger.info(f"- Series info: {json.dumps(first_record.get('series', {}), indent=2)}")
                logger.info(f"- Episode info: {json.dumps({k:v for k,v in first_record.items() if k != 'series'}, indent=2)}")
                
            return records
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting missing episodes: {str(e)}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting missing episodes: {str(e)}")
            return []

    def trigger_search(self, episode):
        try:
            if not isinstance(episode, dict):
                logger.error(f"Invalid episode data type: {type(episode)}")
                return
                
            series_id = episode.get('seriesId')
            if not series_id:
                logger.error(f"Missing seriesId in episode data: {episode}")
                return
                
            headers = {'X-Api-Key': self.api_key}
            data = {
                'name': 'SeriesSearch',
                'seriesId': series_id
            }
            
            # Debug: Print full episode structure
            logger.info("Episode structure for search:")
            logger.info(f"- Series info: {json.dumps(episode.get('series', {}), indent=2)}")
            logger.info(f"- Episode info: {json.dumps({k:v for k,v in episode.items() if k != 'series'}, indent=2)}")
            
            response = requests.post(f"{self.sonarr_url}/api/v3/command", headers=headers, json=data)
            response.raise_for_status()
            
            # Get series info from episode data
            series_info = episode.get('series', {})
            series_title = series_info.get('title', 'Unknown Series')
            
            season = episode.get('seasonNumber', 0)
            ep = episode.get('episodeNumber', 0)
            episode_title = episode.get('title', '')
            
            log_message = f"Triggered search for {series_title} S{season:02d}E{ep:02d}"
            if episode_title:
                log_message += f" - {episode_title}"
                
            logger.info(log_message)
            self.update_status(log_message)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error triggering search: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error triggering search: {str(e)}")

    def run_check(self) -> None:
        if not self.test_connection():
            return
            
        try:
            missing = self.get_missing_episodes()
            if not missing:
                self.update_status("No missing episodes found", 0)
                return

            self.update_status(f"Found {len(missing)} missing episodes", len(missing))
            for episode in missing:
                self.trigger_search(episode)
                time.sleep(2)  # Add delay between searches
        except Exception as e:
            logger.error(f"Error during check: {str(e)}")
            self.update_status(f"Error during check: {str(e)}")

# Global hunter instance
hunter = None

@socketio.on('connect')
def handle_connect():
    logger.info("Client connected")
    emit('status_update', {
        'last_check': status['last_check'],
        'missing_count': status['missing_count'],
        'connection_status': status['connection_status'],
        'log': status['recent_logs'][0] if status['recent_logs'] else "No logs yet"
    })

@app.route('/', methods=['GET'])
def home():
    settings = load_settings()
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sonarr Hunter</title>
        <style>
            body { font-family: Arial; margin: 20px; max-width: 800px; margin: 0 auto; padding: 20px; }
            .status { margin: 20px 0; }
            .logs { background: #f0f0f0; padding: 10px; border-radius: 4px; max-height: 400px; overflow-y: auto; }
            .log-entry { margin: 5px 0; }
            .settings { background: #fff; padding: 20px; border: 1px solid #ddd; border-radius: 4px; margin: 20px 0; }
            .settings input[type="text"] { width: 100%; padding: 8px; margin: 8px 0; box-sizing: border-box; }
            .settings input[type="submit"] { background: #4CAF50; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            .settings input[type="submit"]:hover { background: #45a049; }
            .section { margin-bottom: 30px; }
            h1, h2 { color: #333; }
            .field { margin-bottom: 15px; }
            .field label { display: block; margin-bottom: 5px; font-weight: bold; }
            .field small { display: block; color: #666; margin-top: 2px; }
            .new-log { animation: highlight 2s ease-out; }
            @keyframes highlight {
                0% { background-color: #ffeb3b; }
                100% { background-color: transparent; }
            }
            #connection-status { font-weight: bold; }
            #connection-status.Connected { color: #4CAF50; }
            #connection-status.Error,
            #connection-status.Disconnected,
            #connection-status.Invalid { color: #f44336; }
            #connection-status.Unknown { color: #ff9800; }
        </style>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                const socket = io();
                const logsDiv = document.getElementById('logs');
                const lastCheckSpan = document.getElementById('last-check');
                const missingCountSpan = document.getElementById('missing-count');
                const connectionStatus = document.getElementById('connection-status');

                socket.on('connect', function() {
                    console.log('Connected to server');
                });

                socket.on('disconnect', function() {
                    console.log('Disconnected from server');
                });

                socket.on('status_update', function(data) {
                    console.log('Received status update:', data);
                    lastCheckSpan.textContent = data.last_check || 'Never';
                    missingCountSpan.textContent = data.missing_count;
                    
                    if (data.connection_status) {
                        connectionStatus.textContent = data.connection_status;
                        connectionStatus.className = data.connection_status;
                    }
                    
                    if (data.log) {
                        const logEntry = document.createElement('div');
                        logEntry.className = 'log-entry new-log';
                        logEntry.textContent = data.log;
                        
                        logsDiv.insertBefore(logEntry, logsDiv.firstChild);
                        
                        // Keep only last 100 entries
                        while (logsDiv.children.length > 100) {
                            logsDiv.removeChild(logsDiv.lastChild);
                        }
                    }
                });
            });
        </script>
    </head>
    <body>
        <h1>Sonarr Hunter</h1>
        <p>Connection Status: <span id="connection-status" class="{{ status['connection_status'] }}">{{ status['connection_status'] }}</span></p>
        
        <div class="section settings">
            <h2>Settings</h2>
            <form action="/settings" method="POST">
                <div class="field">
                    <label for="sonarr_url">Sonarr URL:</label>
                    <input type="text" id="sonarr_url" name="sonarr_url" value="{{ settings['sonarr_url'] }}">
                    <small>The URL to your Sonarr instance (e.g., http://sonarr:8989)</small>
                </div>
                <div class="field">
                    <label for="api_key">API Key:</label>
                    <input type="text" id="api_key" name="api_key" value="{{ settings['api_key'] }}">
                    <small>Your Sonarr API key (found in Settings > General)</small>
                </div>
                <input type="submit" value="Save Settings">
            </form>
        </div>

        <div class="section status">
            <h2>Status</h2>
            <p>Last Check: <span id="last-check">{{ status['last_check'] or 'Never' }}</span></p>
            <p>Missing Episodes: <span id="missing-count">{{ status['missing_count'] }}</span></p>
        </div>

        <div class="section">
            <h2>Recent Logs</h2>
            <div id="logs" class="logs">
                {% for log in status['recent_logs'] %}
                <div class="log-entry">{{ log }}</div>
                {% endfor %}
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(template, status=status, settings=settings)

@app.route('/settings', methods=['POST'])
def update_settings():
    settings = {
        'sonarr_url': request.form['sonarr_url'].strip(),
        'api_key': request.form['api_key'].strip()
    }
    save_settings(settings)
    if hunter:
        hunter.reload_settings()
    return redirect('/')

def run_flask():
    socketio.run(app, host='0.0.0.0', port=3000, debug=True, use_reloader=False)

def main():
    try:
        global hunter
        killer = GracefulKiller()
        hunter = SonarrHunter()
        logger.info(f"Sonarr Hunter started. Running every {hunter.search_interval} minutes")
        
        # Run initial check
        hunter.run_check()
        
        # Schedule periodic checks
        schedule.every(hunter.search_interval).minutes.do(hunter.run_check)
        
        # Start Flask with SocketIO
        run_flask()
            
        logger.info("Shutting down Sonarr Hunter...")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
