"""
CLI state persistence for Jirassic Pack CLI.
"""
import os
import json
import types
from jirassicpack.utils.message_utils import error
from jirassicpack.utils.logging import contextual_log

STATE_FILE = os.path.join(os.getcwd(), ".jirassicpack_cli_state.json")
RECENT_FEATURES = []
LAST_FEATURE = None
LAST_REPORT_PATH = None
FAVORITE_FEATURES = []
CLI_THEME = "default"
CLI_LOG_LEVEL = os.environ.get("JIRASSICPACK_LOG_LEVEL", "INFO")

def make_json_safe(obj):
    """
    Recursively convert objects to JSON-serializable forms.
    """
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [make_json_safe(x) for x in obj]
    if hasattr(obj, "__dict__"):
        return make_json_safe(vars(obj))
    return str(obj)

def load_cli_state():
    """
    Loads CLI state from STATE_FILE, updating global variables.
    Handles errors gracefully and auto-recovers from malformed files.
    """
    global RECENT_FEATURES, LAST_FEATURE, LAST_REPORT_PATH, FAVORITE_FEATURES, CLI_THEME, CLI_LOG_LEVEL
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        RECENT_FEATURES = state.get("RECENT_FEATURES", [])
        LAST_FEATURE = state.get("LAST_FEATURE", None)
        LAST_REPORT_PATH = state.get("LAST_REPORT_PATH", None)
        FAVORITE_FEATURES = state.get("FAVORITE_FEATURES", [])
        CLI_THEME = state.get("CLI_THEME", "default")
        CLI_LOG_LEVEL = state.get("CLI_LOG_LEVEL", os.environ.get("JIRASSICPACK_LOG_LEVEL", "INFO"))
    except Exception as e:
        error(f"Failed to load CLI state: {e}")
        contextual_log('error', f"Failed to load CLI state: {e}", exc_info=True)
        # Attempt auto-recovery by renaming the bad file
        try:
            os.rename(STATE_FILE, STATE_FILE + ".bak")
            error(f"Corrupt CLI state file renamed to {STATE_FILE}.bak. State will be reset.")
        except Exception as e2:
            error(f"Failed to rename corrupt state file: {e2}")

def save_cli_state():
    """
    Saves current CLI state to STATE_FILE.
    Handles errors gracefully.
    """
    try:
        state = {
            "RECENT_FEATURES": make_json_safe(RECENT_FEATURES),
            "LAST_FEATURE": make_json_safe(LAST_FEATURE),
            "LAST_REPORT_PATH": make_json_safe(LAST_REPORT_PATH),
            "FAVORITE_FEATURES": make_json_safe(FAVORITE_FEATURES),
            "CLI_THEME": CLI_THEME,
            "CLI_LOG_LEVEL": CLI_LOG_LEVEL,
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        error(f"Failed to save CLI state: {e}")
        contextual_log('error', f"Failed to save CLI state: {e}", exc_info=True) 