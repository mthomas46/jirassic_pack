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
from jirassicpack.utils.prompt_utils import prompt_text, prompt_select, prompt_password, prompt_checkbox, select_from_list
from jirassicpack.utils.output_utils import ensure_output_dir
from jirassicpack.utils.message_utils import error, info, halt_cli
from jirassicpack.utils.progress_utils import spinner
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
from jirassicpack.cli_menu import feature_menu, onboarding_wizard
from jirassicpack.cli_state import load_cli_state, save_cli_state, RECENT_FEATURES, LAST_FEATURE, LAST_REPORT_PATH, FAVORITE_FEATURES, CLI_THEME, CLI_LOG_LEVEL, STATE_FILE
from jirassicpack.cli_llm_server import start_local_llm_server, stop_local_llm_server, view_local_llm_logs, live_tail_local_llm_logs, view_ollama_server_log, live_tail_ollama_server_log, search_ollama_server_log, filter_ollama_server_log, analyze_logs_and_generate_report, update_llm_menu, get_llm_status, is_process_running, live_tail_file
from jirassicpack.cli_feature_dispatch import run_feature
from jirassicpack.cli_logging_setup import logger

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
                        print("[DEBUG] Attempting to stop local LLM server...")
                        stop_local_llm_server()
                        print("[DEBUG] stop_local_llm_server() returned.")
                    except Exception as e:
                        error(f"[EXIT] Failed to stop local LLM server: {e}")
                    print("[DEBUG] Exiting CLI with sys.exit(0)")
                    sys.exit(0)
                contextual_log('info', f"🦖 [CLI] User selected feature '{action}' for user {jira_conf.get('email')}", extra={"feature": action, "user": jira_conf.get('email'), "batch": None, "suffix": None})
                run_feature(action, jira, options, user_email=jira_conf.get('email'))
    except Exception as e:
        import traceback
        stacktrace = traceback.format_exc()
        contextual_log('error', f"Fatal error: {e}", exc_info=True, extra={"feature": "cli", "user": None, "batch": None, "suffix": None, "stacktrace": stacktrace})
        rich_error(f"Fatal error: {e}")
        try:
            stop_local_llm_server()
        except Exception as e:
            error(f"[EXIT] Failed to stop local LLM server: {e}")
        print("[DEBUG] Exiting CLI after fatal error with sys.exit(1)")
        sys.exit(1)

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
            print("🦖 CLI terminated by user (KeyboardInterrupt). Goodbye!")
            sys.exit(0)
        observer.join()
    else:
        try:
            main()
        except KeyboardInterrupt:
            print("🦖 CLI terminated by user (KeyboardInterrupt). Goodbye!")
            sys.exit(0) 