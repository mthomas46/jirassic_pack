# --- Ensure we are running from the project root and can import jirassicpack ---
import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
os.chdir(project_root)

import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
from jirassicpack.config import ConfigLoader
from jirassicpack.jira_client import JiraClient
from jirassicpack.utils.io import ensure_output_dir, spinner, error, info, prompt_text, prompt_select, prompt_password, prompt_checkbox, select_from_list, halt_cli
from jirassicpack.utils.logging import contextual_log, redact_sensitive
from jirassicpack.utils.jira import select_jira_user, select_account_id, select_property_key, search_issues, clear_all_caches, refresh_user_cache
from colorama import Fore, Style
from pythonjsonlogger import jsonlogger
import json
from dotenv import load_dotenv
import uuid
import socket
import re
from jirassicpack.log_monitoring import log_parser
from jirassicpack.features.ticket_discussion_summary import ticket_discussion_summary
from jirassicpack.features.test_local_llm import test_local_llm
from jirassicpack.features.deep_ticket_summary import deep_ticket_summary
import subprocess
import shutil
import requests
import threading
from jirassicpack.utils.rich_prompt import (
    rich_panel, rich_info, rich_error, rich_success,
    panel_objects_in_mirror, panel_clever_girl,
    panel_hold_onto_your_butts, panel_big_pile_of_errors, panel_nobody_cares,
    panel_combined_welcome
)
from mdutils.mdutils import MdUtils
from jirassicpack.features import FEATURE_MANIFEST
from jirassicpack.constants import ABORTED, FAILED_TO, WRITTEN_TO, NO_ISSUES_FOUND
import types

load_dotenv()

"""
Jirassic Pack CLI Logging:
- Structured JSON logging by default (plain text optional)
- Log rotation: 5MB per file, 5 backups
- Log level configurable via env/CLI (JIRASSICPACK_LOG_LEVEL, --log-level)
- Sensitive data (API tokens, passwords) always redacted
- All logs include context: feature, user, batch, suffix, function, operation_id
- All exceptions logged with tracebacks
"""

# Set up detailed logging with rotation and redaction
LOG_FILE = 'jirassicpack.log'
LOG_LEVEL = os.environ.get('JIRASSICPACK_LOG_LEVEL', 'INFO').upper()
LOG_FORMAT = os.environ.get('JIRASSICPACK_LOG_FORMAT', 'json').lower()
CLI_VERSION = "1.0.0"  # Update as needed
HOSTNAME = socket.gethostname()
PID = os.getpid()
ENV = os.environ.get('JIRASSICPACK_ENV', 'dev')

# Ensure log file exists and is writable
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'a'):
        os.utime(LOG_FILE, None)
handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5)

class JirassicJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter for structured CLI logging.
    Adds standard and contextual fields (feature, user, batch, etc.),
    ensures sensitive data is redacted, and supports log rotation.
    """
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        # Standard fields
        log_record['asctime'] = getattr(record, 'asctime', self.formatTime(record, self.datefmt))
        log_record['levelname'] = record.levelname
        log_record['name'] = record.name
        # Add/override context fields
        log_record['feature'] = message_dict.get('feature') or getattr(record, 'feature', None)
        log_record['user'] = message_dict.get('user') or getattr(record, 'user', None)
        log_record['batch'] = message_dict.get('batch', None) or getattr(record, 'batch', None)
        log_record['suffix'] = message_dict.get('suffix', None) or getattr(record, 'suffix', None)
        log_record['function'] = message_dict.get('function') or getattr(record, 'function', record.funcName)
        log_record['operation_id'] = message_dict.get('operation_id') or getattr(record, 'operation_id', str(uuid.uuid4()))
        log_record['operation'] = message_dict.get('operation') or getattr(record, 'operation', None)
        log_record['params'] = message_dict.get('params') or getattr(record, 'params', None)
        log_record['status'] = message_dict.get('status') or getattr(record, 'status', None)
        log_record['error_type'] = message_dict.get('error_type') or getattr(record, 'error_type', None)
        log_record['correlation_id'] = message_dict.get('correlation_id') or getattr(record, 'correlation_id', None)
        log_record['duration_ms'] = message_dict.get('duration_ms') or getattr(record, 'duration_ms', None)
        log_record['output_file'] = message_dict.get('output_file') or getattr(record, 'output_file', None)
        log_record['retry_count'] = message_dict.get('retry_count') or getattr(record, 'retry_count', None)
        log_record['env'] = ENV
        log_record['cli_version'] = CLI_VERSION
        log_record['hostname'] = HOSTNAME
        log_record['pid'] = PID
        # Remove duplicate feature if present
        if isinstance(log_record.get('feature'), list):
            log_record['feature'] = log_record['feature'][0]

if LOG_FORMAT == 'json':
    formatter = JirassicJsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(feature)s %(message)s %(user)s %(batch)s %(suffix)s %(function)s %(operation_id)s %(operation)s %(params)s %(status)s %(error_type)s %(correlation_id)s %(duration_ms)s %(output_file)s %(retry_count)s %(env)s %(cli_version)s %(hostname)s %(pid)s'
    )
else:
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logging.basicConfig(
    handlers=[handler],
    format=None,  # Formatter is set on handler
    level=getattr(logging, LOG_LEVEL, logging.INFO)
)
logger = logging.getLogger("jirassicpack")

# Set default logging level to INFO so logs are written
logger.setLevel(logging.INFO)

"""
cli.py

Jirassic Pack CLI entrypoint. Provides a robust, menu-driven command-line interface for interacting with Jira, GitHub, and local LLMs. Features include advanced issue management, analytics, reporting, log analysis, and seamless integration with local and cloud LLMs. The CLI is highly modular, themed after Jurassic Park, and supports batch and interactive modes, robust error handling, and beautiful output via rich.

Key features:
- Modular feature dispatch via menu or config
- Robust config/environment validation
- Advanced logging (JSON, rotation, redaction)
- Local LLM orchestration and health checks
- Batch and interactive feature execution
- Jurassic Park–themed UX and output
- Graceful shutdown and error handling
"""

# Jurassic Park color palette
JUNGLE_GREEN = '\033[38;5;34m'
WARNING_YELLOW = '\033[38;5;226m'
DANGER_RED = '\033[38;5;196m'
EARTH_BROWN = '\033[38;5;94m'
RESET = Style.RESET_ALL

# --- Jurassic Park ASCII Art Banner ---
JIRASSIC_ASCII = r'''
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
||           JIRASSIC PACK       __ ||           JIRASSIC PACK       __ ||
||           / _)               / _)||           / _)               / _)||
||    .-^^^-/ /----------.-^^^-/ /  ||    .-^^^-/ /----------.-^^^-/ /  ||
|| __/       /        __/       /   || __/       /        __/       /   ||
||<__.|_|-|_|       <__.|_|-|_|     ||<__.|_|-|_|       <__.|_|-|_|     ||
||      |  |   ________   |  |      ||      |  |   ________   |  |      ||
||      |  |  |  __  __|  |  |      ||      |  |  |  __  __|  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||      |  |  | |  ||  |  |  |      ||      |  |  | |  ||  |  |  |      ||
||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
'''
BANNER_ALT_TEXT = "JIRASSIC PACK - The Ultimate Jira CLI Experience!"

# --- Jurassic Park ASCII Art Banners by Feature ---
FEATURE_ASCII_ART = {
    'create_issue': r'''\n   __\n  / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🦖\n''',
    'update_issue': r'''\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🦕\n''',
    'bulk_operations': r'''\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🦴\n''',
    'user_team_analytics': r'''\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🧬\n''',
    'integration_tools': r'''\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🔗\n''',
    'time_tracking_worklogs': r'''\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n⏳\n''',
    'automated_documentation': r'''\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n📄\n''',
    'sprint_board_management': r'''\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🌋\n''',
    'advanced_metrics': r'''\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n📊\n''',
    'gather_metrics': r'''\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n📈\n''',
    'summarize_tickets': r'''\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🗂️\n''',
    'ticket_discussion_summary': r'''\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n📄\n''',
}

FEATURE_COLORS = {
    'create_issue': JUNGLE_GREEN,
    'update_issue': WARNING_YELLOW,
    'bulk_operations': DANGER_RED,
    'user_team_analytics': EARTH_BROWN,
    'integration_tools': Fore.CYAN,
    'time_tracking_worklogs': Fore.MAGENTA,
    'automated_documentation': Fore.BLUE,
    'sprint_board_management': Fore.YELLOW,
    'advanced_metrics': Fore.GREEN,
    'gather_metrics': Fore.CYAN,
    'summarize_tickets': Fore.LIGHTYELLOW_EX,
    'ticket_discussion_summary': Fore.LIGHTYELLOW_EX,
}

# Dynamically generate FEATURE_REGISTRY and FEATURE_GROUPS from FEATURE_MANIFEST
# FEATURE_REGISTRY: Maps feature keys to their main module/function for dispatch.
# FEATURE_GROUPS: Organizes features by group for menu display.
FEATURE_REGISTRY = {f['key']: f['module'] for f in FEATURE_MANIFEST}
FEATURE_GROUPS = {}
for f in FEATURE_MANIFEST:
    group = f['group']
    if group not in FEATURE_GROUPS:
        FEATURE_GROUPS[group] = []
    FEATURE_GROUPS[group].append((f["emoji"] + " " + f["label"], f["key"]))

def register_features():
    """
    Dynamically (re)registers all features in the CLI.
    Imports feature modules and updates FEATURE_REGISTRY for dispatch.
    Call this if you add new features at runtime or for hot-reload scenarios.
    """
    global FEATURE_REGISTRY
    from jirassicpack.features import (
        create_issue, update_issue, bulk_operations, user_team_analytics,
        integration_tools, time_tracking_worklogs, automated_documentation, advanced_metrics, sprint_board_management
    )
    from jirassicpack.metrics import gather_metrics
    from jirassicpack.summary import summarize_tickets
    FEATURE_REGISTRY = {
        "create_issue": create_issue,
        "update_issue": update_issue,
        "bulk_operations": bulk_operations,
        "user_team_analytics": user_team_analytics,
        "integration_tools": integration_tools,
        "time_tracking_worklogs": time_tracking_worklogs,
        "automated_documentation": automated_documentation,
        "advanced_metrics": advanced_metrics,
        "gather_metrics": gather_metrics,
        "summarize_tickets": summarize_tickets,
        "sprint_board_management": sprint_board_management,
        "log_parser": log_parser,
        "ticket_discussion_summary": ticket_discussion_summary,
        "test_local_llm": test_local_llm,
        "deep_ticket_summary": deep_ticket_summary,
    }

STATE_FILE = os.path.join(os.getcwd(), ".jirassicpack_cli_state.json")

RECENT_FEATURES = []
LAST_FEATURE = None
LAST_REPORT_PATH = None
FAVORITE_FEATURES = []
CLI_THEME = "default"
CLI_LOG_LEVEL = LOG_LEVEL

# --- State Persistence Helpers ---
def load_cli_state():
    """
    Loads persistent CLI state from disk (recent features, favorites, theme, etc).
    Handles errors gracefully and auto-recovers from malformed or missing state files.
    Updates global state variables for menu and UX continuity.
    """
    global RECENT_FEATURES, LAST_FEATURE, LAST_REPORT_PATH, FAVORITE_FEATURES, CLI_THEME, CLI_LOG_LEVEL
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        RECENT_FEATURES = state.get("recent_features", [])
        LAST_FEATURE = state.get("last_feature")
        LAST_REPORT_PATH = state.get("last_report_path")
        FAVORITE_FEATURES = state.get("favorite_features", [])
        CLI_THEME = state.get("theme", "default")
        CLI_LOG_LEVEL = state.get("log_level", LOG_LEVEL)
    except Exception as e:
        import traceback
        from jirassicpack.utils.logging import contextual_log
        contextual_log(
            'error',
            f"Failed to load CLI state: {e}",
            operation="load_cli_state",
            error_type=type(e).__name__,
            status="error",
            extra={"traceback": traceback.format_exc(), "state_file": STATE_FILE}
        )
        RECENT_FEATURES = []
        LAST_FEATURE = None
        LAST_REPORT_PATH = None
        FAVORITE_FEATURES = []
        CLI_THEME = "default"
        CLI_LOG_LEVEL = LOG_LEVEL
        # Optionally, recreate the file as empty/default
        try:
            with open(STATE_FILE, "w") as f:
                json.dump({
                    "recent_features": [],
                    "last_feature": None,
                    "last_report_path": None,
                    "favorite_features": [],
                    "theme": "default",
                    "log_level": LOG_LEVEL,
                }, f, indent=2)
        except Exception as e2:
            contextual_log(
                'error',
                f"Failed to recreate CLI state file: {e2}",
                operation="recreate_cli_state",
                error_type=type(e2).__name__,
                status="error",
                extra={"traceback": traceback.format_exc(), "state_file": STATE_FILE}
            )

def make_json_safe(obj):
    """
    Recursively converts an object to a JSON-serializable form.
    Strips out functions and non-serializable types, used for safe state persistence.
    """
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items() if not isinstance(v, types.FunctionType)}
    if isinstance(obj, (list, tuple, set)):
        return [make_json_safe(v) for v in obj]
    # For anything else, return its string representation
    return str(obj)

def save_cli_state():
    """
    Saves the current CLI state to disk as JSON.
    Uses make_json_safe to ensure all objects are serializable.
    Logs errors but does not crash the CLI on failure.
    """
    try:
        state = make_json_safe({
            "recent_features": RECENT_FEATURES,
            "last_feature": LAST_FEATURE,
            "last_report_path": LAST_REPORT_PATH,
            "favorite_features": FAVORITE_FEATURES,
            "theme": CLI_THEME,
            "log_level": CLI_LOG_LEVEL,
        })
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        error(f"Failed to save CLI state: {e}")

# --- Onboarding: Step-by-step wizard for first run ---
def onboarding_wizard():
    """
    Interactive onboarding wizard for first-time users.
    Guides the user through theme selection, log level, a quick tour, and optional docs.
    Can be rerun from the Settings menu at any time.
    """
    rich_panel("""
🦖 Welcome to Jirassic Pack CLI!

This wizard will help you get started in under a minute.
""", title="Welcome!", style="banner")
    # Step 1: Theme
    theme = prompt_select("Choose your preferred CLI theme:", choices=["default", "light", "dark", "jurassic", "matrix"])
    global CLI_THEME
    CLI_THEME = theme
    save_cli_state()
    rich_info(f"Theme set to {theme}.")
    # Step 2: Log level
    log_level = prompt_select("Set the log verbosity:", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    global CLI_LOG_LEVEL
    CLI_LOG_LEVEL = log_level
    save_cli_state()
    rich_info(f"Log level set to {log_level}.")
    # Step 3: Tour
    rich_panel("""
Main CLI Features:
- 🦖 Modular menu: Select features by group, favorites, or search.
- ⭐ Pin favorites for quick access.
- 🗂️ Batch mode: Run multiple features in sequence.
- ⚙️ Settings: Change theme, log level, and clear history.
- 🆘 Contextual help in every menu.
- 📄 All reports saved to the output directory.
""", title="Quick Tour", style="info")
    # Step 4: Docs
    open_docs = prompt_select("Would you like to open the documentation in your browser?", choices=["Yes", "No"])
    if open_docs == "Yes":
        import webbrowser
        webbrowser.open("https://github.com/your-org/jirassicpack")
        rich_info("Opened documentation in your browser.")
    rich_success("Onboarding complete! You can rerun this wizard from Settings at any time.")

# --- Enhanced Main Menu (onboarding wizard, batch mode with per-feature options) ---
def feature_menu():
    """
    Main menu loop for the CLI.
    Lets users select feature groups, run batch mode, access favorites, recently used, help, settings, onboarding, or exit.
    Handles dynamic feature discovery, batch planning, and contextual help.
    Yields (feature, group) tuples for the main loop to dispatch.
    """
    from jirassicpack.features import FEATURE_MANIFEST
    global RECENT_FEATURES, LAST_FEATURE, LAST_REPORT_PATH, FAVORITE_FEATURES, CLI_THEME, CLI_LOG_LEVEL
    group_names = ["Batch mode: Run multiple features", "Favorites", "Recently Used"] + list(FEATURE_GROUPS.keys()) + ["Help", "Settings", "Onboarding Wizard", "Exit"]
    while True:
        group_choices = group_names + ["What is this?"]
        group = prompt_select(
            "Select a feature group:",
            choices=group_choices,
            default=group_names[0]
        )
        if group == "What is this?":
            rich_info("🦖 The main menu lets you choose feature groups, access favorites, run multiple features, or change settings. Use arrow keys, numbers, or type to search.")
            continue
        if group == "Onboarding Wizard":
            onboarding_wizard()
            continue
        if group == "Batch mode: Run multiple features":
            # Multi-select features from all groups
            all_features = [{"name": f["emoji"] + " " + f["label"], "value": f["key"]} for f in FEATURE_MANIFEST]
            selected = select_from_list(all_features, message="Select features to run in batch mode (space to select, enter to confirm):", multi=True)
            if not selected:
                continue
            # For each feature, prompt for options if prompt function exists
            import importlib
            batch_plan = []
            for feat_key in selected:
                feat = next((f for f in FEATURE_MANIFEST if f["key"] == feat_key), None)
                prompt_func_name = f"prompt_{feat_key}_options"
                prompt_func = None
                feature_module = feat["module"] if feat else None
                if feature_module and hasattr(feature_module, prompt_func_name):
                    prompt_func = getattr(feature_module, prompt_func_name)
                else:
                    try:
                        mod = importlib.import_module(f"jirassicpack.features.{feat_key}")
                        prompt_func = getattr(mod, prompt_func_name, None)
                    except Exception:
                        prompt_func = None
                if prompt_func:
                    import inspect
                    sig = inspect.signature(prompt_func)
                    if 'jira' in sig.parameters:
                        params = prompt_func({}, jira=None)  # Will be re-prompted with real jira later
                    else:
                        params = prompt_func({})
                else:
                    params = {}
                batch_plan.append({"key": feat_key, "label": feat["label"] if feat else feat_key, "options": params})
            # Show summary
            rich_panel("\n".join([f"{i+1}. {item['label']} (key: {item['key']})" for i, item in enumerate(batch_plan)]), title="Batch Plan", style="info")
            confirm = prompt_select("Proceed to run these features in sequence?", choices=["Yes", "No"])
            if confirm != "Yes":
                continue
            yield batch_plan, "batch_mode"
            continue
        if group == "Help":
            rich_info("🦖 Jirassic Pack CLI Help\n- Use arrow keys, numbers, or type to search.\n- Press Enter to select.\n- 'Back' returns to previous menu.\n- 'Abort' cancels the current operation.\n- 'Settings' lets you change config, log level, and theme.\n- 'Favorites' lets you pin features for quick access.\n- 'Batch mode' lets you run multiple features in sequence.\n- 'Run last feature again' and 'View last report' are available in 'Recently Used'.")
            continue
        if group == "Settings":
            settings_choices = [
                {"name": f"Theme: {CLI_THEME}", "value": "theme"},
                {"name": f"Log level: {CLI_LOG_LEVEL}", "value": "log_level"},
                {"name": "Clear history/reset favorites", "value": "clear_history"},
                {"name": "⬅️ Back to main menu", "value": "return_to_main_menu"},
                {"name": "What is this?", "value": "help"},
                {"name": "Update all caches (refresh user list, etc)", "value": "update_caches"},
            ]
            setting = prompt_select("Settings:", choices=settings_choices)
            if setting == "return_to_main_menu":
                continue
            if setting == "help":
                rich_info("🦖 Settings lets you change the CLI theme, log level, and clear your history/favorites. Theme affects color scheme. Log level controls verbosity.")
                continue
            if setting == "theme":
                theme = prompt_select("Select CLI theme:", choices=["default", "light", "dark", "jurassic", "matrix"])
                CLI_THEME = theme
                save_cli_state()
                rich_info(f"Theme set to {theme} (will apply on next run if not immediate).")
                continue
            if setting == "log_level":
                log_level = prompt_select("Select log level:", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
                CLI_LOG_LEVEL = log_level
                save_cli_state()
                rich_info(f"Log level set to {log_level} (will apply on next run if not immediate).")
                continue
            if setting == "clear_history":
                confirm = prompt_select("Are you sure you want to clear all history and reset favorites?", choices=["Yes, clear all", "No, cancel"])
                if confirm == "Yes, clear all":
                    RECENT_FEATURES.clear()
                    FAVORITE_FEATURES.clear()
                    global LAST_FEATURE, LAST_REPORT_PATH
                    LAST_FEATURE = None
                    LAST_REPORT_PATH = None
                    save_cli_state()
                    rich_info("🦖 All history and favorites have been cleared.")
                else:
                    rich_info("No changes made.")
                continue
            if setting == "update_caches":
                clear_all_caches()
                refresh_user_cache(jira)
                rich_info("All major caches have been refreshed.")
                continue
            continue
        if group == "Exit":
            save_cli_state()
            yield "exit", None
            return
        # Contextual help for group menus
        if group not in FEATURE_GROUPS and group not in ["Favorites", "Recently Used"]:
            continue
        if group == "Favorites":
            fav_choices = []
            for i, feat in enumerate(FAVORITE_FEATURES):
                fav_choices.append({"name": f"[{i+1}] {feat['emoji']} {feat['label']} — {feat['description']}", "value": feat['key']})
            if fav_choices:
                fav_choices.append({"name": "Unpin a feature", "value": "unpin_feature"})
            fav_choices.append({"name": "⬅️ Back to main menu", "value": "return_to_main_menu"})
            fav_choices.append({"name": "What is this?", "value": "help"})
            feature = prompt_select(
                "Favorite features (pinned):",
                choices=fav_choices
            )
            if feature == "return_to_main_menu":
                continue
            if feature == "help":
                rich_info("🦖 Favorites are features you have pinned for quick access. Pin/unpin features from any group menu.")
                continue
            if feature == "unpin_feature":
                if not FAVORITE_FEATURES:
                    rich_info("No favorites to unpin.")
                    continue
                unpin_choices = [f"{feat['emoji']} {feat['label']}" for feat in FAVORITE_FEATURES]
                to_unpin = prompt_select("Select a feature to unpin:", choices=unpin_choices)
                idx = unpin_choices.index(to_unpin)
                FAVORITE_FEATURES.pop(idx)
                save_cli_state()
                rich_info(f"Unpinned {to_unpin} from favorites.")
                continue
            yield feature, group
            continue
        if group == "Recently Used":
            recent_choices = []
            if LAST_FEATURE:
                recent_choices.append({"name": f"🔁 Run last feature again: {LAST_FEATURE['emoji']} {LAST_FEATURE['label']}", "value": LAST_FEATURE['key']})
            if LAST_REPORT_PATH:
                recent_choices.append({"name": f"📄 View last report: {LAST_REPORT_PATH}", "value": "view_last_report"})
            for i, feat in enumerate(RECENT_FEATURES[-5:][::-1]):
                recent_choices.append({"name": f"[{i+1}] {feat['emoji']} {feat['label']} — {feat['description']}", "value": feat['key']})
            recent_choices.append({"name": "⬅️ Back to main menu", "value": "return_to_main_menu"})
            recent_choices.append({"name": "What is this?", "value": "help"})
            feature = prompt_select(
                "Recently used features:",
                choices=recent_choices
            )
            if feature == "return_to_main_menu":
                continue
            if feature == "help":
                rich_info("🦖 Recently Used shows your last 5 features and quick actions. Use it to quickly rerun or access recent reports.")
                continue
            if feature == "view_last_report":
                if LAST_REPORT_PATH and os.path.exists(LAST_REPORT_PATH):
                    os.system(f"open '{LAST_REPORT_PATH}'" if sys.platform == "darwin" else f"xdg-open '{LAST_REPORT_PATH}'")
                else:
                    rich_info("No last report found.")
                continue
            yield feature, group
            continue
        # Normal group
        features = FEATURE_GROUPS[group]
        feature_map = {f['key']: f for f in FEATURE_MANIFEST if f['group'] == group}
        submenu_choices = []
        for i, (name, key) in enumerate(features):
            feat = feature_map.get(key)
            desc = f" — {feat['description']}" if feat and 'description' in feat else ""
            shortcut = f"[{i+1}] "
            submenu_choices.append({"name": f"{shortcut}{name}{desc}", "value": key})
        submenu_choices.append({"name": "Pin a feature to Favorites", "value": "pin_feature"})
        submenu_choices.append({"name": "⬅️ Back to main menu", "value": "return_to_main_menu"})
        submenu_choices.append({"name": "What is this?", "value": "help"})
        feature = prompt_select(
            f"Select a feature from '{group}': (type to search or use number)",
            choices=submenu_choices
        )
        if feature == "return_to_main_menu":
            continue  # Go back to group selection
        if feature == "help":
            rich_info(f"🦖 This menu shows all features in the '{group}' group. Pin your favorites, or select a feature to run.")
            continue
        if feature == "pin_feature":
            pin_choices = [f"{feat['emoji']} {feat['label']}" for feat in feature_map.values() if feat not in FAVORITE_FEATURES]
            if not pin_choices:
                rich_info("All features in this group are already pinned.")
                continue
            to_pin = prompt_select("Select a feature to pin:", choices=pin_choices)
            idx = pin_choices.index(to_pin)
            feat_to_pin = [f for f in feature_map.values() if f not in FAVORITE_FEATURES][idx]
            FAVORITE_FEATURES.append(feat_to_pin)
            save_cli_state()
            rich_info(f"Pinned {to_pin} to favorites.")
            continue
        # Track recent
        feat_obj = feature_map.get(feature)
        if feat_obj and feat_obj not in RECENT_FEATURES:
            RECENT_FEATURES.append(feat_obj)
            save_cli_state()
        if feat_obj:
            LAST_FEATURE = feat_obj
            save_cli_state()
        yield feature, group

# Load CLI state at startup
first_run = not os.path.exists(STATE_FILE)
load_cli_state()
if first_run:
    onboarding_wizard()

# --- Main loop: persistently return to main menu ---
def main() -> None:
    """
    Main entrypoint for the CLI application.
    Handles startup, config loading, onboarding, and persistent menu loop.
    Connects to Jira, registers features, and dispatches user-selected features or batch runs.
    Handles graceful shutdown, error reporting, and LLM server orchestration.
    """
    try:
        logger.info('[DIAGNOSTIC] Logging is working at CLI startup.')
        # Show a single combined welcome panel
        user = None
        config_path = None
        if len(sys.argv) > 1:
            for arg in sys.argv:
                if arg.startswith('--config='):
                    config_path = arg.split('=', 1)[1]
                if arg.startswith('--log-level='):
                    arg.split('=', 1)[1]
        config = ConfigLoader(config_path)
        jira_conf = config.get_jira_config()
        user = jira_conf.get('email', 'User')
        panel_combined_welcome(user)
        rich_info(BANNER_ALT_TEXT)
        options = config.get_options()
        # Print loaded Jira config (redacted token)
        def redact_token(token):
            if not token or len(token) < 7:
                return '***'
            return token[:3] + '*' * (len(token)-6) + token[-3:]
        rich_info(f"Loaded Jira config: URL={jira_conf['url']}, Email={jira_conf['email']}, Token={redact_token(jira_conf['api_token'])}")
        logger.info(f"🦖 Loaded config: {config_path or 'default'} | Jira config: {redact_sensitive(jira_conf)} | Options: {redact_sensitive(options)}", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
        # Prompt for Jira credentials (shared by all features)
        if not jira_conf['url']:
            jira_conf['url'] = prompt_text("Jira URL:", default=os.environ.get('JIRA_URL', 'https://your-domain.atlassian.net'))
            contextual_log('info', "User prompted for Jira URL", operation="user_prompt", status="answered", params={"prompt": "Jira URL"}, extra={"feature": "cli"})
        if not jira_conf['email']:
            jira_conf['email'] = prompt_text("Jira Email:", default=os.environ.get('JIRA_EMAIL', ''))
            contextual_log('info', "User prompted for Jira Email", operation="user_prompt", status="answered", params={"prompt": "Jira Email"}, extra={"feature": "cli"})
        if not jira_conf['api_token']:
            jira_conf['api_token'] = prompt_password("Jira API Token:")
            contextual_log('info', "User prompted for Jira API Token", operation="user_prompt", status="answered", params={"prompt": "Jira API Token"}, extra={"feature": "cli"})
        # Before long operations
        panel_hold_onto_your_butts()
        with spinner("Connecting to Jira..."):
            contextual_log('info', f"🦖 [CLI] Connecting to Jira at {jira_conf['url']} as {jira_conf['email']}", extra={"feature": "cli", "user": jira_conf['email'], "batch": None, "suffix": None, "easteregg": "hold_onto_your_butts"})
            jira = JiraClient(jira_conf['url'], jira_conf['email'], jira_conf['api_token'])
        register_features()
        # Interactive mode: persistent main menu loop
        while True:
            print(f"\n{WARNING_YELLOW}{Style.BRIGHT}Select a feature to run:{RESET}")
            for action, group in feature_menu():
                if group == "batch_mode":
                    # action is a list of dicts: {key, label, options}
                    for i, item in enumerate(action):
                        feat_key = item["key"]
                        feat_options = item["options"]
                        contextual_log('info', f"🦖 [CLI] Batch mode running feature '{feat_key}' for user {jira_conf.get('email')}", extra={"feature": feat_key, "user": jira_conf.get('email'), "batch": i, "suffix": None})
                        run_feature(feat_key, jira, feat_options, user_email=jira_conf.get('email'), batch_index=i, unique_suffix=f"_batch_{i}")
                    continue
                if action == "exit":
                    print(f"{JUNGLE_GREEN}Goodbye!{RESET}")
                    contextual_log('info', "🦖 [CLI] User exited from main menu.", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
                    panel_nobody_cares()
                    rich_info("🦖 CLI halted. User exited from main menu.")
                    try:
                        stop_local_llm_server()
                    except Exception as e:
                        error(f"[EXIT] Failed to stop local LLM server: {e}")
                    halt_cli("User exited from main menu.")
                contextual_log('info', f"🦖 [CLI] User selected feature '{action}' for user {jira_conf.get('email')}", extra={"feature": action, "user": jira_conf.get('email'), "batch": None, "suffix": None})
                run_feature(action, jira, options, user_email=jira_conf.get('email'))
    except Exception as e:
        rich_error(f"Fatal error: {e}")
        try:
            stop_local_llm_server()
        except Exception as e:
            error(f"[EXIT] Failed to stop local LLM server: {e}")

def run_feature(feature: str, jira: JiraClient, options: dict, user_email: str = None, batch_index: int = None, unique_suffix: str = None) -> None:
    """
    Dispatches and runs a single feature by key.
    Handles mapping menu labels to feature keys, context logging, and special-case inline handlers.
    Supports batch mode, user prompts, and robust error handling for all feature types.
    Parameters:
        feature: Feature key or menu label
        jira: JiraClient instance
        options: Feature options/config
        user_email: Email of the user running the feature
        batch_index: Batch run index (if in batch mode)
        unique_suffix: Suffix for output files (if in batch mode)
    """
    update_llm_menu()
    context = {"feature": feature, "user": user_email, "batch": batch_index, "suffix": unique_suffix}
    contextual_log('info', f"🦖 [CLI] run_feature: key={repr(feature)}", extra=context)
    menu_to_key = {
        "🧪 Test connection to Jira": "test_connection",
        "🐙 Test GitHub Connect": "test_github_connect",
        "🦖 Test Local LLM": "test_local_llm",
        "🦖 Start Local LLM Server": "start_local_llm_server",
        "👥 Output all users": "output_all_users",
        "📝 Create a new issue": "create_issue",
        "✏️ Update an existing issue": "update_issue",
        "📋 Sprint and board management": "sprint_board_management",
        "📊 Advanced metrics and reporting": "advanced_metrics",
        "🔁 Bulk operations": "bulk_operations",
        "👤 User and team analytics": "user_team_analytics",
        "🔗 Integration with other tools": "integration_tools",
        "⏱️ Time tracking and worklogs": "time_tracking_worklogs",
        "📄 Automated documentation": "automated_documentation",
        "📈 Gather metrics for a user": "gather_metrics",
        "🗂️ Summarize tickets": "summarize_tickets",
        "🧑‍💻 Get user by accountId/email": "get_user",
        "🔍 Search users": "search_users",
        "🔎 Search users by displayname and email": "search_users_by_displayname_email",
        "🏷️ Get user property": "get_user_property",
        "📋 Get task (issue)": "get_task",
        "⚙️ Get mypreferences": "get_mypreferences",
        "🙋 Get current user (myself)": "get_current_user",
        "🔍 Search logs for points of interest": "log_parser",
        "🏷️ Output all user property keys": "output_all_user_property_keys",
        "🔎 Search issues": "search_issues",
        "📄 Ticket Discussion Summary": "ticket_discussion_summary",
        "👀 Live Tail Local LLM Logs": "live_tail_local_llm_logs",
        "🪵 View Ollama Server Log": "view_ollama_server_log",
        "👀 Live Tail Ollama Server Log": "live_tail_ollama_server_log",
        "🔍 Search Ollama Server Log": "search_ollama_server_log",
        "🧹 Filter Ollama Server Log": "filter_ollama_server_log",
        "🦖 Analyze Logs and Generate Report": "analyze_logs_and_generate_report",
    }
    key = menu_to_key.get(feature, feature)
    context = {"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix}
    feature_tag = f"[{key}]"
    contextual_log('info', f"🦖 [CLI] run_feature: key={repr(key)}", extra=context)
    if key == "test_github_connect":
        test_github_connect()
        return
    if key == "test_local_llm":
        FEATURE_REGISTRY[key](options, user_email=user_email, batch_index=batch_index, unique_suffix=unique_suffix)
        return
    if key == "test_connection":
        test_connection(jira, options, context)
        return
    if key == "output_all_users":
        contextual_log('info', f"{feature_tag} Outputting all users. Options: {redact_sensitive(options)}", extra=context)
        output_all_users(jira, options, options.get('unique_suffix', ''))
        return
    if key == "output_all_user_property_keys":
        output_all_user_property_keys(jira, options, options.get('unique_suffix', ''))
        return
    # Inline handlers for user features
    if key == "get_user":
        try:
            # Prompt for accountId using the search helper
            account_id = select_account_id(jira)
            # Prompt for email using a user search helper, or allow manual entry
            email = None
            search_email = prompt_checkbox("Would you like to search for a user to fill in the email?", default=True)
            if search_email:
                users = jira.search_users("")
                email_choices = [u.get('emailAddress') for u in users if u.get('emailAddress')]
                if email_choices:
                    picked = prompt_select("Select an email:", choices=email_choices + ["(Enter manually)"])
                    if picked == "(Enter manually)":
                        email = prompt_text("Enter email (leave blank if not used):")
                    else:
                        email = picked
                else:
                    email = prompt_text("Enter email (leave blank if not used):")
            else:
                email = prompt_text("Enter email (leave blank if not used):")
            # Prompt for username and user key, but allow skipping
            username = prompt_text("Username (leave blank if not used):")
            key_ = prompt_text("User key (leave blank if not used):")
            result = jira.get_user(account_id=account_id or None, email=email or None, username=username or None, key=key_ or None)
            if not result:
                info(ABORTED)
                return
            pretty_print_result(result)
        except Exception as e:
            error(FAILED_TO.format(action='fetch user', error=e), extra=context)
            contextual_log('error', f"🦖 [CLI] Error fetching user: {e}", exc_info=True, extra=context)
        return
    if key == "search_users":
        try:
            query = prompt_text("Search query (name/email):")
            contextual_log('info', f"🦖 [CLI] User searched users with query: {query}", extra={"feature": key, "easteregg": "clever_girl" if 'raptor' in query.lower() else None})
            result = jira.search_users(query=query)
            if not result:
                panel_nobody_cares()
                info(NO_ISSUES_FOUND)
                return
            panel_clever_girl()
            pretty_print_result(result)
        except Exception as e:
            panel_big_pile_of_errors()
            error(FAILED_TO.format(action='search users', error=e), extra=context)
            contextual_log('error', f"🦖 [CLI] Error searching users: {e}", exc_info=True, extra=context)
        return
    if key == "search_users_by_displayname_email":
        try:
            displayname = prompt_text("Display name (leave blank if not used):")
            email = prompt_text("Email (leave blank if not used):")
            params = {}
            if displayname:
                params['query'] = displayname
            if email:
                params['username'] = email
            contextual_log('info', f"🦖 [CLI] User searched users by displayname and email with params: {params}", extra=context)
            result = jira.get('users/search', params=params)
            if not result:
                info(NO_ISSUES_FOUND)
                return
            pretty_print_result(result)
        except Exception as e:
            error(FAILED_TO.format(action='search users by displayname and email', error=e), extra=context)
            contextual_log('error', f"🦖 [CLI] Error searching users: {e}", exc_info=True, extra=context)
        return
    if key == "get_user_property":
        try:
            account_id = select_account_id(jira)
            property_key = select_property_key(jira, account_id)
            result = jira.get_user_property(account_id, property_key)
            if not result:
                info(ABORTED)
                return
            pretty_print_result(result)
        except Exception as e:
            error(FAILED_TO.format(action='fetch user property', error=e), extra=context)
            contextual_log('error', f"🦖 [CLI] Error fetching user property: {e}", exc_info=True, extra=context)
        return
    if key == "get_task":
        try:
            issue_key = search_issues(jira)
            if issue_key:
                info(f"Selected issue: {issue_key}")
                result = jira.get_task(issue_key)
                pretty_print_result(result)
            return
        except Exception as e:
            error(FAILED_TO.format(action='fetch task', error=e), extra=context)
            contextual_log('error', f"🦖 [CLI] Error fetching task: {e}", exc_info=True, extra=context)
        return
    if key == "get_mypreferences":
        try:
            result = jira.get_mypreferences()
            pretty_print_result(result)
        except Exception as e:
            # Check for HTTP error code if available
            msg = str(e)
            if ("400" in msg or "404" in msg or "Bad Request" in msg or "not found" in msg.lower()):
                error_msg = "🦖 The 'mypreferences' endpoint is not supported on your Jira instance. (Jira Cloud does not support this endpoint.)"
                print(DANGER_RED + error_msg + RESET)
                contextual_log('error', f"🦖 [CLI] {error_msg} Exception: {e}", exc_info=True, extra=context)
            else:
                error(FAILED_TO.format(action='fetch mypreferences', error=e), extra=context)
                contextual_log('error', f"🦖 [CLI] Exception: {e}", exc_info=True, extra=context)
        return
    if key == "get_current_user":
        try:
            result = jira.get_current_user()
            if not result:
                info(ABORTED)
                return
            pretty_print_result(result)
        except Exception as e:
            error(FAILED_TO.format(action='fetch current user', error=e), extra=context)
            contextual_log('error', f"🦖 [CLI] Error fetching current user: {e}", exc_info=True, extra=context)
        return
    if key == "search_issues":
        try:
            issue_key = search_issues(jira)
            if not issue_key:
                info(NO_ISSUES_FOUND)
                return
            info(f"Selected issue: {issue_key}")
        except Exception as e:
            error(FAILED_TO.format(action='search issues', error=e), extra=context)
            contextual_log('error', f"🦖 [CLI] Error searching issues: {e}", exc_info=True, extra=context)
        return
    if key == "start_local_llm_server":
        start_local_llm_server()
        return
    if key == "stop_local_llm_server":
        stop_local_llm_server()
        return
    if key == "view_local_llm_logs":
        view_local_llm_logs()
        return
    if key == "live_tail_local_llm_logs":
        live_tail_local_llm_logs()
        return
    if key == "view_ollama_server_log":
        view_ollama_server_log()
        return
    if key == "live_tail_ollama_server_log":
        live_tail_ollama_server_log()
        return
    if key == "search_ollama_server_log":
        search_ollama_server_log()
        return
    if key == "filter_ollama_server_log":
        filter_ollama_server_log()
        return
    if key == "analyze_logs_and_generate_report":
        analyze_logs_and_generate_report()
        return
    # Only now check for FEATURE_REGISTRY
    if key not in FEATURE_REGISTRY:
        error(f"{feature_tag} Unknown feature: {feature}", extra=context)
        contextual_log('error', f"🦖 [CLI] Unknown feature: {feature}", exc_info=True, extra=context)
        return
    contextual_log('info', f"🦖 [CLI] Dispatching feature: {key} | Options: {redact_sensitive(options)} {context}", extra=context)
    # --- Refactored: Parameter gathering and validation before spinner ---
    prompt_func_name = f"prompt_{key}_options"
    prompt_func = None
    feature_module = FEATURE_REGISTRY[key]
    contextual_log('info', f"🦖 [CLI] Looking for prompt function: {prompt_func_name} in {feature_module}", extra=context)
    if hasattr(feature_module, prompt_func_name):
        prompt_func = getattr(feature_module, prompt_func_name)
        contextual_log('info', f"🦖 [CLI] Found prompt function: {prompt_func_name} in module {feature_module}", extra=context)
    else:
        try:
            import importlib
            mod = importlib.import_module(f"jirassicpack.features.{key}")
            prompt_func = getattr(mod, prompt_func_name, None)
            contextual_log('info', f"🦖 [CLI] Imported module jirassicpack.features.{key}, found prompt_func: {bool(prompt_func)}", extra=context)
        except Exception as e:
            contextual_log('error', f"🦖 [CLI] Could not import prompt function for {key}: {e}", exc_info=True, extra=context)
            prompt_func = None
    if prompt_func:
        import inspect
        sig = inspect.signature(prompt_func)
        contextual_log('info', f"🦖 [CLI] prompt_func signature: {sig}", extra=context)
        if 'jira' in sig.parameters:
            contextual_log('info', "[DEBUG] Calling prompt_func with jira", extra=context)
            params = prompt_func(options, jira=jira)
        else:
            contextual_log('info', "[DEBUG] Calling prompt_func without jira", extra=context)
            params = prompt_func(options)
        contextual_log('info', f"🦖 [CLI] prompt_func returned params: {params}", extra=context)
        if not params:
            contextual_log('info', f"🦖 [CLI] Feature '{key}' cancelled or missing parameters for user {user_email}", extra=context)
            return
    else:
        contextual_log('info', f"🦖 [CLI] No prompt_func found for {key}, using options as params.", extra=context)
        params = options
    # Now call the feature handler (which should only perform the operation, with spinner inside if needed)
    start_time = time.time()
    contextual_log('info', f"🦖 [CLI] Feature '{key}' execution started for user {user_email}", operation="feature_start", params=redact_sensitive(options), extra=context)
    FEATURE_REGISTRY[key](jira, params, user_email=user_email, batch_index=batch_index, unique_suffix=unique_suffix)
    duration = int((time.time() - start_time) * 1000)
    contextual_log('info', f"🦖 [CLI] Feature '{key}' execution finished for user {user_email} in {duration}ms", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(options), extra=context)
    contextual_log('info', f"🦖 [CLI] Feature '{key}' complete for user {user_email}", extra=context)

def test_connection(jira: JiraClient, options: dict = None, context: str = "") -> None:
    with spinner("Testing Jira connection..."):
        try:
            # Log parameters
            contextual_log('info', f"🦖 [CLI] [test_connection] Parameters: url={jira.base_url}, email={jira.auth[0]}", extra=context)
            # Log full request details
            endpoint = 'myself'
            params = None
            contextual_log('info', f"🦖 [CLI] [test_connection] Request: endpoint={endpoint}, headers=REDACTED, params={params}", extra=context)
            contextual_log('info', "🦖 [CLI] [test_connection] Starting Jira connection test.", extra=context)
            user = jira.get(endpoint)
            contextual_log('info', f"🦖 [CLI] [test_connection] Response: {user}", extra=context)
            contextual_log('info', f"🦖 [CLI] [test_connection] Jira connection successful for user {user.get('displayName', user.get('name', 'Unknown'))}", extra=context)
            print(f"{JUNGLE_GREEN}🦖 Connection successful! Logged in as: {user.get('displayName', user.get('name', 'Unknown'))}{RESET}")
            contextual_log('info', "🦖 [CLI] Welcome to Jurassic Park.", extra=context)
            info("🦖 Welcome to Jurassic Park.")
        except Exception as e:
            contextual_log('error', f"🦖 [CLI] [test_connection] Failed to connect to Jira: {e}", exc_info=True, extra=context)
            error(FAILED_TO.format(action='connect to Jira', error=e), extra=context)

def output_all_users(jira: JiraClient, options: dict, unique_suffix: str = "") -> None:
    output_dir = options.get('output_dir', 'output')
    ensure_output_dir(output_dir)
    with spinner("Fetching users from Jira..."):
        try:
            users = jira.get('users/search', params={'maxResults': 1000})
            if not users:
                panel_nobody_cares()
                info(NO_ISSUES_FOUND)
                return
            filename = f"{output_dir}/jira_users{unique_suffix}.md"
            try:
                with open(filename, 'w') as f:
                    f.write("# Jira Users\n\n")
                    for user in users:
                        f.write(f"- {user.get('displayName', user.get('name', 'Unknown'))} ({user.get('emailAddress', 'N/A')})\n")
                panel_objects_in_mirror()
                info(WRITTEN_TO.format(item='user list', filename=filename))
            except Exception as file_err:
                panel_big_pile_of_errors()
                error(FAILED_TO.format(action='write user list to file', error=file_err), extra={"feature": "output_all_users", "user": None, "batch": None, "suffix": unique_suffix})
        except Exception as e:
            panel_big_pile_of_errors()
            error(FAILED_TO.format(action='fetch users', error=e), extra={"feature": "output_all_users", "user": None, "batch": None, "suffix": unique_suffix})

def output_all_user_property_keys(jira: JiraClient, options: dict, unique_suffix: str = "") -> None:
    """
    Fetches and writes all property keys for a selected Jira user to a Markdown file.
    Prompts the user to select a user, fetches property keys, and writes them to disk.
    Args:
        jira (JiraClient): Authenticated Jira client.
        options (dict): CLI options, including output_dir.
        unique_suffix (str, optional): Suffix for output filename.
    """
    context = {"feature": "output_all_user_property_keys", "user": None, "batch": None, "suffix": unique_suffix}
    output_dir = options.get('output_dir', 'output')
    ensure_output_dir(output_dir)
    label, user_obj = select_jira_user(jira)
    if not user_obj or not user_obj.get('accountId'):
        info(ABORTED)
        return
    account_id = user_obj['accountId']
    display_name = user_obj.get('displayName', account_id)
    with spinner("Fetching user property keys from Jira..."):
        try:
            resp = jira.get('user/properties', params={'accountId': account_id})
            keys = resp.get('keys', [])
            safe_name = re.sub(r'[^\w.-]', '_', display_name)
            filename = f"{output_dir}/user_property_keys_{safe_name}{unique_suffix}.md"
            with open(filename, 'w') as f:
                f.write(f"# User Property Keys for {display_name} ({account_id})\n\n")
                if not keys:
                    f.write("No property keys found for this user.\n")
                else:
                    for k in keys:
                        f.write(f"- {k.get('key')}\n")
            print(f"{JUNGLE_GREEN}🦖 User property keys written to {filename}{RESET}")
            info(WRITTEN_TO.format(item='user property keys', filename=filename))
        except Exception as e:
            error(FAILED_TO.format(action='fetch user property keys', error=e), extra=context)
            contextual_log('error', f"🦖 [CLI] [output_all_user_property_keys] Exception: {e}", exc_info=True, extra=context)

def pretty_print_result(result):
    """
    Pretty-prints a result object as formatted JSON in a rich panel.
    Args:
        result (Any): The object to print.
    """
    rich_panel(json.dumps(result, indent=2), style="info")

def halt_cli(reason=None):
    """
    Halts the CLI application, printing a message and logging the reason.
    Args:
        reason (str, optional): Reason for halting.
    """
    msg = f"🦖 CLI halted. {reason}" if reason else "🦖 CLI halted."
    rich_error(msg)
    contextual_log('warning', msg, extra={"feature": "cli"})
    sys.exit(0)

# Helper to check if a process is running (basic check)
def is_process_running(process_name):
    """
    Checks if a process with the given name is running on the system.
    Args:
        process_name (str): Name or substring of the process to check.
    Returns:
        bool: True if running, False otherwise.
    """
    try:
        import psutil
    except ImportError:
        print("[ERROR] The 'psutil' package is required for process management. Please install it with 'pip install psutil'.")
        return False
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if process_name in ' '.join(proc.info['cmdline']):
                return True
        except Exception:
            continue
    return False

def get_llm_status():
    """
    Returns a status indicator (emoji) for the local LLM server and API processes.
    Returns:
        str: Emoji status (🟢 or 🔴)
    """
    try:
        import psutil  # Only import if needed
    except ImportError:
        return '🔴 (psutil not installed)'
    ollama_running = is_process_running('ollama')
    http_api_running = is_process_running('http_api.py')
    if ollama_running and http_api_running:
        return '🟢'
    return '🔴'

# Update menu with status indicator
def update_llm_menu():
    """
    Updates the Local LLM Tools menu group with current status and options.
    """
    status = get_llm_status()
    FEATURE_GROUPS["Local LLM Tools"] = [
        (f"🦖 Start Local LLM Server {status}", "start_local_llm_server"),
        ("🛑 Stop Local LLM Server", "stop_local_llm_server"),
        ("🪵 View Local LLM Logs", "view_local_llm_logs"),
        ("🪵 View Ollama Server Log", "view_ollama_server_log"),
        ("👀 Live Tail Ollama Server Log", "live_tail_ollama_server_log"),
        ("🔍 Search Ollama Server Log", "search_ollama_server_log"),
        ("🧹 Filter Ollama Server Log", "filter_ollama_server_log"),
        ("🦖 Test Local LLM", "test_local_llm"),
        ("👀 Live Tail Local LLM Logs", "live_tail_local_llm_logs"),
    ]

update_llm_menu()

def start_local_llm_server():
    """
    Starts the local LLM server (ollama and http_api.py) if not already running.
    Checks for binaries, launches processes, and performs health checks.
    """
    info("🦖 Starting local LLM server...")
    # Check if the server is already running
    try:
        resp = requests.get("http://localhost:5000/health", timeout=2)
        if resp.status_code == 200:
            info("[INFO] Local LLM server is already running at http://localhost:5000.")
            logger.info("[LLM] Local LLM server already running at http://localhost:5000.")
            return
    except Exception:
        pass
    if not shutil.which("ollama"):
        error("[ERROR] 'ollama' is not installed or not in PATH.")
        return
    if not is_process_running("ollama"): 
        try:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            info("Started 'ollama serve' in the background.")
        except Exception as e:
            error(FAILED_TO.format(action='start ollama', error=e))
    else:
        info("'ollama serve' is already running.")
    import os
    ollama_dir = os.path.abspath(os.path.join(os.getcwd(), "../Ollama7BPoc"))
    http_api_path = os.path.join(ollama_dir, "http_api.py")
    fallback_api_path = "/Users/mykalthomas/Documents/work/Ollama7BPoc/http_api.py"
    fallback_api_dir = "/Users/mykalthomas/Documents/work/Ollama7BPoc"
    info(f"[LLM] Checking dynamic path: {http_api_path}")
    logger.info(f"[LLM] Checking dynamic path: {http_api_path}")
    info(f"[LLM] Checking user-provided absolute path: {fallback_api_path}")
    logger.info(f"[LLM] Checking user-provided absolute path: {fallback_api_path}")
    if os.path.exists(http_api_path):
        api_path = http_api_path
        api_dir = ollama_dir
        info(f"[LLM] Using dynamic path for http_api.py: {api_path}")
        logger.info(f"[LLM] Using dynamic path for http_api.py: {api_path}")
    elif os.path.exists(fallback_api_path):
        api_path = fallback_api_path
        api_dir = fallback_api_dir
        info(f"[LLM] Using user-provided absolute path for http_api.py: {api_path}")
        logger.info(f"[LLM] Using user-provided absolute path for http_api.py: {api_path}")
    else:
        error(f"[LLM] Could not find http_api.py at {http_api_path} or {fallback_api_path}")
        logger.error(f"[LLM] Could not find http_api.py at {http_api_path} or {fallback_api_path}")
        return
    if not is_process_running("http_api.py"):
        try:
            info(f"[LLM] Attempting to start http_api.py from {api_path} (cwd={api_dir})")
            logger.info(f"[LLM] Attempting to start http_api.py from {api_path} (cwd={api_dir})")
            subprocess.Popen(["python", api_path], cwd=api_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            info(f"Started 'http_api.py' in the background from {api_path}.")
            logger.info(f"[LLM] Started http_api.py in the background from {api_path}.")
        except Exception as e:
            error(FAILED_TO.format(action='start http_api.py', error=e))
            logger.error(f"[LLM] Failed to start 'http_api.py': {e}")
    else:
        info("[LLM] 'http_api.py' is already running.")
        logger.info("[LLM] 'http_api.py' is already running.")
    # Health check
    info("Checking local LLM health endpoint...")
    try:
        for _ in range(10):
            try:
                resp = requests.get("http://localhost:5000/health", timeout=2)
                if resp.status_code == 200 and resp.json().get("status") == "ok":
                    info("🟢 Local LLM health check passed!")
                    break
                else:
                    info("[WARN] Health endpoint returned non-ok status.")
            except Exception:
                info("[INFO] Waiting for local LLM to become healthy...")
                time.sleep(1)
        else:
            error("[ERROR] Local LLM health check failed after waiting.")
    except Exception as e:
        error(FAILED_TO.format(action='health check', error=e))
    info("🦖 Local LLM server startup attempted. Use 'Test Local LLM' to verify health.")

def stop_local_llm_server():
    """
    Stops the local LLM server processes (ollama, http_api.py) and ensures shutdown.
    Attempts to terminate by process name and by port.
    """
    info("🛑 Stopping local LLM server...")
    # Try health check, but proceed regardless of result
    try:
        resp = requests.get("http://localhost:5000/health", timeout=2)
        if resp.status_code == 200:
            pass
    except Exception:
        pass
    try:
        import psutil
        import os
        candidates = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmd = ' '.join(proc.info['cmdline'])
                if ('ollama' in cmd or 'http_api.py' in cmd or '/Ollama7BPoc/http_api.py' in cmd):
                    candidates.append(proc)
            except Exception:
                continue
        stopped = False
        for proc in candidates:
            try:
                info(f"Terminating PID {proc.info['pid']}: {proc.info['cmdline']}")
                proc.terminate()
                stopped = True
            except Exception as e:
                error(FAILED_TO.format(action='terminate process', error=e))
        # Optionally, kill by port 5000
        import subprocess
        try:
            output = subprocess.check_output(["lsof", "-i", ":5000", "-t"])
            pids = set(int(pid) for pid in output.decode().split())
            for pid in pids:
                info(f"Killing process on port 5000: PID {pid}")
                os.kill(pid, 9)
                stopped = True
        except Exception:
            pass
        if stopped:
            info("🛑 Local LLM server processes terminated.")
        else:
            info("No local LLM server processes found to stop.")
    except ImportError:
        error("[ERROR] The 'psutil' package is required for process management. Please install it with 'pip install psutil'.")
        return
    # Safety: health check to confirm server has stopped
    import time
    for _ in range(5):
        try:
            resp = requests.get("http://localhost:5000/health", timeout=2)
            if resp.status_code == 200:
                time.sleep(1)
            else:
                break
        except Exception:
            info("[INFO] Confirmed: Local LLM server is no longer responding at http://localhost:5000.")
            break
    else:
        info("[WARN] Local LLM server may still be running or is stuck.")

def view_local_llm_logs():
    """
    Prints the last 20 lines of ollama.log and http_api.log for local LLM diagnostics.
    """
    import os
    ollama_log = os.path.expanduser("~/.ollama/ollama.log")
    ollama_dir = os.path.abspath(os.path.join(os.getcwd(), "../Ollama7BPoc"))
    http_api_log = os.path.join(ollama_dir, "llm_api.log")
    print("--- ollama.log (last 20 lines) ---")
    if os.path.exists(ollama_log):
        with open(ollama_log) as f:
            lines = f.readlines()
            print(''.join(lines[-20:]))
    else:
        print("No ollama.log found.")
    print("--- http_api.log (last 20 lines) ---")
    if os.path.exists(http_api_log):
        with open(http_api_log) as f:
            lines = f.readlines()
            print(''.join(lines[-20:]))
    else:
        print("No http_api.log found.")

def live_tail_file(filepath, label):
    """
    Live-tails a log file, printing new lines as they appear. Handles log rotation and errors.
    Args:
        filepath (str): Path to the log file.
        label (str): Human-readable label for the log.
    """
    import os
    import time
    rich_panel(f"--- {label} (live tail, Ctrl+C to exit) ---", style="info")
    last_inode = None
    try:
        while True:
            try:
                if not os.path.exists(filepath):
                    rich_error(f"No {label} found at {filepath}. Retrying in 2s...")
                    time.sleep(2)
                    continue
                with open(filepath, 'r') as f:
                    f.seek(0, os.SEEK_END)
                    last_inode = os.fstat(f.fileno()).st_ino
                    while True:
                        line = f.readline()
                        if line:
                            rich_info(line.rstrip())
                        else:
                            time.sleep(0.5)
                            # Check for log rotation/truncation
                            try:
                                if os.stat(filepath).st_ino != last_inode:
                                    rich_info(f"\n[INFO] {label} was rotated or truncated. Re-opening...")
                                    break
                            except Exception:
                                break
            except PermissionError:
                rich_error(f"[ERROR] Permission denied for {label} at {filepath}. Retrying in 2s...")
                time.sleep(2)
                continue
            except FileNotFoundError:
                rich_error(f"[ERROR] {label} not found at {filepath}. Retrying in 2s...")
                time.sleep(2)
                continue
            except Exception as e:
                rich_error(f"[ERROR] Unexpected error tailing {label}: {e}. Retrying in 2s...")
                time.sleep(2)
                continue
    except KeyboardInterrupt:
        rich_info(f"\nStopped tailing {label}.")
    except Exception as e:
        rich_error(f"[ERROR] Fatal error in tailing {label}: {e}")

def live_tail_local_llm_logs():
    """
    Starts two threads to live-tail both ollama.log and http_api.log simultaneously.
    Handles Ctrl+C and thread errors gracefully.
    """
    import os
    ollama_log = os.path.expanduser("~/.ollama/ollama.log")
    ollama_dir = os.path.abspath(os.path.join(os.getcwd(), "../Ollama7BPoc"))
    http_api_log = os.path.join(ollama_dir, "llm_api.log")
    def tail1():
        try:
            live_tail_file(ollama_log, "ollama.log")
        except Exception as e:
            print(f"[ERROR] ollama.log tailing thread: {e}")
    def tail2():
        try:
            live_tail_file(http_api_log, "http_api.log")
        except Exception as e:
            print(f"[ERROR] http_api.log tailing thread: {e}")
    print("Tailing both ollama.log and http_api.log. Press Ctrl+C to stop.")
    t1 = threading.Thread(target=tail1, daemon=True)
    t2 = threading.Thread(target=tail2, daemon=True)
    t1.start()
    t2.start()
    try:
        while t1.is_alive() or t2.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped live tailing logs.")
        stop_event.set()
    except Exception as e:
        print(f"[ERROR] Fatal error in live tailing logs: {e}")

def view_ollama_server_log():
    """
    Prints the last 40 lines of the Ollama server log for diagnostics.
    """
    log_path = "/Users/mykalthomas/Documents/work/Ollama7BPoc/ollama_server.log"
    print("--- ollama_server.log (last 40 lines) ---")
    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
            print(''.join(lines[-40:]))
    except FileNotFoundError:
        print(f"No ollama_server.log found at {log_path}.")
    except Exception as e:
        print(f"[ERROR] Could not read ollama_server.log: {e}")

def live_tail_ollama_server_log():
    """
    Live-tails the Ollama server log, printing new lines as they appear.
    Handles Ctrl+C and file errors.
    """
    import time
    log_path = "/Users/mykalthomas/Documents/work/Ollama7BPoc/ollama_server.log"
    print("--- Live tailing ollama_server.log (Ctrl+C to stop) ---")
    try:
        with open(log_path, 'r') as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    print(line.rstrip())
                else:
                    time.sleep(0.5)
    except FileNotFoundError:
        print(f"No ollama_server.log found at {log_path}.")
    except KeyboardInterrupt:
        print("\nStopped live tailing ollama_server.log.")
    except Exception as e:
        print(f"[ERROR] Could not tail ollama_server.log: {e}")

def search_ollama_server_log():
    """
    Prompts the user for a search string and prints all matching lines from the Ollama server log.
    """
    log_path = "/Users/mykalthomas/Documents/work/Ollama7BPoc/ollama_server.log"
    query = prompt_text("Enter search string for ollama_server.log:")
    print(f"--- Search results for '{query}' in ollama_server.log ---")
    try:
        with open(log_path, 'r') as f:
            matches = [line for line in f if query.lower() in line.lower()]
            if matches:
                print(''.join(matches))
            else:
                print("No matches found.")
    except FileNotFoundError:
        print(f"No ollama_server.log found at {log_path}.")
    except Exception as e:
        print(f"[ERROR] Could not search ollama_server.log: {e}")

def filter_ollama_server_log():
    """
    Prompts the user for a log level and prints all matching lines from the Ollama server log.
    """
    log_path = "/Users/mykalthomas/Documents/work/Ollama7BPoc/ollama_server.log"
    level = prompt_text("Enter log level to filter by (e.g., INFO, ERROR, WARNING):")
    print(f"--- ollama_server.log filtered by level '{level.upper()}' ---")
    try:
        with open(log_path, 'r') as f:
            matches = [line for line in f if level.upper() in line]
            if matches:
                print(''.join(matches))
            else:
                print(f"No lines found with level '{level.upper()}'.")
    except FileNotFoundError:
        print(f"No ollama_server.log found at {log_path}.")
    except Exception as e:
        print(f"[ERROR] Could not filter ollama_server.log: {e}")

def analyze_logs_and_generate_report():
    """
    Analyzes multiple log files and generates a Markdown report summarizing errors, warnings, and info entries.
    Writes a summary table and top issues for each log.
    """
    import os
    import datetime
    log_files = [
        ("jirassicpack.log", "Jirassic Pack CLI Log"),
        ("/Users/mykalthomas/Documents/work/Ollama7BPoc/ollama_server.log", "Ollama Server Log"),
        ("/Users/mykalthomas/Documents/work/Ollama7BPoc/http_api.log", "Local LLM API Log"),
    ]
    now = datetime.datetime.now()
    output_path = f"output/log_analysis_report_{now.strftime('%Y%m%d_%H%M%S')}.md"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    md_file = MdUtils(file_name=output_path, title="🦖 Log Analysis Report")
    md_file.new_line(f"_Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}_")
    md_file.new_line()
    md_file.new_header(level=2, title="Summary Table")
    table_data = ["Log File", "Errors", "Warnings", "Info"]
    summary = []
    details = []
    for log_path, label in log_files:
        errors, warnings, infos = [], [], []
        if not os.path.exists(log_path):
            summary.extend([label, "N/A", "N/A", "N/A"])
            details.append((label, None, None, None, log_path))
            continue
        with open(log_path, 'r') as f:
            for line in f:
                if 'ERROR' in line:
                    errors.append(line.strip())
                elif 'WARN' in line or 'WARNING' in line:
                    warnings.append(line.strip())
                elif 'INFO' in line:
                    infos.append(line.strip())
        summary.extend([label, str(len(errors)), str(len(warnings)), str(len(infos))])
        details.append((label, errors, warnings, infos, log_path))
    rows = len(log_files) + 1
    md_file.new_table(columns=4, rows=rows, text=table_data + summary, text_align='center')
    md_file.new_line()
    for label, errors, warnings, infos, log_path in details:
        md_file.new_header(level=2, title=label)
        if errors is None:
            md_file.new_line(f"File not found: `{log_path}`")
            md_file.new_line('---')
            continue
        if errors:
            md_file.new_header(level=3, title="Top 5 Errors")
            md_file.new_list(errors[-5:])
        if warnings:
            md_file.new_header(level=3, title="Top 5 Warnings")
            md_file.new_list(warnings[-5:])
        md_file.new_line('---')
    md_file.create_md_file()
    info(WRITTEN_TO.format(item='Log analysis report', filename=output_path))

def test_github_connect(config: dict = None) -> None:
    """
    Test connectivity to the GitHub API using the configured token.
    Fetches the authenticated user and reports success/failure with rich output.
    Args:
        config (dict, optional): Config dictionary. If None, loads from ConfigLoader.
    Returns:
        None. Prints result to CLI.
    """
    if config is None:
        config = ConfigLoader().get_github_config()
    token = config.get('token') or os.environ.get('GITHUB_TOKEN')
    if not token:
        rich_error("No GitHub token found in config or environment.")
        return
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    try:
        resp = requests.get("https://api.github.com/user", headers=headers, timeout=10)
        if resp.status_code == 200:
            user = resp.json()
            login = user.get('login', 'N/A')
            name = user.get('name', '')
            rich_success(f"✅ GitHub connection successful! Authenticated as: {login} {f'({name})' if name else ''}")
            rich_panel(f"User: {login}\nName: {name or 'N/A'}\nID: {user.get('id', 'N/A')}\nType: {user.get('type', 'N/A')}\nPublic Repos: {user.get('public_repos', 'N/A')}", title="GitHub User Info", style="success")
        elif resp.status_code == 401:
            rich_error("❌ GitHub authentication failed. Invalid or expired token.")
        else:
            rich_error(f"❌ GitHub API error: {resp.status_code} {resp.text}")
    except Exception as e:
        rich_error(f"❌ Exception during GitHub connect test: {e}")

# --- Autoreload logic for development ---
if __name__ == "__main__":
    # If JIRASSICPACK_AUTORELOAD=1, enable watchdog-based autoreload for development
    if os.environ.get("JIRASSICPACK_AUTORELOAD") == "1":
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        import threading

        class ReloadHandler(FileSystemEventHandler):
            """
            Watches for file changes in the CLI directory and triggers a restart on any .py file change.
            Used for hot-reloading during development.
            """
            def __init__(self, restart):
                self.restart = restart
            def on_any_event(self, event):
                if event.src_path.endswith(".py"):
                    print("🔄 Code change detected, reloading...")
                    self.restart()

        def restart():
            """
            Stops the observer and restarts the CLI process.
            """
            observer.stop()
            print("🔄 Code change detected, restarting CLI...")
            os.execv(sys.executable, [sys.executable] + sys.argv)

        event_handler = ReloadHandler(restart)
        observer = Observer()
        observer.schedule(event_handler, path=os.path.dirname(__file__), recursive=True)
        observer.start()
        try:
            main()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
    else:
        main() 