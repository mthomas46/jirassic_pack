import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
from jirassicpack.config import ConfigLoader
from jirassicpack.jira_client import JiraClient
import questionary
from typing import Any, Dict
from jirassicpack.utils.io import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, spinner, progress_bar, error, info
from jirassicpack.utils.logging import contextual_log, redact_sensitive
from jirassicpack.utils.jira import select_jira_user, get_valid_project_key, get_valid_issue_type, get_valid_user, get_valid_field, get_valid_transition, select_account_id, select_property_key, search_issues
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
    "Test Connection": [
        ("🧪 Test connection to Jira", "test_connection"),
    ],
    "Issues & Tasks": [
        ("📝 Create a new issue", "create_issue"),
        ("✏️ Update an existing issue", "update_issue"),
        ("🔁 Bulk operations", "bulk_operations"),
        ("📋 Get task (issue)", "get_task"),
        ("🔎 Search issues", "search_issues"),
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
        ("👥 Output all users", "output_all_users"),
        ("🏷️ Output all user property keys", "output_all_user_property_keys"),
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
        contextual_log('info', f"🦖 [CLI] User selected feature group: {group}", operation="user_prompt", status="answered", params={"group": group}, extra={"feature": "cli"})
        if not group or group not in FEATURE_GROUPS:
            continue  # Defensive: skip invalid or None group
        if group == "Exit":
            yield "exit", None
            return
        features = FEATURE_GROUPS[group]
        while True:
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
            contextual_log('info', f"🦖 [CLI] User selected feature: {feature}", operation="user_prompt", status="answered", params={"feature": feature}, extra={"feature": "cli"})
            if feature == "return_to_main_menu":
                break  # Go back to group selection
            yield feature, group

# --- Main loop: persistently return to main menu ---
def main() -> None:
    try:
        banner = pyfiglet.figlet_format("JIRASSIC PACK", font="slant")
        print(JUNGLE_GREEN + banner + RESET)
        print(JUNGLE_GREEN + JIRASSIC_ASCII + RESET)
        print(WARNING_YELLOW + BANNER_ALT_TEXT + RESET)
        print(DANGER_RED + "\nROOOAAARRR! 🦖\n" + RESET)
        print(f"[Banner: {BANNER_ALT_TEXT}]")
        contextual_log('info', f"🦖 [CLI] Jirassic Pack CLI started.", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
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
        contextual_log('info', f"🦖 [CLI] Loaded config from {config_path or 'default'} for user {jira_conf.get('email')}", extra={"feature": "cli", "user": jira_conf.get('email'), "batch": None, "suffix": None})
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
            contextual_log('info', f"🦖 [CLI] Connecting to Jira at {jira_conf['url']} as {jira_conf['email']}", extra={"feature": "cli", "user": jira_conf['email'], "batch": None, "suffix": None})
            jira = JiraClient(jira_conf['url'], jira_conf['email'], jira_conf['api_token'])
        register_features()
        # Batch mode: run each feature with merged options
        if features:
            global_options = config.get_options()
            correlation_id = str(uuid.uuid4())
            contextual_log('info', f"🦖 [CLI] Batch mode: {len(features)} features queued. Correlation ID: {correlation_id}", extra={"feature": "cli", "user": None, "batch": None, "suffix": None, "correlation_id": correlation_id})
            for i, feat in enumerate(progress_bar(features, desc="Batch Processing")):
                name = feat.get('name')
                feat_options = feat.get('options', {})
                merged_options = {**global_options, **feat_options}
                unique_suffix = f"_{int(time.time())}_{i}"
                merged_options['unique_suffix'] = unique_suffix
                merged_options['correlation_id'] = correlation_id
                print(f"\n{WARNING_YELLOW}--- Running feature {i+1}/{len(features)}: {name} ---{RESET}")
                contextual_log('info', f"🦖 [CLI] Running feature: {name} | Options: {redact_sensitive(merged_options)} | Batch index: {i} | Suffix: {unique_suffix} | Correlation ID: {correlation_id}", extra={"feature": name, "user": None, "batch": i, "suffix": unique_suffix, "correlation_id": correlation_id})
                run_feature(name, jira, merged_options, user_email=jira_conf.get('email'), batch_index=i, unique_suffix=unique_suffix)
            contextual_log('info', "🦖 [CLI] Batch run complete!", extra={"feature": "cli", "user": None, "batch": None, "suffix": None, "correlation_id": correlation_id})
            contextual_log('info', "🦖 [CLI] Welcome to Jurassic Park.", extra={"feature": "cli", "user": jira_conf.get('email'), "batch": None, "suffix": None, "correlation_id": correlation_id})
            info("🦖 Welcome to Jurassic Park.")
            return
        # Single feature mode
        if feature:
            contextual_log('info', f"🦖 [CLI] Running feature '{feature}' for user {jira_conf.get('email')}", extra={"feature": feature, "user": jira_conf.get('email'), "batch": None, "suffix": None})
            contextual_log('info', f"🦖 [CLI] Feature options: {redact_sensitive(options)}", extra={"feature": feature, "user": jira_conf.get('email'), "batch": None, "suffix": None})
            run_feature(feature, jira, options, user_email=jira_conf.get('email'))
            return
        # Interactive mode: persistent main menu loop
        while True:
            print(f"\n{WARNING_YELLOW}{Style.BRIGHT}Select a feature to run:{RESET}")
            for action, group in feature_menu():
                if action == "exit":
                    print(f"{JUNGLE_GREEN}Goodbye!{RESET}")
                    contextual_log('info', f"🦖 [CLI] User exited from main menu.", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
                    halt_cli("User exited from main menu.")
                contextual_log('info', f"🦖 [CLI] User selected feature '{action}' for user {jira_conf.get('email')}", extra={"feature": action, "user": jira_conf.get('email'), "batch": None, "suffix": None})
                run_feature(action, jira, options, user_email=jira_conf.get('email'))
    except KeyboardInterrupt:
        halt_cli("Graceful exit: Goodbye from Jirassic Pack!")
    except Exception as e:
        contextual_log('exception', f"🦖 [CLI] Unhandled exception: {e}", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
        error(f"🦖 Unhandled exception in main: {e}", extra={"feature": "cli", "user": None, "batch": None, "suffix": None})
        halt_cli(f"Unhandled exception: {e}")

def run_feature(feature: str, jira: JiraClient, options: dict, user_email: str = None, batch_index: int = None, unique_suffix: str = None) -> None:
    context = {"feature": feature, "user": user_email, "batch": batch_index, "suffix": unique_suffix}
    contextual_log('debug', f"[DEBUG] run_feature called. feature={feature}, user_email={user_email}, batch_index={batch_index}, unique_suffix={unique_suffix}, options={options}", extra=context)
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
        "🏷️ Output all user property keys": "output_all_user_property_keys",
        "🔎 Search issues": "search_issues",
    }
    key = menu_to_key.get(feature, feature)
    context = {"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix}
    feature_tag = f"[{key}]"
    contextual_log('info', f"🦖 [CLI] run_feature: key={repr(key)}", extra=context)
    if key == "test_connection":
        test_connection(jira, options, context)
        return
    if key == "output_all_users":
        contextual_log('info', f"{feature_tag} Outputting all users. Options: {redact_sensitive(options)} {context}", extra=context)
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
            search_email = questionary.confirm("Would you like to search for a user to fill in the email?", default=True).ask()
            if search_email:
                users = jira.search_users("")
                email_choices = [u.get('emailAddress') for u in users if u.get('emailAddress')]
                if email_choices:
                    picked = questionary.select("Select an email:", choices=email_choices + ["(Enter manually)"]).ask()
                    if picked == "(Enter manually)":
                        email = questionary.text("Enter email (leave blank if not used):").ask()
                    else:
                        email = picked
                else:
                    email = questionary.text("Enter email (leave blank if not used):").ask()
            else:
                email = questionary.text("Enter email (leave blank if not used):").ask()
            # Prompt for username and user key, but allow skipping
            username = questionary.text("Username (leave blank if not used):").ask()
            key_ = questionary.text("User key (leave blank if not used):").ask()
            result = jira.get_user(account_id=account_id or None, email=email or None, username=username or None, key=key_ or None)
            if not result:
                info("Aborted: No user found with provided details.")
                return
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error fetching user: {e}", extra=context)
            contextual_log('error', f"🦖 [CLI] Error fetching user: {e}", exc_info=True, extra=context)
        return
    if key == "search_users":
        try:
            query = questionary.text("Search query (name/email):").ask()
            contextual_log('info', f"🦖 [CLI] User searched users with query: {query}", extra=context)
            result = jira.search_users(query=query)
            if not result:
                info("Aborted: No users found for query.")
                return
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error searching users: {e}", extra=context)
            contextual_log('error', f"🦖 [CLI] Error searching users: {e}", exc_info=True, extra=context)
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
            contextual_log('info', f"🦖 [CLI] User searched users by displayname and email with params: {params}", extra=context)
            result = jira.get('users/search', params=params)
            if not result:
                info("Aborted: No users found for provided display name/email.")
                return
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error searching users: {e}", extra=context)
            contextual_log('error', f"🦖 [CLI] Error searching users: {e}", exc_info=True, extra=context)
        return
    if key == "get_user_property":
        try:
            account_id = select_account_id(jira)
            property_key = select_property_key(jira, account_id)
            result = jira.get_user_property(account_id, property_key)
            if not result:
                info("Aborted: No property found for user.")
                return
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error fetching user property: {e}", extra=context)
            contextual_log('error', f"🦖 [CLI] Error fetching user property: {e}", exc_info=True, extra=context)
        return
    if key == "get_task":
        try:
            label, issue_obj = search_issues(jira)
            issue_key = issue_obj.get('key') if issue_obj else label
            if issue_key:
                info(f"Selected issue: {issue_key}")
            return
        except Exception as e:
            error(f"🦖 Error fetching task: {e}", extra=context)
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
                error_msg = f"🦖 The 'mypreferences' endpoint is not supported on your Jira instance. (Jira Cloud does not support this endpoint.)"
                print(DANGER_RED + error_msg + RESET)
                contextual_log('error', f"🦖 [CLI] {error_msg} Exception: {e}", exc_info=True, extra=context)
            else:
                error(f"🦖 Error fetching mypreferences: {e}", extra=context)
                contextual_log('error', f"🦖 [CLI] Exception: {e}", exc_info=True, extra=context)
        return
    if key == "get_current_user":
        try:
            result = jira.get_current_user()
            if not result:
                info("Aborted: No current user found.")
                return
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error fetching current user: {e}", extra=context)
            contextual_log('error', f"🦖 [CLI] Error fetching current user: {e}", exc_info=True, extra=context)
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
    contextual_log('debug', f"[DEBUG] Looking for prompt function: {prompt_func_name} in {feature_module}", extra=context)
    if hasattr(feature_module, prompt_func_name):
        prompt_func = getattr(feature_module, prompt_func_name)
        contextual_log('debug', f"[DEBUG] Found prompt function: {prompt_func_name} in module {feature_module}", extra=context)
    else:
        try:
            import importlib
            mod = importlib.import_module(f"jirassicpack.features.{key}")
            prompt_func = getattr(mod, prompt_func_name, None)
            contextual_log('debug', f"[DEBUG] Imported module jirassicpack.features.{key}, found prompt_func: {bool(prompt_func)}", extra=context)
        except Exception as e:
            contextual_log('debug', f"[DEBUG] Could not import prompt function for {key}: {e}", extra=context)
            prompt_func = None
    if prompt_func:
        import inspect
        sig = inspect.signature(prompt_func)
        contextual_log('debug', f"[DEBUG] prompt_func signature: {sig}", extra=context)
        if 'jira' in sig.parameters:
            contextual_log('debug', f"[DEBUG] Calling prompt_func with jira", extra=context)
            params = prompt_func(options, jira=jira)
        else:
            contextual_log('debug', f"[DEBUG] Calling prompt_func without jira", extra=context)
            params = prompt_func(options)
        contextual_log('debug', f"[DEBUG] prompt_func returned params: {params}", extra=context)
        if not params:
            contextual_log('info', f"🦖 [CLI] Feature '{key}' cancelled or missing parameters for user {user_email}", extra=context)
            return
    else:
        contextual_log('debug', f"[DEBUG] No prompt_func found for {key}, using options as params.", extra=context)
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
            headers = jira.headers
            params = None
            contextual_log('info', f"🦖 [CLI] [test_connection] Request: endpoint={endpoint}, headers=REDACTED, params={params}", extra=context)
            contextual_log('info', f"🦖 [CLI] [test_connection] Starting Jira connection test.", extra=context)
            user = jira.get(endpoint)
            contextual_log('info', f"🦖 [CLI] [test_connection] Response: {user}", extra=context)
            contextual_log('info', f"🦖 [CLI] [test_connection] Jira connection successful for user {user.get('displayName', user.get('name', 'Unknown'))}", extra=context)
            print(f"{JUNGLE_GREEN}🦖 Connection successful! Logged in as: {user.get('displayName', user.get('name', 'Unknown'))}{RESET}")
            contextual_log('info', "🦖 [CLI] Welcome to Jurassic Park.", extra=context)
            info("🦖 Welcome to Jurassic Park.")
        except Exception as e:
            contextual_log('error', f"🦖 [CLI] [test_connection] Failed to connect to Jira: {e}", exc_info=True, extra=context)
            error(f"🦖 Failed to connect to Jira: {e}", extra=context)

def output_all_users(jira: JiraClient, options: dict, unique_suffix: str = "") -> None:
    context = {"feature": "output_all_users", "user": None, "batch": None, "suffix": unique_suffix}
    output_dir = options.get('output_dir', 'output')
    ensure_output_dir(output_dir)
    with spinner("Fetching users from Jira..."):
        try:
            users = jira.get('users/search', params={'maxResults': 1000})
            if not users:
                info("Aborted: No users found or operation cancelled.")
                return
            filename = f"{output_dir}/jira_users{unique_suffix}.md"
            try:
                with open(filename, 'w') as f:
                    f.write("# Jira Users\n\n")
                    for user in users:
                        f.write(f"- {user.get('displayName', user.get('name', 'Unknown'))} ({user.get('emailAddress', 'N/A')})\n")
                print(f"{JUNGLE_GREEN}🦖 User list written to {filename}{RESET}")
                contextual_log('info', "🦖 Objects in mirror are closer than they appear.", extra=context)
                info("🦖 Objects in mirror are closer than they appear.")
                contextual_log('info', f"🦖 [CLI] Writing user list to {filename}", operation="output_write", output_file=filename, status="success", extra=context)
            except Exception as file_err:
                error(f"🦖 Failed to write user list to file: {file_err}", extra=context)
                contextual_log('error', f"🦖 [CLI] [output_all_users] File write error: {file_err}", exc_info=True, extra=context)
        except Exception as e:
            error(f"🦖 Failed to fetch users: {e}", extra=context)
            contextual_log('error', f"🦖 [CLI] [output_all_users] Exception: {e}", exc_info=True, extra=context)

def output_all_user_property_keys(jira: JiraClient, options: dict, unique_suffix: str = "") -> None:
    context = {"feature": "output_all_user_property_keys", "user": None, "batch": None, "suffix": unique_suffix}
    output_dir = options.get('output_dir', 'output')
    ensure_output_dir(output_dir)
    label, user_obj = select_jira_user(jira)
    if not user_obj or not user_obj.get('accountId'):
        info("Aborted: No user selected.")
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
            info("🦖 Objects in mirror are closer than they appear.")
            contextual_log('info', f"🦖 [CLI] Writing user property keys to {filename}", operation="output_write", output_file=filename, status="success", extra=context)
        except Exception as e:
            error(f"🦖 Failed to fetch user property keys: {e}", extra=context)
            contextual_log('error', f"🦖 [CLI] [output_all_user_property_keys] Exception: {e}", exc_info=True, extra=context)

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
        contextual_log('info', f"🦖 [CLI] User prompted for validated input: {prompt}", operation="user_prompt", status="answered", params={"prompt": prompt}, retry_count=retry_count, extra={"feature": "get_validated_input"})
        # Regex validation
        if regex:
            if not re.match(regex, value or ""):
                contextual_log('warning', f"🦖 [CLI] Input failed regex validation: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt, "regex": regex, "value": value}, retry_count=retry_count, extra={"feature": "get_validated_input"})
                print(f"\033[91m{error_msg or 'Input does not match required format.'}\033[0m")
                retry_count += 1
                continue
        # Date/time validation
        if date_format:
            try:
                dt = datetime.strptime(value, date_format)
                if min_date and dt < min_date:
                    contextual_log('warning', f"🦖 [CLI] Input date before min_date: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt, "date_format": date_format, "value": value, "min_date": min_date}, retry_count=retry_count, extra={"feature": "get_validated_input"})
                    print(f"\033[91mDate/time must be after {min_date.strftime(date_format)}.\033[0m")
                    retry_count += 1
                    continue
                if max_date and dt > max_date:
                    contextual_log('warning', f"🦖 [CLI] Input date after max_date: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt, "date_format": date_format, "value": value, "max_date": max_date}, retry_count=retry_count, extra={"feature": "get_validated_input"})
                    print(f"\033[91mDate/time must be before {max_date.strftime(date_format)}.\033[0m")
                    retry_count += 1
                    continue
            except Exception:
                contextual_log('warning', f"🦖 [CLI] Input failed date format validation: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt, "date_format": date_format, "value": value}, retry_count=retry_count, extra={"feature": "get_validated_input"})
                print(f"\033[91m{error_msg or f'Input must match date format {date_format}.'}\033[0m")
                retry_count += 1
                continue
        # Custom validation function
        if validate_fn:
            if not validate_fn(value):
                contextual_log('warning', f"🦖 [CLI] Input failed custom validation: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt, "value": value}, retry_count=retry_count, extra={"feature": "get_validated_input"})
                print(f"\033[91m{error_msg or 'Invalid input.'}\033[0m")
                retry_count += 1
                continue
        # Required check
        if not value or not value.strip():
            contextual_log('warning', f"🦖 [CLI] Input required but empty: {prompt}", operation="input_validation", status="failed", params={"prompt": prompt}, retry_count=retry_count, extra={"feature": "get_validated_input"})
            print("\033[91mInput is required.\033[0m")
            retry_count += 1
            continue
        contextual_log('info', f"🦖 [CLI] Input validated successfully: {prompt}", operation="input_validation", status="success", params={"prompt": prompt, "value": value}, retry_count=retry_count, extra={"feature": "get_validated_input"})
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

def select_account_id(jira):
    """
    Use the robust select_jira_user helper for user selection, returning the selected user's accountId.
    """
    label, user_obj = select_jira_user(jira)
    return user_obj.get('accountId') if user_obj else None

def select_property_key(jira, account_id):
    """
    Prompt the user to select a property key for the given accountId, or enter manually if none are found.
    """
    try:
        resp = jira.get('user/properties', params={'accountId': account_id})
        keys = resp.get('keys', [])
        if not keys:
            return questionary.text("Enter property key:").ask()
        choices = [k.get('key') for k in keys]
        choices.append("(Enter manually)")
        picked = questionary.select("Select a property key:", choices=choices).ask()
        if picked == "(Enter manually)":
            return questionary.text("Enter property key:").ask()
        return picked
    except Exception:
        return questionary.text("Enter property key:").ask()

def search_issues(jira):
    """
    Prompt the user to search for a Jira issue by key or summary and select from the list, or enter manually if not found. Caches issues per search term.
    """
    issue_cache = {}
    while True:
        search_term = questionary.text("Enter issue key or summary to search (leave blank if you don't know):").ask()
        if not search_term:
            action = questionary.select(
                "You didn't enter an issue key or summary. What would you like to do?",
                choices=["Search for an issue", "Enter issue key manually", "Abort"]
            ).ask()
            if action == "Enter issue key manually":
                return questionary.text("Enter issue key:").ask()
            elif action == "Abort":
                return None
            # else: fall through to search
            search_term = questionary.text("Enter search term for issues (summary or key):").ask()
            if not search_term:
                continue
        if search_term in issue_cache:
            issues = issue_cache[search_term]
        else:
            jql = f"summary ~ '{search_term}' OR key = '{search_term}'"
            try:
                issues = jira.search_issues(jql, fields=["key", "summary"], max_results=20)
                issue_cache[search_term] = issues
            except Exception as e:
                info(f"Error searching issues: {e}")
                continue
        if not issues:
            info("No issues found. Try again or leave blank to enter manually.")
            continue
        # Sort issues by key
        issues = sorted(issues, key=lambda i: i.get('key', ''))
        choices = [f"{i.get('key','?')}: {i.get('fields',{}).get('summary','?')}" for i in issues]
        choices.append("(Enter manually)")
        picked = questionary.select("Select an issue:", choices=choices).ask()
        if picked == "(Enter manually)":
            return questionary.text("Enter issue key:").ask()
        return picked.split(':')[0] if picked else None

def halt_cli(reason=None):
    """Gracefully halt the CLI, printing a friendly message and logging the halt."""
    msg = f"🦖 CLI halted. {reason}" if reason else "🦖 CLI halted."
    print(f"{DANGER_RED}{msg}{RESET}")
    contextual_log('warning', msg, extra={"feature": "cli"})
    sys.exit(0)

if __name__ == "__main__":
    main() 