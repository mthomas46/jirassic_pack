import os
import questionary
from typing import Any, Callable, Optional
from datetime import datetime
from colorama import Fore, Style, init as colorama_init
from yaspin import yaspin
from tqdm import tqdm
import sys
import logging
import uuid
import inspect
import platform
import socket
import requests

colorama_init(autoreset=True)

# utils.py
# This module provides utility functions and constants for option access, validation, error handling, and common choices.
# Used throughout the features to ensure consistent prompting, validation, and error reporting.

# Constants for prompt choices
DOC_TYPES = ["Release notes", "Changelog", "Sprint review"]
BULK_ACTIONS = ["Add comment", "Update field"]

REDACT_KEYS = {'api_token', 'password', 'token'}

def redact_sensitive(d):
    """Recursively redact sensitive fields in a dict or list."""
    if isinstance(d, dict):
        return {k: ('***' if k in REDACT_KEYS else redact_sensitive(v)) for k, v in d.items()}
    if isinstance(d, list):
        return [redact_sensitive(i) for i in d]
    return d

# Spinner context manager for network/file operations
def spinner(text: str, hold_on: bool = False):
    """
    Context manager for a spinner during long-running operations.
    If 'loading' is in the text or hold_on is True, display 'Hold on to your butts... 🦖' instead.
    Usage: with spinner('Fetching data...'):
    """
    themed = hold_on or ('loading' in text.lower())
    display_text = 'Hold on to your butts... 🦖' if themed else text
    return yaspin(text=display_text, color="cyan")

# Progress bar utility for iterables
def progress_bar(iterable, desc: str = "Processing"):
    """
    Wrap an iterable with a tqdm progress bar.
    Usage: for item in progress_bar(items, desc="Processing issues"):
    """
    from jirassicpack.cli import logger  # Ensure logger is always defined
    items = list(iterable)
    if len(items) > 50:
        info("🦖 Objects in mirror are closer than they appear.")
        logger.info("🦖 Objects in mirror are closer than they appear.")
    return tqdm(items, desc=desc, ncols=80, colour="green")

# Enhanced error/info output
def contextual_log(level, msg, extra=None, exc_info=None, params=None, result=None, operation=None, status=None, error_type=None, correlation_id=None, duration_ms=None, output_file=None, retry_count=None, feature=None):
    """
    Log with enriched context and standardized, human-friendly messages.
    - Prefix with emoji and feature tag (e.g., 🦖 [Create Issue])
    - Use present-tense, concise, readable language
    - Always include user, batch, suffix, operation, and feature in context
    - Redact sensitive info in params/result
    - For errors, include exception type and message
    - 'feature' is always present for easier filtering/parsing
    """
    from jirassicpack.cli import logger, CLI_VERSION, HOSTNAME, PID  # Avoid circular import
    frame = inspect.currentframe().f_back
    func_name = frame.f_code.co_name
    operation_id = str(uuid.uuid4())
    context = extra.copy() if extra else {}
    context.update({
        'function': func_name,
        'operation_id': operation_id,
        'operation': operation,
        'status': status,
        'error_type': error_type,
        'correlation_id': correlation_id or context.get('correlation_id'),
        'duration_ms': duration_ms,
        'output_file': output_file,
        'retry_count': retry_count,
        'env': os.environ.get('JIRASSICPACK_ENV', 'dev'),
        'cli_version': CLI_VERSION,
        'hostname': HOSTNAME,
        'pid': PID,
        'feature': feature or context.get('feature')
    })
    if params is not None:
        context['params'] = redact_sensitive(params)
    if result is not None:
        context['result'] = redact_sensitive(result)
    # Human-friendly log output
    if level == 'info':
        logger.info(msg, extra=context)
    elif level == 'error':
        logger.error(msg, extra=context, exc_info=exc_info)
    elif level == 'warning':
        logger.warning(msg, extra=context)
    elif level == 'debug':
        logger.debug(msg, extra=context)
    elif level == 'exception':
        logger.exception(msg, extra=context, exc_info=exc_info)
    else:
        logger.log(level, msg, extra=context)

def info(msg, extra=None, params=None, result=None):
    context_str = ""
    if extra:
        context_str = f" [feature={extra.get('feature')}, user={extra.get('user')}, batch={extra.get('batch')}, suffix={extra.get('suffix')}]"
    print(Fore.GREEN + str(msg) + context_str + Style.RESET_ALL)
    contextual_log('info', msg, extra=extra, params=params, result=result)

def error(msg, extra=None, exc_info=True, params=None, result=None):
    context_str = ""
    if extra:
        context_str = f" [feature={extra.get('feature')}, user={extra.get('user')}, batch={extra.get('batch')}, suffix={extra.get('suffix')}]"
    print(Fore.RED + str(msg) + context_str + Style.RESET_ALL)
    contextual_log('error', msg, extra=extra, exc_info=exc_info, params=params, result=result)

# Enhanced validation with re-prompting in interactive mode
def validate_required(value: Any, name: str, prompt: Optional[str] = None) -> Any:
    """
    Validate that a required value is present (not None or empty).
    If invalid and prompt is provided, re-prompt the user until valid.
    Returns the valid value or None if not interactive.
    """
    retry_count = 0
    while value is None or (isinstance(value, str) and not value.strip()):
        error(f"{name} is required.")
        if prompt:
            value = questionary.text(prompt).ask()
            # Enhanced logging for user prompt
            contextual_log('info', f"🛠️ [Utils] User prompted for required value: {name}", operation="user_prompt", status="answered", params={"prompt": prompt, "name": name}, retry_count=retry_count, extra={"feature": "validation"})
            retry_count += 1
        else:
            return None
    return value

def validate_date(date_str: str, name: str, prompt: Optional[str] = None) -> Any:
    """
    Validate that a string is a valid date in YYYY-MM-DD format.
    If invalid and prompt is provided, re-prompt the user until valid.
    Returns the valid date string or None if not interactive.
    """
    retry_count = 0
    while True:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except Exception:
            error(f"{name} must be in YYYY-MM-DD format.")
            if prompt:
                date_str = questionary.text(prompt).ask()
                # Enhanced logging for user prompt
                contextual_log('info', f"🛠️ [Utils] User prompted for date value: {name}", operation="user_prompt", status="answered", params={"prompt": prompt, "name": name}, retry_count=retry_count, extra={"feature": "validation"})
                retry_count += 1
            else:
                return None

def get_option(
    options: dict,
    key: str,
    prompt: Optional[str] = None,
    default: Optional[Any] = None,
    required: bool = False,
    validate: Optional[Callable[[Any, str], bool]] = None,
    choices: Optional[list] = None,
    password: bool = False
) -> Any:
    """
    Retrieve an option from a dictionary, ALWAYS prompt the user (never skip), using config/env/default as the pre-filled value.
    - options: the options/config dictionary
    - key: the key to retrieve
    - prompt: the prompt to show
    - default: default value if not provided
    - required: whether the value is required
    - choices: list of valid choices (for select prompts)
    - validate: optional validation function
    Returns the value for the option, or None if not provided and not required.
    """
    env_key = f'JIRA_{key.upper()}'
    prefill = options.get(key) or os.environ.get(env_key) or default
    if not prompt:
        prompt = f"Please enter a value for '{key}':"
    # Always prompt, using prefill as the default
    if choices:
        value = questionary.select(prompt, choices=choices, default=prefill).ask()
        contextual_log('info', f"🛠️ [Utils] User prompted for option: {key}", operation="user_prompt", status="answered", params={"prompt": prompt, "key": key, "choices": choices}, extra={"feature": "get_option"})
    elif password:
        value = questionary.password(prompt, default=prefill or '').ask()
        contextual_log('info', f"🛠️ [Utils] User prompted for password option: {key}", operation="user_prompt", status="answered", params={"prompt": prompt, "key": key}, extra={"feature": "get_option"})
    else:
        value = questionary.text(prompt, default=prefill or '').ask()
        contextual_log('info', f"🛠️ [Utils] User prompted for text option: {key}", operation="user_prompt", status="answered", params={"prompt": prompt, "key": key}, extra={"feature": "get_option"})
    if required and not validate_required(value, key):
        return None
    if validate and value and not validate(value, key):
        return None
    return value

def retry_or_skip(action_desc, func, *args, **kwargs):
    """
    Retry or skip a function call based on user input.
    """
    from jirassicpack.cli import logger  # Ensure logger is always defined
    retry_count = 0
    while True:
        try:
            result = func(*args, **kwargs)
            if result is not None:
                info("🦖 Clever girl. The operation succeeded.")
                info("🚗 We're back in the car again.")
                logger.info("🚗 We're back in the car again.")
            return result
        except Exception as e:
            print(DANGER_RED + f"🦖 Error during {action_desc}: {e}" + RESET)
            contextual_log('warning', f"🛠️ [Utils] Error during {action_desc}: {e}", operation="retry_or_skip", error_type=type(e).__name__, retry_count=retry_count, status="error", params={"action_desc": action_desc}, extra={"feature": "retry_or_skip"})
            choice = questionary.select(
                f"🦖 {action_desc} failed. What would you like to do?",
                choices=["Retry", "Skip", "Exit"],
                style=questionary.Style([
                    ("selected", "fg:#ffcc00 bold"),  # Yellow
                    ("pointer", "fg:#22bb22 bold"),   # Jungle green
                ])
            ).ask()
            contextual_log('info', f"🛠️ [Utils] User selected retry/skip option: {choice}", operation="retry_or_skip", retry_count=retry_count, status=choice.lower(), params={"action_desc": action_desc}, extra={"feature": "retry_or_skip"})
            if choice == "Retry":
                retry_count += 1
                continue
            elif choice == "Skip":
                info("🦖 Life finds a way! Skipping and continuing...")
                return None
            else:
                sys.exit(1)

# For batch summary, add a utility to print the message if there are failures
def print_batch_summary(results):
    print(WARNING_YELLOW + "\n🦖 Batch Summary:" + RESET)
    print("Feature         | Status")
    print("----------------|--------")
    any_failed = False
    fail_count = 0
    for name, status in results:
        color = JUNGLE_GREEN if status == "Success" else DANGER_RED
        print(f"{name:<15} | {color}{status}{RESET}")
        if status != "Success":
            any_failed = True
            fail_count += 1
    if any_failed:
        print(WARNING_YELLOW + "🦖 Batch completed with some failures, but life finds a way!" + RESET)
    if fail_count > len(results) // 2:
        error("💩 That is one big pile of errors.")
        logger.error("💩 That is one big pile of errors.")

def info_spared_no_expense():
    from jirassicpack.cli import logger  # Fix for NameError
    info("💸 Spared no expense! Report generated.")
    logger.info("💸 Spared no expense! Report generated.")

def prompt_with_validation(prompt, validate_fn, error_msg, default=None):
    """
    Prompt the user for input, validate with validate_fn, and re-prompt on error.
    Ensures default is a string (not None) to avoid TypeError in questionary.text().
    """
    default_str = default if default is not None else ""
    retry_count = 0
    while True:
        value = questionary.text(prompt, default=default_str).ask()
        contextual_log('info', f"🛠️ [Utils] User prompted with validation: {prompt}", operation="user_prompt", status="answered", params={"prompt": prompt}, retry_count=retry_count, extra={"feature": "prompt_with_validation"})
        if validate_fn(value):
            return value
        error(error_msg)
        retry_count += 1

def safe_get(d, keys, default='N/A'):
    """
    Safely get a nested value from a dict. Example: safe_get(issue, ['fields', 'status', 'name'])
    """
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return default
        if d is None:
            return default
    return d

def build_context(feature, user_email, batch_index, unique_suffix, correlation_id=None):
    """
    Build a context dict for logging and error/info utilities.
    """
    ctx = {"feature": feature, "user": user_email, "batch": batch_index, "suffix": unique_suffix}
    if correlation_id:
        ctx["correlation_id"] = correlation_id
    return ctx

def write_markdown_file(filename, lines, feature, user_email, batch_index, unique_suffix, context=None):
    """
    Write lines to a Markdown file with robust error handling and logging.
    """
    from .utils import info, error  # Avoid circular import if used in utils
    ctx = context or build_context(feature, user_email, batch_index, unique_suffix)
    try:
        with open(filename, 'w') as f:
            for line in lines:
                f.write(line)
        info(f"File written to {filename}", extra=ctx)
        contextual_log('info', f"🛠️ [Utils] Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=ctx)
    except Exception as e:
        error(f"Failed to write file: {e}. Check if the directory '{filename}' exists and is writable.", extra=ctx)
        contextual_log('error', f"🛠️ [Utils] Failed to write markdown file: {e}", operation="output_write", output_file=filename, status="error", error_type=type(e).__name__, extra=ctx)

def api_error_handler(feature, user_email, batch_index, unique_suffix):
    """
    Decorator for API error handling. Logs and reports errors with context.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            from .utils import error  # Avoid circular import if used in utils
            try:
                contextual_log('info', f"🛠️ [Utils] Starting operation '{func.__name__}' with params: {redact_sensitive(kwargs)}", operation=func.__name__, params=redact_sensitive(kwargs), extra=build_context(feature, user_email, batch_index, unique_suffix))
                result = func(*args, **kwargs)
                contextual_log('info', f"🛠️ [Utils] Operation '{func.__name__}' completed successfully.", operation=func.__name__, status="success", params=redact_sensitive(kwargs), extra=build_context(feature, user_email, batch_index, unique_suffix))
                return result
            except Exception as e:
                error(f"API error: {e}. Please check your Jira connection, credentials, and network.",
                      extra=build_context(feature, user_email, batch_index, unique_suffix))
                contextual_log('error', f"🛠️ [Utils] Exception occurred during '{func.__name__}': {e}", exc_info=True, operation=func.__name__, error_type=type(e).__name__, status="error", params=redact_sensitive(kwargs), extra=build_context(feature, user_email, batch_index, unique_suffix))
                return None
        return wrapper
    return decorator

def require_param(params, key, context, message=None):
    """
    Validate that a required parameter is present. If not, log an error and return False.
    """
    from .utils import error  # Avoid circular import if used in utils
    if not params.get(key):
        error(message or f"{key} is required.", extra=context)
        return False
    return True

def render_markdown_report(
    feature, user, batch, suffix, feature_title, summary_section, main_content_section
):
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    return f"""<!--
  This file was generated by Jirassic Pack.
  Feature: {feature}
  User: {user}
  Batch: {batch}
  Suffix: {suffix}
  Generated: {timestamp}
-->

# 🦖 Jirassic Pack Report: {feature_title}

**Generated by:** `{user}`  
**Date:** `{timestamp}`  
**Feature:** `{feature}`  
**Batch:** `{batch}`  
**Suffix:** `{suffix}`

---

## 📋 Summary

{summary_section}

---

## 📊 Details

{main_content_section}

---

## 📝 Notes

- This report was generated automatically by Jirassic Pack.
- For more information, visit [Jirassic Pack Documentation](https://github.com/your-org/jirassicpack).

---

*“Life finds a way.” – Dr. Ian Malcolm*
"""

def select_board_name(jira):
    """
    Prompt the user to select a Jira board via submenu:
    - Enter board name to search
    - Enter manually
    - Pick from list
    Returns the selected board name.
    """
    while True:
        method = questionary.select(
            "How would you like to select a board?",
            choices=[
                "Enter board name to search",
                "Pick from list",
                "Enter manually",
                "Abort"
            ],
            default="Pick from list"
        ).ask()
        if method == "Enter board name to search":
            search_term = questionary.text("Enter board name to search:").ask()
            if not search_term:
                continue
            boards = jira.list_boards(name=search_term)
            if not boards:
                info("No boards found matching your search.")
                continue
            boards = sorted(boards, key=lambda b: (b.get('name') or '').lower())
            choices = [f"{b.get('name','?')} (ID: {b.get('id','?')}, Type: {b.get('type','?')})" for b in boards]
            picked = questionary.select("Select a board:", choices=choices + ["(Search again)"]).ask()
            if picked == "(Search again)":
                continue
            for b in boards:
                label = f"{b.get('name','?')} (ID: {b.get('id','?')}, Type: {b.get('type','?')})"
                if picked == label:
                    return b.get('name')
        elif method == "Pick from list":
            boards = jira.list_boards()
            if not boards:
                info("No boards found in Jira.")
                continue
            boards = sorted(boards, key=lambda b: (b.get('name') or '').lower())
            choices = [f"{b.get('name','?')} (ID: {b.get('id','?')}, Type: {b.get('type','?')})" for b in boards]
            picked = questionary.select("Select a board:", choices=choices + ["(Abort)"]).ask()
            if picked == "(Abort)":
                return None
            for b in boards:
                label = f"{b.get('name','?')} (ID: {b.get('id','?')}, Type: {b.get('type','?')})"
                if picked == label:
                    return b.get('name')
        elif method == "Enter manually":
            return questionary.text("Enter board name:").ask()
        else:  # Abort
            return None

def select_sprint_name(jira, board_name=None, board_id=None):
    """
    Prompt the user to select a sprint via submenu:
    - Enter sprint name to search
    - Enter manually
    - Pick from list
    Handles boards that do not support sprints (e.g., Kanban) gracefully.
    Returns the selected sprint name.
    Accepts board_id directly if available, otherwise looks up by board_name.
    """
    if not board_id:
        if not board_name:
            board_name = questionary.text("Enter board name:").ask()
        boards = jira.list_boards(name=board_name)
        board_id = None
        for b in boards:
            if b.get('name') == board_name:
                board_id = b.get('id')
                break
        if not board_id:
            info(f"No board found with name '{board_name}'.")
            return questionary.text("Enter sprint name:").ask()
    while True:
        try:
            method = questionary.select(
                "How would you like to select a sprint?",
                choices=[
                    "Enter sprint name to search",
                    "Pick from list",
                    "Enter manually",
                    "Abort"
                ],
                default="Pick from list"
            ).ask()
            if method == "Enter sprint name to search":
                search_term = questionary.text("Enter sprint name to search:").ask()
                if not search_term:
                    continue
                sprints = jira.list_sprints(board_id)
                sprints = [s for s in sprints if search_term.lower() in s.get('name','').lower()]
                if not sprints:
                    info("No sprints match your search.")
                    continue
                choices = [f"{s.get('name','?')} (ID: {s.get('id','?')}, State: {s.get('state','?')})" for s in sprints]
                picked = questionary.select("Select a sprint:", choices=choices + ["(Search again)"]).ask()
                if picked == "(Search again)":
                    continue
                for s in sprints:
                    label = f"{s.get('name','?')} (ID: {s.get('id','?')}, State: {s.get('state','?')})"
                    if picked == label:
                        return s.get('name')
            elif method == "Pick from list":
                sprints = jira.list_sprints(board_id)
                if not sprints:
                    info("No sprints found for this board.")
                    continue
                choices = [f"{s.get('name','?')} (ID: {s.get('id','?')}, State: {s.get('state','?')})" for s in sprints]
                picked = questionary.select("Select a sprint:", choices=choices + ["(Abort)"]).ask()
                if picked == "(Abort)":
                    return None
                for s in sprints:
                    label = f"{s.get('name','?')} (ID: {s.get('id','?')}, State: {s.get('state','?')})"
                    if picked == label:
                        return s.get('name')
            elif method == "Enter manually":
                return questionary.text("Enter sprint name:").ask()
            else:  # Abort
                return None
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                info(f"This board does not support sprints (likely a Kanban board) or is invalid. Please select another board.")
                retry = questionary.confirm("Would you like to pick another board?", default=True).ask()
                if retry:
                    return select_sprint_name(jira)
                else:
                    return questionary.text("Enter sprint name:").ask()
            else:
                info(f"Error fetching sprints: {e}")
                return questionary.text("Enter sprint name:").ask()

def search_issues(jira):
    """
    Prompt the user to search for a Jira issue by key or summary and select from the list, or enter manually if not found. Caches issues per search term.
    Returns a (label, issue_obj) tuple for single selection.
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
                manual_key = questionary.text("Enter issue key:").ask()
                return (manual_key, None)
            elif action == "Abort":
                return (None, None)
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
        choices = [(f"{i.get('key','?')}: {i.get('fields',{}).get('summary','?')}", i) for i in issues]
        picked_label = questionary.select("Select an issue:", choices=[c[0] for c in choices] + ["(Enter manually)"]).ask()
        if picked_label == "(Enter manually)":
            manual_key = questionary.text("Enter issue key:").ask()
            return (manual_key, None)
        picked = next((c for c in choices if c[0] == picked_label), None)
        return picked if picked else (None, None) 