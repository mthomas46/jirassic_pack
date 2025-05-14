import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
from jirassicpack.config import ConfigLoader
from jirassicpack.jira_client import JiraClient
import questionary
from typing import Any, Dict
from jirassicpack.utils.io import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, spinner, progress_bar, error, info, prompt_text, prompt_select, prompt_password, prompt_checkbox, prompt_path
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
from jirassicpack.log_monitoring import log_parser
from jirassicpack.features.ticket_discussion_summary import ticket_discussion_summary
from jirassicpack.features.test_local_llm import test_local_llm
import subprocess
import shutil
import requests
import threading
from jirassicpack.utils.rich_prompt import (
    rich_panel, rich_info, rich_error, rich_success,
    panel_life_finds_a_way, panel_spared_no_expense, panel_objects_in_mirror, panel_clever_girl,
    panel_hold_onto_your_butts, panel_big_pile_of_errors, panel_jurassic_ascii, panel_nobody_cares,
    panel_crazy_son_of_a, panel_welcome_dr, panel_combined_welcome
)
from mdutils.mdutils import MdUtils

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
        "log_parser": log_parser,
        "ticket_discussion_summary": ticket_discussion_summary,
        "test_local_llm": test_local_llm,
    }

# --- Feature Groupings (Reordered for UX) ---
FEATURE_GROUPS = {
    "Test Connection": [
        ("🧪 Test connection to Jira", "test_connection"),
    ],
    "Local LLM Tools": [
        ("🦖 Start Local LLM Server", "start_local_llm_server"),
        ("🛑 Stop Local LLM Server", "stop_local_llm_server"),
        ("🪵 View Local LLM Logs", "view_local_llm_logs"),
        ("🪵 View Ollama Server Log", "view_ollama_server_log"),
        ("👀 Live Tail Ollama Server Log", "live_tail_ollama_server_log"),
        ("🔍 Search Ollama Server Log", "search_ollama_server_log"),
        ("🧹 Filter Ollama Server Log", "filter_ollama_server_log"),
        ("🦖 Test Local LLM", "test_local_llm"),
        ("👀 Live Tail Local LLM Logs", "live_tail_local_llm_logs"),
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
        ("📄 Ticket Discussion Summary", "ticket_discussion_summary"),
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
        ("🦖 Analyze Logs and Generate Report", "analyze_logs_and_generate_report"),
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
        group = prompt_select(
            "Select a feature group:",
            choices=group_names
        )
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
            feature = prompt_select(
                f"Select a feature from '{group}':",
                choices=submenu_choices
            )
            contextual_log('info', f"🦖 [CLI] User selected feature: {feature}", operation="user_prompt", status="answered", params={"feature": feature}, extra={"feature": "cli"})
            if feature == "return_to_main_menu":
                break  # Go back to group selection
            yield feature, group

# --- Main loop: persistently return to main menu ---
def main() -> None:
    try:
        # Show a single combined welcome panel
        user = None
        config_path = None
        log_level = LOG_LEVEL
        if len(sys.argv) > 1:
            for arg in sys.argv:
                if arg.startswith('--config='):
                    config_path = arg.split('=', 1)[1]
                if arg.startswith('--log-level='):
                    log_level = arg.split('=', 1)[1]
        config = ConfigLoader(config_path)
        jira_conf = config.get_jira_config()
        user = jira_conf.get('email', 'User')
        panel_combined_welcome(user)
        rich_info(BANNER_ALT_TEXT)
        options = config.get_options()
        features = getattr(config, 'config', {}).get('features')
        feature = getattr(config, 'config', {}).get('feature')
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
            panel_spared_no_expense()
            panel_crazy_son_of_a()
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
                    panel_nobody_cares()
                    rich_info("🦖 CLI halted. User exited from main menu.")
                    try:
                        stop_local_llm_server()
                    except Exception as e:
                        error(f"[EXIT] Failed to stop local LLM server: {e}")
                    return
                contextual_log('info', f"🦖 [CLI] User selected feature '{action}' for user {jira_conf.get('email')}", extra={"feature": action, "user": jira_conf.get('email'), "batch": None, "suffix": None})
                run_feature(action, jira, options, user_email=jira_conf.get('email'))
    except Exception as e:
        rich_error(f"Fatal error: {e}")
        try:
            stop_local_llm_server()
        except Exception as e:
            error(f"[EXIT] Failed to stop local LLM server: {e}")

def run_feature(feature: str, jira: JiraClient, options: dict, user_email: str = None, batch_index: int = None, unique_suffix: str = None) -> None:
    update_llm_menu()
    context = {"feature": feature, "user": user_email, "batch": batch_index, "suffix": unique_suffix}
    contextual_log('debug', f"[DEBUG] run_feature called. feature={feature}, user_email={user_email}, batch_index={batch_index}, unique_suffix={unique_suffix}, options={options}", extra=context)
    menu_to_key = {
        "🧪 Test connection to Jira": "test_connection",
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
    if key == "test_local_llm":
        FEATURE_REGISTRY[key](options, user_email=user_email, batch_index=batch_index, unique_suffix=unique_suffix)
        return
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
                info("Aborted: No user found with provided details.")
                return
            pretty_print_result(result)
        except Exception as e:
            error(f"🦖 Error fetching user: {e}", extra=context)
            contextual_log('error', f"🦖 [CLI] Error fetching user: {e}", exc_info=True, extra=context)
        return
    if key == "search_users":
        try:
            query = prompt_text("Search query (name/email):")
            contextual_log('info', f"🦖 [CLI] User searched users with query: {query}", extra={"feature": key, "easteregg": "clever_girl" if 'raptor' in query.lower() else None})
            result = jira.search_users(query=query)
            if not result:
                panel_nobody_cares()
                info("Aborted: No users found for query.")
                return
            panel_clever_girl()
            pretty_print_result(result)
        except Exception as e:
            panel_big_pile_of_errors()
            error(f"🦖 Error searching users: {e}", extra=context)
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
            issue_key = search_issues(jira)
            if issue_key:
                info(f"Selected issue: {issue_key}")
                result = jira.get_task(issue_key)
                pretty_print_result(result)
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
    if key == "search_issues":
        try:
            issue_key = search_issues(jira)
            if not issue_key:
                info("Aborted: No issue selected.")
                return
            info(f"Selected issue: {issue_key}")
        except Exception as e:
            error(f"🦖 Error searching issues: {e}", extra=context)
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
                panel_nobody_cares()
                info("Aborted: No users found or operation cancelled.")
                return
            filename = f"{output_dir}/jira_users{unique_suffix}.md"
            try:
                with open(filename, 'w') as f:
                    f.write("# Jira Users\n\n")
                    for user in users:
                        f.write(f"- {user.get('displayName', user.get('name', 'Unknown'))} ({user.get('emailAddress', 'N/A')})\n")
                panel_objects_in_mirror()
                info("🦖 Objects in mirror are closer than they appear.")
            except Exception as file_err:
                panel_big_pile_of_errors()
                error(f"🦖 Failed to write user list to file: {file_err}", extra={"feature": "output_all_users", "user": None, "batch": None, "suffix": unique_suffix})
        except Exception as e:
            panel_big_pile_of_errors()
            error(f"🦖 Failed to fetch users: {e}", extra={"feature": "output_all_users", "user": None, "batch": None, "suffix": unique_suffix})

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

def pretty_print_result(result):
    rich_panel(json.dumps(result, indent=2), style="info")

def halt_cli(reason=None):
    msg = f"🦖 CLI halted. {reason}" if reason else "🦖 CLI halted."
    rich_error(msg)
    contextual_log('warning', msg, extra={"feature": "cli"})
    sys.exit(0)

# Helper to check if a process is running (basic check)
def is_process_running(process_name):
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
    try:
        import psutil
    except ImportError:
        return '🔴 (psutil not installed)'
    ollama_running = is_process_running('ollama')
    http_api_running = is_process_running('http_api.py')
    if ollama_running and http_api_running:
        return '🟢'
    return '🔴'

# Update menu with status indicator
def update_llm_menu():
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
            error(f"[ERROR] Failed to start 'ollama serve': {e}")
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
            error(f"[LLM] Failed to start 'http_api.py': {e}")
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
        error(f"[ERROR] Health check error: {e}")
    info("🦖 Local LLM server startup attempted. Use 'Test Local LLM' to verify health.")

def stop_local_llm_server():
    info("🛑 Stopping local LLM server...")
    # Try health check, but proceed regardless of result
    health_running = False
    try:
        resp = requests.get("http://localhost:5000/health", timeout=2)
        if resp.status_code == 200:
            health_running = True
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
                error(f"[ERROR] Could not terminate PID {proc.info['pid']}: {e}")
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
    import os
    import sys
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
    import os
    ollama_log = os.path.expanduser("~/.ollama/ollama.log")
    ollama_dir = os.path.abspath(os.path.join(os.getcwd(), "../Ollama7BPoc"))
    http_api_log = os.path.join(ollama_dir, "llm_api.log")
    threads = []
    stop_event = threading.Event()
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
    log_path = "/Users/mykalthomas/Documents/work/Ollama7BPoc/ollama_server.log"
    print(f"--- ollama_server.log (last 40 lines) ---")
    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
            print(''.join(lines[-40:]))
    except FileNotFoundError:
        print(f"No ollama_server.log found at {log_path}.")
    except Exception as e:
        print(f"[ERROR] Could not read ollama_server.log: {e}")

def live_tail_ollama_server_log():
    import time
    log_path = "/Users/mykalthomas/Documents/work/Ollama7BPoc/ollama_server.log"
    print(f"--- Live tailing ollama_server.log (Ctrl+C to stop) ---")
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
    info(f"🦖 Log analysis report written to {output_path}")

if __name__ == "__main__":
    main() 