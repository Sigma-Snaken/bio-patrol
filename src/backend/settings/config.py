import os
import sys


def get_env_file_path():
    """Get the path to .env.local file, using AppData to avoid startup folder issues."""
    if getattr(sys, 'frozen', False):
        appdata = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        config_dir = os.path.join(appdata, 'BioPatrol')
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, '.env.local')

        if not os.path.exists(config_path):
            with open(config_path, 'w') as f:
                f.write('# Bio Patrol Configuration\nPORT=8000\nMQTT_ENABLED=false\n')

        return config_path
    else:
        return '.env.local'


def get_settings_dir():
    """Get the path to the data/config directory (JSON configs).
    From src/backend/settings/config.py → up 4 levels to project root."""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(base_path, "data", "config")


# --- JSON config file paths ---
SETTINGS_FILE = os.path.join(get_settings_dir(), "settings.json")
BEDS_FILE = os.path.join(get_settings_dir(), "beds.json")
PATROL_FILE = os.path.join(get_settings_dir(), "patrol.json")
SCHEDULE_FILE = os.path.join(get_settings_dir(), "schedule.json")


def get_runtime_settings() -> dict:
    """Load runtime settings merged with defaults. Called per-request for fresh values."""
    from settings.defaults import DEFAULT_SETTINGS
    from utils.json_io import load_json
    saved = load_json(SETTINGS_FILE, {})
    merged = {**DEFAULT_SETTINGS, **saved}
    return merged


def get_port() -> int:
    """Get the server port from environment or default."""
    return int(os.environ.get("PORT", "8000"))
