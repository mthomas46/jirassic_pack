import os
import questionary
from typing import Any, Callable, Optional
from datetime import datetime
from colorama import Fore, Style, init as colorama_init
from yaspin import yaspin
from tqdm import tqdm
import sys
import logging

colorama_init(autoreset=True)

# utils.py
# This module provides utility functions and constants for option access, validation, error handling, and common choices.
# Used throughout the features to ensure consistent prompting, validation, and error reporting.

# Constants for prompt choices
DOC_TYPES = ["Release notes", "Changelog", "Sprint review"]
BULK_ACTIONS = ["Add comment", "Update field"]

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
    items = list(iterable)
    if len(items) > 50:
        info("🦖 Objects in mirror are closer than they appear.")
        logger.info("🦖 Objects in mirror are closer than they appear.")
    return tqdm(items, desc=desc, ncols=80, colour="green")

# Enhanced error/info output
def info(msg, extra=None):
    context_str = ""
    if extra:
        context_str = f" [feature={extra.get('feature')}, user={extra.get('user')}, batch={extra.get('batch')}, suffix={extra.get('suffix')}]"
    print(Fore.GREEN + str(msg) + context_str + Style.RESET_ALL)
    logger.info(msg, extra=extra or {})

def error(msg, extra=None):
    context_str = ""
    if extra:
        context_str = f" [feature={extra.get('feature')}, user={extra.get('user')}, batch={extra.get('batch')}, suffix={extra.get('suffix')}]"
    print(Fore.RED + str(msg) + context_str + Style.RESET_ALL)
    logger.error(msg, extra=extra or {})

# Enhanced validation with re-prompting in interactive mode
def validate_required(value: Any, name: str, prompt: Optional[str] = None) -> Any:
    """
    Validate that a required value is present (not None or empty).
    If invalid and prompt is provided, re-prompt the user until valid.
    Returns the valid value or None if not interactive.
    """
    while value is None or (isinstance(value, str) and not value.strip()):
        error(f"{name} is required.")
        if prompt:
            value = questionary.text(prompt).ask()
        else:
            return None
    return value

def validate_date(date_str: str, name: str, prompt: Optional[str] = None) -> Any:
    """
    Validate that a string is a valid date in YYYY-MM-DD format.
    If invalid and prompt is provided, re-prompt the user until valid.
    Returns the valid date string or None if not interactive.
    """
    while True:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except Exception:
            error(f"{name} must be in YYYY-MM-DD format.")
            if prompt:
                date_str = questionary.text(prompt).ask()
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
    Retrieve an option from a dictionary, prompt the user if not present, and validate if needed.
    - options: the options/config dictionary
    - key: the key to retrieve
    - prompt: the prompt to show if value is missing
    - default: default value if not provided
    - required: whether the value is required
    - choices: list of valid choices (for select prompts)
    - validate: optional validation function
    Returns the value for the option, or None if not provided and not required.
    """
    env_key = f'JIRA_{key.upper()}'
    value = options.get(key) or os.environ.get(env_key) or default
    if value:
        return value
    if prompt:
        if choices:
            value = questionary.select(prompt, choices=choices, default=default).ask()
        elif password:
            value = questionary.password(prompt).ask()
        else:
            value = questionary.text(prompt, default=default or '').ask()
    if required and not validate_required(value, key):
        return None
    if validate and value and not validate(value, key):
        return None
    return value

def retry_or_skip(action_desc, func, *args, **kwargs):
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
    info("💸 Spared no expense! Report generated.")
    logger.info("💸 Spared no expense! Report generated.")

def prompt_with_validation(prompt, validate_fn, error_msg, default=None):
    """
    Prompt the user for input, validate with validate_fn, and re-prompt on error.
    Ensures default is a string (not None) to avoid TypeError in questionary.text().
    """
    default_str = default if default is not None else ""
    while True:
        value = questionary.text(prompt, default=default_str).ask()
        if validate_fn(value):
            return value
        error(error_msg)

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

def build_context(feature, user_email, batch_index, unique_suffix):
    """
    Build a context dict for logging and error/info utilities.
    """
    return {"feature": feature, "user": user_email, "batch": batch_index, "suffix": unique_suffix}

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
    except Exception as e:
        error(f"Failed to write file: {e}. Check if the directory '{filename}' exists and is writable.", extra=ctx)

def api_error_handler(feature, user_email, batch_index, unique_suffix):
    """
    Decorator for API error handling. Logs and reports errors with context.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            from .utils import error  # Avoid circular import if used in utils
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error(f"API error: {e}. Please check your Jira connection, credentials, and network.",
                      extra=build_context(feature, user_email, batch_index, unique_suffix))
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