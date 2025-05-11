import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
from jirassicpack.config import ConfigLoader
from jirassicpack.jira_client import JiraClient
import questionary
from typing import Any, Dict
from jirassicpack.utils import error, info, spinner, progress_bar, contextual_log, redact_sensitive
from colorama import Fore, Style
import pyfiglet
from pythonjsonlogger import jsonlogger
import json
from dotenv import load_dotenv
import uuid
import platform
import socket
from datetime import datetime
import re
import inspect

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
handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5)
if LOG_FORMAT == 'json':
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s %(feature)s %(user)s %(batch)s %(suffix)s %(function)s %(operation_id)s %(operation)s %(params)s %(status)s %(error_type)s %(correlation_id)s %(duration_ms)s %(output_file)s %(retry_count)s %(env)s %(cli_version)s %(hostname)s %(pid)s')
else:
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logging.basicConfig(
    handlers=[handler],
    format=None,  # Formatter is set on handler
    level=getattr(logging, LOG_LEVEL, logging.INFO)
)
logger = logging.getLogger("jirassicpack")

# cli.py
# This module provides the command-line interface (CLI) entrypoint for the jirassicPack tool.
# It handles argument parsing, configuration loading, and dispatches to the appropriate feature based on user input or config.
# Ensures output directories exist and provides a consistent entrypoint for all features.

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
}

# Utility for output directory
def ensure_output_dir(directory: str) -> None:
    """
    Ensure the output directory exists, creating it if necessary.
    Used by all features to guarantee output files can be written.
    """
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

# Feature registration table (imported lazily to avoid circular imports)
FEATURE_REGISTRY: Dict[str, Any] = {}

def register_features():
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
    }
    FEATURE_REGISTRY["log_parser"] = log_parser

# --- Feature Groupings (Reordered for UX) ---
FEATURE_GROUPS = {
    "Issues & Tasks": [
        ("📝 Create a new issue", "create_issue"),
        ("✏️ Update an existing issue", "update_issue"),
        ("🔁 Bulk operations", "bulk_operations"),
        ("📋 Get task (issue)", "get_task"),
    ],
    "Boards & Sprints": [
        ("📋 Sprint and board management", "sprint_board_management"),
    ],
    "Analytics & Reporting": [
        ("📊 Advanced metrics and reporting", "advanced_metrics"),
        ("👤 User and team analytics", "user_team_analytics"),
        ("⏱️ Time tracking and worklogs", "time_tracking_worklogs"),
        ("📈 Gather metrics for a user", "gather_metrics"),
        ("🗂️ Summarize tickets", "summarize_tickets"),
    ],
    "Integrations & Docs": [
        ("🔗 Integration with other tools", "integration_tools"),
        ("📄 Automated documentation", "automated_documentation"),
    ],
    "Jira Connection & Users": [
        ("🧪 Test connection to Jira", "test_connection"),
        ("👥 Output all users", "output_all_users"),
        ("🧑‍💻 Get user by accountId/email", "get_user"),
        ("🔍 Search users", "search_users"),
        ("🔎 Search users by displayname and email", "search_users_by_displayname_email"),
        ("🏷️ Get user property", "get_user_property"),
        ("🙋 Get current user (myself)", "get_current_user"),
        ("⚙️ Get mypreferences", "get_mypreferences"),
    ],
    "Logs & Diagnostics": [
        ("🔍 Search logs for points of interest", "log_parser"),
    ],
    "Preferences": [
        ("⚙️ Get mypreferences", "get_mypreferences"),
    ],
    "Exit": [
        ("🚪 Exit", "exit"),
    ],
}

def feature_menu():
    group_names = list(FEATURE_GROUPS.keys())
    while True:
        group = questionary.select(
            "Select a feature group:",
            choices=group_names,
            style=questionary.Style([
                ("selected", "fg:#22bb22 bold"),  # Jungle green
                ("pointer", "fg:#ffcc00 bold"),   # Yellow
            ])
        ).ask()
        contextual_log('info', f"User selected feature group: {group}", operation="user_prompt", status="answered", params={"group": group}, extra={"feature": "cli"})
        if group == "Exit":
            return "exit"
        features = FEATURE_GROUPS[group]
        # Add 'Return to previous menu' option to all submenus except Exit
        submenu_choices = [{"name": name, "value": value} for name, value in features]
        submenu_choices.append({"name": "⬅️ Return to previous menu", "value": "return_to_main_menu"})
        feature = questionary.select(
            f"Select a feature from '{group}':",
            choices=submenu_choices,
            style=questionary.Style([
                ("selected", "fg:#22bb22 bold"),
                ("pointer", "fg:#ffcc00 bold"),
            ])
        ).ask()
        contextual_log('info', f"User selected feature: {feature}", operation="user_prompt", status="answered", params={"feature": feature}, extra={"feature": "cli"})
        if feature == "return_to_main_menu":
            continue  # Go back to group selection
        return feature

# --- Main loop: persistently return to main menu ---
def main() -> None:
    try:
        banner = pyfiglet.figlet_format("JIRASSIC PACK", font="slant")
        print(JUNGLE_GREEN + banner + RESET)
        print(JUNGLE_GREEN + JIRASSIC_ASCII + RESET)
        print(WARNING_YELLOW + BANNER_ALT_TEXT + RESET)
        print(DANGER_RED + "\nROOOAAARRR! 🦖\n" + RESET)
        print(f"[Banner: {BANNER_ALT_TEXT}]")
        contextual_log('info', "🦖 Jirassic Pack CLI started.", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
        config_path = None
        log_level = LOG_LEVEL
        if len(sys.argv) > 1:
            for arg in sys.argv:
                if arg.startswith('--log-level='):
                    log_level = arg.split('=')[-1].upper()
                    logger.setLevel(getattr(logging, log_level, logging.INFO))
        if len(sys.argv) > 1 and sys.argv[1].startswith('--config'):
            config_path = sys.argv[1].split('=')[-1] if '=' in sys.argv[1] else sys.argv[2]
        config = ConfigLoader(config_path)
        jira_conf = config.get_jira_config()
        options = config.get_options()
        features = getattr(config, 'config', {}).get('features')
        feature = getattr(config, 'config', {}).get('feature')
        # Print loaded Jira config (redacted token)
        def redact_token(token):
            if not token or len(token) < 7:
                return '***'
            return token[:3] + '*' * (len(token)-6) + token[-3:]
        print(WARNING_YELLOW + f"Loaded Jira config: URL={jira_conf['url']}, Email={jira_conf['email']}, Token={redact_token(jira_conf['api_token'])}" + RESET)
        contextual_log('info', f"🦖 Loaded config: {config_path or 'default'} | Jira config: {redact_sensitive(jira_conf)} | Options: {redact_sensitive(options)}", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
        # Prompt for Jira credentials (shared by all features)
        if not jira_conf['url']:
            jira_conf['url'] = questionary.text("Jira URL:", default=os.environ.get('JIRA_URL', 'https://your-domain.atlassian.net')).ask()
            contextual_log('info', "User prompted for Jira URL", operation="user_prompt", status="answered", params={"prompt": "Jira URL"}, extra={"feature": "cli"})
        if not jira_conf['email']:
            jira_conf['email'] = questionary.text("Jira Email:", default=os.environ.get('JIRA_EMAIL', '')).ask()
            contextual_log('info', "User prompted for Jira Email", operation="user_prompt", status="answered", params={"prompt": "Jira Email"}, extra={"feature": "cli"})
        if not jira_conf['api_token']:
            jira_conf['api_token'] = questionary.password("Jira API Token:").ask()
            contextual_log('info', "User prompted for Jira API Token", operation="user_prompt", status="answered", params={"prompt": "Jira API Token"}, extra={"feature": "cli"})
        with spinner("Connecting to Jira..."):
            contextual_log('info', f"🦖 Connecting to Jira at {jira_conf['url']} as {jira_conf['email']}", extra={"feature": "cli", "user": jira_conf['email'], "batch": None, "suffix": None})
            jira = JiraClient(jira_conf['url'], jira_conf['email'], jira_conf['api_token'])
        register_features()
        # Batch mode: run each feature with merged options
        if features:
            global_options = config.get_options()
            correlation_id = str(uuid.uuid4())
            contextual_log('info', f"🦖 Batch mode: {len(features)} features queued. Correlation ID: {correlation_id}", extra={"feature": "cli", "user": None, "batch": None, "suffix": None, "correlation_id": correlation_id})
            for i, feat in enumerate(progress_bar(features, desc="Batch Processing")):
                name = feat.get('name')
                feat_options = feat.get('options', {})
                merged_options = {**global_options, **feat_options}
                unique_suffix = f"_{int(time.time())}_{i}"
                merged_options['unique_suffix'] = unique_suffix
                merged_options['correlation_id'] = correlation_id
                print(f"\n{WARNING_YELLOW}--- Running feature {i+1}/{len(features)}: {name} ---{RESET}")
                contextual_log('info', f"🦖 Running feature: {name} | Options: {redact_sensitive(merged_options)} | Batch index: {i} | Suffix: {unique_suffix} | Correlation ID: {correlation_id}", extra={"feature": name, "user": None, "batch": i, "suffix": unique_suffix, "correlation_id": correlation_id})
                run_feature(name, jira, merged_options, user_email=jira_conf.get('email'), batch_index=i, unique_suffix=unique_suffix)
            contextual_log('info', "🦖 Batch run complete!", extra={"feature": "cli", "user": None, "batch": None, "suffix": None, "correlation_id": correlation_id})
            contextual_log('info', "🦖 Welcome to Jurassic Park.", extra={"feature": "cli", "user": jira_conf.get('email'), "batch": None, "suffix": None, "correlation_id": correlation_id})
            info("🦖 Welcome to Jurassic Park.")
            return
        # Single feature mode
        if feature:
            contextual_log('info', f"🦖 Running feature: {feature}", extra={"feature": feature, "user": jira_conf.get('email'), "batch": None, "suffix": None})
            contextual_log('info', f"🦖 Running feature: {feature} | Options: {redact_sensitive(options)} | User: {jira_conf.get('email')}", extra={"feature": feature, "user": jira_conf.get('email'), "batch": None, "suffix": None})
            run_feature(feature, jira, options, user_email=jira_conf.get('email'))
            return
        # Interactive mode: persistent main menu loop
        while True:
            print(f"\n{WARNING_YELLOW}{Style.BRIGHT}Select a feature to run:{RESET}")
            action = feature_menu()
            if action == "exit":
                print(f"{JUNGLE_GREEN}Goodbye!{RESET}")
                contextual_log('info', "🦖 User exited from main menu.", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
                sys.exit(0)
            contextual_log('info', f"🦖 Running feature: {action} | Options: {redact_sensitive(options)} | User: {jira_conf.get('email')}", extra={"feature": action, "user": jira_conf.get('email'), "batch": None, "suffix": None})
            run_feature(action, jira, options, user_email=jira_conf.get('email'))
    except KeyboardInterrupt:
        print(f"\n{DANGER_RED}🦖 Graceful exit: Goodbye from Jirassic Pack!{RESET}")
        contextual_log('warning', "🦖 Graceful exit via KeyboardInterrupt.", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
        sys.exit(0)
    except Exception as e:
        contextual_log('exception', f"🦖 Unhandled exception in main: {e}", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
        error(f"🦖 Unhandled exception in main: {e}", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
        raise

def run_feature(feature: str, jira: JiraClient, options: dict, user_email: str = None, batch_index: int = None, unique_suffix: str = None) -> None:
    menu_to_key = {
        "🧪 Test connection to Jira": "test_connection",
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
    }
    key = menu_to_key.get(feature, feature)
    context = f"User: {user_email} | Batch: {batch_index} | Suffix: {unique_suffix}" if user_email or batch_index or unique_suffix else ""
    feature_tag = f"[{key}]"
    contextual_log('info', f"[DEBUG] run_feature: key={repr(key)}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
    if key == "test_connection":
        test_connection(jira, options, context)
        return
    if key == "output_all_users":
        contextual_log('info', f"{feature_tag} Outputting all users. Options: {redact_sensitive(options)} {context}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        output_all_users(jira, options, options.get('unique_suffix', ''))
        return
    # Inline handlers for user features
    if key == "get_user":
        try:
            account_id = questionary.text("Account ID (leave blank if not used):").ask()
            email = questionary.text("Email (leave blank if not used):").ask()
            username = questionary.text("Username (leave blank if not used):").ask()
            key_ = questionary.text("User key (leave blank if not used):").ask()
            result = jira.get_user(account_id=account_id or None, email=email or None, username=username or None, key=key_ or None)
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error fetching user: {e}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            contextual_log('error', f"[get_user] Exception: {e}", exc_info=True, extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        return
    if key == "search_users":
        try:
            query = questionary.text("Search query (name/email):").ask()
            contextual_log('info', f"[search_users] Query param: {query}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            result = jira.search_users(query=query)
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error searching users: {e}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            contextual_log('error', f"[search_users] Exception: {e}", exc_info=True, extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        return
    if key == "search_users_by_displayname_email":
        try:
            displayname = questionary.text("Display name (leave blank if not used):").ask()
            email = questionary.text("Email (leave blank if not used):").ask()
            params = {}
            if displayname:
                params['query'] = displayname
            if email:
                params['username'] = email
            contextual_log('info', f"[search_users_by_displayname_email] Params: {params}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            result = jira.get('users/search', params=params)
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error searching users: {e}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            contextual_log('error', f"[search_users_by_displayname_email] Exception: {e}", exc_info=True, extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        return
    if key == "get_user_property":
        try:
            account_id = questionary.text("Account ID:").ask()
            property_key = questionary.text("Property key:").ask()
            result = jira.get_user_property(account_id, property_key)
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error fetching user property: {e}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            contextual_log('error', f"[get_user_property] Exception: {e}", exc_info=True, extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        return
    if key == "get_task":
        try:
            issue_id_or_key = questionary.text("Issue ID or Key:").ask()
            result = jira.get_task(issue_id_or_key)
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error fetching task: {e}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            contextual_log('error', f"[get_task] Exception: {e}", exc_info=True, extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        return
    if key == "get_mypreferences":
        try:
            result = jira.get_mypreferences()
            pretty_print_result(result)
        except Exception as e:
            # Check for HTTP error code if available
            msg = str(e)
            if ("400" in msg or "404" in msg or "Bad Request" in msg or "not found" in msg.lower()):
                error_msg = f"🦖 The 'mypreferences' endpoint is not supported on your Jira instance. (Jira Cloud does not support this endpoint.)"
                print(DANGER_RED + error_msg + RESET)
                contextual_log('error', f"[get_mypreferences] {error_msg} Exception: {e}", exc_info=True, extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            else:
                error(f"🦖 Error fetching mypreferences: {e}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
                contextual_log('error', f"[get_mypreferences] Exception: {e}", exc_info=True, extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        return
    if key == "get_current_user":
        try:
            result = jira.get_current_user()
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error fetching current user: {e}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            contextual_log('error', f"[get_current_user] Exception: {e}", exc_info=True, extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        return
    # Only now check for FEATURE_REGISTRY
    if key not in FEATURE_REGISTRY:
        error(f"{feature_tag} Unknown feature: {feature}", extra={"feature": feature, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        contextual_log('error', f"{feature_tag} Unknown feature: {feature}", exc_info=True, extra={"feature": feature, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        return
    contextual_log('info', f"{feature_tag} Dispatching feature: {key} | Options: {redact_sensitive(options)} {context}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
    # --- Refactored: Parameter gathering and validation before spinner ---
    prompt_func_name = f"prompt_{key}_options"
    prompt_func = None
    # Try to get the prompt function from the feature module
    feature_module = FEATURE_REGISTRY[key]
    if hasattr(feature_module, prompt_func_name):
        prompt_func = getattr(feature_module, prompt_func_name)
    else:
        # Try to import from the feature module if it's a function
        try:
            import importlib
            mod = importlib.import_module(f"jirassicpack.features.{key}")
            prompt_func = getattr(mod, prompt_func_name, None)
        except Exception:
            prompt_func = None
    if prompt_func:
        # Pass jira to prompt_func if it accepts it
        sig = inspect.signature(prompt_func)
        if 'jira' in sig.parameters:
            params = prompt_func(options, jira=jira)
        else:
            params = prompt_func(options)
        if not params:
            contextual_log('info', f"{feature_tag} Feature '{key}' cancelled or missing parameters.", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            return
    else:
        params = options
    # Now call the feature handler (which should only perform the operation, with spinner inside if needed)
    start_time = time.time()
    contextual_log('info', f"Feature '{key}' execution started.", operation="feature_start", params=options, extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
    FEATURE_REGISTRY[key](jira, params, user_email=user_email, batch_index=batch_index, unique_suffix=unique_suffix)
    duration = int((time.time() - start_time) * 1000)
    contextual_log('info', f"Feature '{key}' execution finished.", operation="feature_end", status="success", duration_ms=duration, params=options, extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})
    contextual_log('info', f"{feature_tag} Feature '{key}' complete. {context}", extra={"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix})

def test_connection(jira: JiraClient, options: dict = None, context: str = "") -> None:
    with spinner("Testing Jira connection..."):
        try:
            # Log parameters
            contextual_log('info', f"🦖 [test_connection] Parameters: url={jira.base_url}, email={jira.auth[0]}", extra={"feature": "test_connection", "user": jira.auth[0], "batch": None, "suffix": None})
            # Log full request details
            endpoint = 'myself'
            headers = jira.headers
            params = None
            contextual_log('info', f"🦖 [test_connection] Request: endpoint={endpoint}, headers={headers}, params={params}", extra={"feature": "test_connection", "user": jira.auth[0], "batch": None, "suffix": None})
            contextual_log('info', f"🦖 [test_connection] Starting Jira connection test. {context}", extra={"feature": "test_connection", "user": None, "batch": None, "suffix": None})
            user = jira.get(endpoint)
            contextual_log('info', f"🦖 [test_connection] Response: {user}", extra={"feature": "test_connection", "user": jira.auth[0], "batch": None, "suffix": None})
            contextual_log('info', f"🦖 [test_connection] Jira connection successful. User: {user} {context}", extra={"feature": "test_connection", "user": user.get('displayName', user.get('name', 'Unknown')), "batch": None, "suffix": None})
            print(f"{JUNGLE_GREEN}🦖 Connection successful! Logged in as: {user.get('displayName', user.get('name', 'Unknown'))}{RESET}")
            contextual_log('info', "🦖 [test_connection] Welcome to Jurassic Park.", extra={"feature": "cli", "user": user.get('email'), "batch": None, "suffix": None})
            info("🦖 Welcome to Jurassic Park.")
        except Exception as e:
            contextual_log('error', f"🦖 [test_connection] Failed to connect to Jira: {e} {context}", exc_info=True, extra={"feature": "test_connection", "user": None, "batch": None, "suffix": None})
            error(f"🦖 Failed to connect to Jira: {e}", extra={"feature": "test_connection", "user": None, "batch": None, "suffix": None})

def output_all_users(jira: JiraClient, options: dict, unique_suffix: str = "") -> None:
    """Output all users in the Jira instance to a Markdown file."""
    output_dir = options.get('output_dir', 'output')
    ensure_output_dir(output_dir)
    with spinner("Fetching users from Jira..."):
        try:
            users = jira.get('users/search', params={'maxResults': 1000})
            filename = f"{output_dir}/jira_users{unique_suffix}.md"
            try:
                with open(filename, 'w') as f:
                    f.write("# Jira Users\n\n")
                    for user in users:
                        f.write(f"- {user.get('displayName', user.get('name', 'Unknown'))} ({user.get('emailAddress', 'N/A')})\n")
                print(f"{JUNGLE_GREEN}🦖 User list written to {filename}{RESET}")
                contextual_log('info', "🦖 Objects in mirror are closer than they appear.", extra={"feature": "output_all_users", "user": None, "batch": None, "suffix": unique_suffix})
                info("🦖 Objects in mirror are closer than they appear.")
                contextual_log('info', f"Writing user list to {filename}", operation="output_write", output_file=filename, status="success", extra={"feature": "output_all_users", "user": None, "batch": None, "suffix": unique_suffix})
            except Exception as file_err:
                error(f"🦖 Failed to write user list to file: {file_err}", extra={"feature": "output_all_users", "user": None, "batch": None, "suffix": unique_suffix})
                contextual_log('error', f"[output_all_users] File write error: {file_err}", exc_info=True, extra={"feature": "output_all_users", "user": None, "batch": None, "suffix": unique_suffix})
        except Exception as e:
            error(f"🦖 Failed to fetch users: {e}", extra={"feature": "output_all_users", "user": None, "batch": None, "suffix": unique_suffix})
            contextual_log('error', f"[output_all_users] Exception: {e}", exc_info=True, extra={"feature": "output_all_users", "user": None, "batch": None, "suffix": unique_suffix})

# --- Section Header with ASCII Art ---
def print_section_header(title: str, feature_key: str = None):
    """
    Print a section header with per-feature ASCII art and color theme.
    """
    color = FEATURE_COLORS.get(feature_key, EARTH_BROWN)
    art = FEATURE_ASCII_ART.get(feature_key, JIRASSIC_ASCII)
    header = pyfiglet.figlet_format(title, font="mini")
    print(color + art + RESET)
    print(color + header + RESET)
    print(f"[Section: {title}]")  # For screen readers

# --- Celebratory Output ---
def celebrate_success():
    print(JUNGLE_GREEN + "🎉 Success! 🎉" + RESET)

# --- Batch Summary Table ---
def print_batch_summary(results):
    print(WARNING_YELLOW + "\n🦖 Batch Summary:" + RESET)
    print("Feature         | Status")
    print("----------------|--------")
    for name, status in results:
        color = JUNGLE_GREEN if status == "Success" else DANGER_RED
        print(f"{name:<15} | {color}{status}{RESET}")

# --- Retry/Skip on Network Failure ---
def retry_or_skip(action_desc, func, *args, **kwargs):
    while True:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(DANGER_RED + f"🦖 Error during {action_desc}: {e}" + RESET)
            choice = questionary.select(
                f"🦖 {action_desc} failed. What would you like to do?",
                choices=["Retry", "Skip", "Exit"],
                style=questionary.Style([
                    ("selected", "fg:#ffcc00 bold"),  # Yellow
                    ("pointer", "fg:#22bb22 bold"),   # Jungle green
                ])
            ).ask()
            if choice == "Retry":
                continue
            elif choice == "Skip":
                return None
            else:
                sys.exit(1)

# --- Ensure all output is screen reader friendly after banner ---
# (No excessive ASCII art, clear text for progress/results, alt text for banners/headers)

# Add a utility: def themed_log(msg, emoji, **kwargs): logger.info(f"{emoji} {msg}", extra=kwargs)

def pretty_print_result(result):
    print("\n" + WARNING_YELLOW + json.dumps(result, indent=2) + RESET)

# --- Enhanced Logging Context ---
CLI_VERSION = "1.0.0"  # Update as needed
HOSTNAME = socket.gethostname()
PID = os.getpid()

def log_parser(*args, **kwargs):
    log_file = LOG_FILE
    if not os.path.exists(log_file):
        error(f"Log file '{log_file}' does not exist.")
        return
    # --- Prompt for search type ---
    search_types = [
        ("Feature start", r'operation.*feature_start'),
        ("Feature end", r'operation.*feature_end'),
        ("Errors", r'level.*error'),
        ("Output writes", r'operation.*output_write'),
        ("Warnings", r'level.*warning'),
        ("Custom search", None),
    ]
    choice = questionary.select(
        "What do you want to search for in the logs?",
        choices=[name for name, _ in search_types],
        style=questionary.Style([
            ("selected", "fg:#22bb22 bold"),
            ("pointer", "fg:#ffcc00 bold"),
        ])
    ).ask()
    pattern = None
    for name, pat in search_types:
        if name == choice:
            pattern = pat
            break
    if choice == "Custom search":
        pattern = questionary.text("Enter a regex or keyword to search for:").ask()
    if not pattern:
        error("No search pattern provided.")
        return
    # --- Extract all unique features from the log file ---
    feature_choices = ["(all)"]
    try:
        features_set = set()
        with open(log_file, 'r') as f:
            for line in f:
                try:
                    if LOG_FORMAT == 'json':
                        data = json.loads(line)
                        feat = data.get('feature')
                        if feat:
                            features_set.add(str(feat))
                    else:
                        # crude parse for plain text logs
                        m = re.search(r'feature[": ]+([\w_]+)', line)
                        if m:
                            features_set.add(m.group(1))
                except Exception:
                    continue
        feature_choices += sorted(features_set)
    except Exception:
        pass
    # --- Prompt for feature filter ---
    if len(feature_choices) > 1:
        feature_filter = questionary.select(
            "Filter by feature:",
            choices=feature_choices,
            default="(all)",
            style=questionary.Style([
                ("selected", "fg:#22bb22 bold"),
                ("pointer", "fg:#ffcc00 bold"),
            ])
        ).ask()
        if feature_filter == "(all)":
            feature_filter = ""
    else:
        feature_filter = questionary.text("Filter by feature (leave blank for all):").ask()
    # --- User filter ---
    user_filter = questionary.text("Filter by user (leave blank for all):").ask()
    # Log level filter
    log_levels = ["", "info", "warning", "error", "debug"]
    log_level_filter = questionary.select(
        "Filter by log level:",
        choices=["(all)"] + log_levels[1:],
        default="(all)",
        style=questionary.Style([
            ("selected", "fg:#22bb22 bold"),
            ("pointer", "fg:#ffcc00 bold"),
        ])
    ).ask()
    if log_level_filter == "(all)":
        log_level_filter = ""
    # Date range filter
    start_date = questionary.text("Start date (YYYY-MM-DD, leave blank for earliest):").ask()
    end_date = questionary.text("End date (YYYY-MM-DD, leave blank for latest):").ask()
    def parse_date(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except Exception:
            return None
    start_dt = parse_date(start_date) if start_date else None
    end_dt = parse_date(end_date) if end_date else None
    # --- Search the log file ---
    matches = []
    features = set()
    levels = {}
    min_time = None
    max_time = None
    def colorize(level, msg):
        if level == "error":
            return f"\033[91m{msg}\033[0m"  # Red
        elif level == "warning":
            return f"\033[93m{msg}\033[0m"  # Yellow
        elif level == "info":
            return f"\033[92m{msg}\033[0m"  # Green
        elif level == "debug":
            return f"\033[96m{msg}\033[0m"  # Cyan
        else:
            return msg
    with open(log_file, 'r') as f:
        for line in f:
            try:
                if LOG_FORMAT == 'json':
                    data = json.loads(line)
                    # --- Filtering logic ---
                    if not re.search(pattern, json.dumps(data)):
                        continue
                    if feature_filter and str(data.get("feature", "")).lower() != feature_filter.lower():
                        continue
                    if user_filter and str(data.get("user", "")).lower() != user_filter.lower():
                        continue
                    if log_level_filter and str(data.get("level", "")).lower() != log_level_filter.lower():
                        continue
                    # Date/time filtering
                    ts = data.get("asctime") or data.get("timestamp")
                    dt = None
                    if ts:
                        try:
                            dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            pass
                    if start_dt and dt and dt < start_dt:
                        continue
                    if end_dt and dt and dt > end_dt:
                        continue
                    # Track stats
                    features.add(data.get("feature", ""))
                    lvl = str(data.get("level", "")).lower()
                    levels[lvl] = levels.get(lvl, 0) + 1
                    if dt:
                        if not min_time or dt < min_time:
                            min_time = dt
                        if not max_time or dt > max_time:
                            max_time = dt
                    matches.append(data)
                else:
                    if not re.search(pattern, line):
                        continue
                    if feature_filter and feature_filter.lower() not in line.lower():
                        continue
                    if user_filter and user_filter.lower() not in line.lower():
                        continue
                    if log_level_filter and log_level_filter.lower() not in line.lower():
                        continue
                    # Date filtering for plain text: skip (unless you want to parse)
                    matches.append(line.strip())
            except Exception:
                continue
    if not matches:
        info(f"No log entries found for: {choice}")
        return
    # --- Summary statistics ---
    info(f"Found {len(matches)} log entries for: {choice}")
    if LOG_FORMAT == 'json':
        print("\nSummary:")
        print("Level     | Count")
        print("----------|------")
        for lvl, count in levels.items():
            print(f"{lvl:<9} | {count}")
        print(f"Unique features: {len(features)}: {', '.join(sorted(f for f in features if f))}")
        if min_time and max_time:
            print(f"Time range: {min_time} to {max_time}")
    # --- Pagination ---
    page_size = 20
    total = len(matches)
    page = 0
    while True:
        start = page * page_size
        end = min(start + page_size, total)
        print(f"\nShowing results {start+1}-{end} of {total}:")
        for entry in matches[start:end]:
            if isinstance(entry, dict):
                lvl = str(entry.get("level", "")).lower()
                msg = entry.get("message") or entry.get("msg") or json.dumps(entry)
                print(colorize(lvl, f"[{lvl.upper()}] {msg}"))
                # Optionally pretty-print the whole entry
                print(json.dumps(entry, indent=2))
            else:
                print(entry)
        if end == total:
            break
        nav = questionary.select(
            f"Page {page+1}/{(total-1)//page_size+1}. Next/Prev?",
            choices=["Next", "Prev", "Exit"],
            default="Next",
            style=questionary.Style([
                ("selected", "fg:#22bb22 bold"),
                ("pointer", "fg:#ffcc00 bold"),
            ])
        ).ask()
        if nav == "Next":
            page += 1
        elif nav == "Prev" and page > 0:
            page -= 1
        else:
            break
    # --- Export option ---
    export = questionary.confirm("Export these results to a file?").ask()
    if export:
        export_fmt = questionary.select(
            "Export format:",
            choices=["JSON", "Text"],
            default="JSON",
            style=questionary.Style([
                ("selected", "fg:#22bb22 bold"),
                ("pointer", "fg:#ffcc00 bold"),
            ])
        ).ask()
        fname = questionary.text("Enter filename to export to:", default="filtered_logs.json" if export_fmt=="JSON" else "filtered_logs.txt").ask()
        with open(fname, 'w') as f:
            if export_fmt == "JSON":
                json.dump(matches, f, indent=2, default=str)
            else:
                for entry in matches:
                    if isinstance(entry, dict):
                        f.write(json.dumps(entry) + "\n")
                    else:
                        f.write(str(entry) + "\n")
        info(f"Exported {len(matches)} log entries to {fname}")

# --- Enhanced get_option with validation for all user-typed input prompts ---
def get_validated_input(prompt, validate_fn=None, error_msg=None, default=None, regex=None, date_format=None, min_date=None, max_date=None):
    retry_count = 0
    while True:
        value = questionary.text(prompt, default=default or '').ask()
        contextual_log('info', f"User prompted for validated input: {prompt}", operation="user_prompt", status="answered", params={"prompt": prompt}, retry_count=retry_count, extra={"feature": "get_validated_input"})
        # Regex validation
        if regex:
            if not re.match(regex, value or ""):
                contextual_log('warning', f"Input failed regex validation: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt, "regex": regex, "value": value}, retry_count=retry_count, extra={"feature": "get_validated_input"})
                print(f"\033[91m{error_msg or 'Input does not match required format.'}\033[0m")
                retry_count += 1
                continue
        # Date/time validation
        if date_format:
            try:
                dt = datetime.strptime(value, date_format)
                if min_date and dt < min_date:
                    contextual_log('warning', f"Input date before min_date: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt, "date_format": date_format, "value": value, "min_date": min_date}, retry_count=retry_count, extra={"feature": "get_validated_input"})
                    print(f"\033[91mDate/time must be after {min_date.strftime(date_format)}.\033[0m")
                    retry_count += 1
                    continue
                if max_date and dt > max_date:
                    contextual_log('warning', f"Input date after max_date: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt, "date_format": date_format, "value": value, "max_date": max_date}, retry_count=retry_count, extra={"feature": "get_validated_input"})
                    print(f"\033[91mDate/time must be before {max_date.strftime(date_format)}.\033[0m")
                    retry_count += 1
                    continue
            except Exception:
                contextual_log('warning', f"Input failed date format validation: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt, "date_format": date_format, "value": value}, retry_count=retry_count, extra={"feature": "get_validated_input"})
                print(f"\033[91m{error_msg or f'Input must match date format {date_format}.'}\033[0m")
                retry_count += 1
                continue
        # Custom validation function
        if validate_fn:
            if not validate_fn(value):
                contextual_log('warning', f"Input failed custom validation: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt, "value": value}, retry_count=retry_count, extra={"feature": "get_validated_input"})
                print(f"\033[91m{error_msg or 'Invalid input.'}\033[0m")
                retry_count += 1
                continue
        # Required check
        if not value or not value.strip():
            contextual_log('warning', f"Input required but empty: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt}, retry_count=retry_count, extra={"feature": "get_validated_input"})
            print("\033[91mInput is required.\033[0m")
            retry_count += 1
            continue
        contextual_log('info', f"Input validated successfully: {prompt}", operation="input_validation", status="success", params={"prompt": prompt, "value": value}, retry_count=retry_count, extra={"feature": "get_validated_input"})
        return value

# --- Jira-aware input helpers ---
SELECT_MENU_STYLE = questionary.Style([
    ("selected", "fg:#22bb22 bold"),  # Jungle green
    ("pointer", "fg:#ffcc00 bold"),   # Yellow
])

def get_valid_project_key(jira):
    try:
        projects = jira.get('project')
        project_keys = [p['key'] for p in projects]
        return questionary.select(
            "Select a Jira Project:",
            choices=project_keys,
            style=SELECT_MENU_STYLE
        ).ask()
    except Exception:
        return get_validated_input('Enter Jira Project Key:', regex=r'^[A-Z][A-Z0-9]+$', error_msg='Invalid project key format.')

def get_valid_issue_type(jira, project_key):
    try:
        meta = jira.get(f'issue/createmeta?projectKeys={project_key}')
        types = meta['projects'][0]['issuetypes']
        return questionary.select(
            "Select Issue Type:",
            choices=[t['name'] for t in types],
            style=SELECT_MENU_STYLE
        ).ask()
    except Exception:
        return get_validated_input('Enter Issue Type:', error_msg='Invalid issue type.')

def get_valid_user(jira):
    try:
        users = jira.search_users("")
        user_choices = [f"{u.get('displayName','?')} <{u.get('emailAddress','?')}>" for u in users]
        return questionary.select(
            "Select User:",
            choices=user_choices,
            style=SELECT_MENU_STYLE
        ).ask()
    except Exception:
        return get_validated_input('Enter user email or username:', regex=r'^[^@\s]+@[^@\s]+\.[^@\s]+$', error_msg='Invalid email format.')

def get_valid_field(jira, project_key, issue_type):
    try:
        fields = jira.get('field')
        # Optionally filter by project/issue_type if needed
        field_names = [f['name'] for f in fields if f.get('name')]
        return questionary.select(
            "Select Field:",
            choices=field_names,
            style=SELECT_MENU_STYLE
        ).ask()
    except Exception:
        return get_validated_input('Enter field name:', error_msg='Invalid field name.')

def get_valid_transition(jira, issue_key):
    try:
        transitions = jira.get(f'issue/{issue_key}/transitions')
        choices = [t['name'] for t in transitions.get('transitions',[])]
        return questionary.select(
            "Select Transition:",
            choices=choices,
            style=SELECT_MENU_STYLE
        ).ask()
    except Exception:
        return get_validated_input('Enter transition name:', error_msg='Invalid transition.')

if __name__ == "__main__":
    main() 