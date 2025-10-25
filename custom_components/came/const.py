"""
The CAME Integration Component - Optimized Version
Versione ottimizzata da Stefano Paoletti
Basata sul lavoro originale di Danny Mauro (Den901)
For more details: https://github.com/StefanoPaoletti/Came_Connect
"""
import json
from pathlib import Path

# Base component constants
NAME = "CAME Connect sp"
DOMAIN = "came"
ATTRIBUTION = "Data provided by Came Connect"
ISSUE_URL = "https://github.com/StefanoPaoletti/Came_Connect/issues"
DATA_YAML = f"{DOMAIN}__yaml"


# Read version ONCE at module import (before event loop starts)
def _load_version() -> str:
    """Load version from manifest.json at module import time."""
    try:
        manifest_path = Path(__file__).parent / "manifest.json"
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        return manifest.get("version", "unknown")
    except Exception:
        return "unknown"


# Load version immediately at import (not in event loop)
VERSION = _load_version()

# Startup message with version already embedded
STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
Versione ottimizzata per impianto personale
Basata sul progetto originale di Den901
Per problemi o suggerimenti:
{ISSUE_URL}
-------------------------------------------------------------------
"""

# Icons
# Device classes
# Signals
SIGNAL_DISCOVERY_NEW = DOMAIN + "_discovery_{}"
SIGNAL_DELETE_ENTITY = DOMAIN + "_delete"
SIGNAL_UPDATE_ENTITY = DOMAIN + "_update"

# Services
SERVICE_PULL_DEVICES = "pull_devices"
SERVICE_FORCE_UPDATE = "force_update"

# Configuration and options
CONF_MANAGER = "manager"
CONF_CAME_LISTENER = "came_listener"
CONF_ENTRY_IS_SETUP = "entry_is_setup"
CONF_PENDING = "pending"

# Defaults
# Attributes
