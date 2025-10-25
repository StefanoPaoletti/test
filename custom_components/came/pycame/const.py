"""Python client for CAME ETI/Domo - Constants.
Versione ottimizzata da Stefano Paoletti
Based on original work by Danny Mauro (Den901)
For more details: https://github.com/StefanoPaoletti/Came_Connect
"""
import json
from pathlib import Path

# Debug flag - set to True for deep debugging (verbose logs)
DEBUG_DEEP = False

# Issue tracker URL
ISSUE_URL = "https://github.com/StefanoPaoletti/ha_came_personale/issues"


# Read version ONCE at module import (before event loop starts)
def _load_version() -> str:
    """Load version from manifest.json at module import time."""
    try:
        # Go up two directories: pycame -> came -> manifest.json
        manifest_path = Path(__file__).parent.parent / "manifest.json"
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
CAME ETI/Domo API Python Client - Optimized Version
Version: {VERSION}
Based on original work by Den901
For issues or suggestions:
{ISSUE_URL}
-------------------------------------------------------------------
"""
