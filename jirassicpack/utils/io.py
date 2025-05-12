import os
import sys
import questionary
from colorama import Fore, Style
from typing import Optional
import pyfiglet
from jirassicpack.utils.logging import contextual_log
from datetime import datetime
import contextlib
import threading
import time

JUNGLE_GREEN = '\033[38;5;34m'
WARNING_YELLOW = '\033[38;5;226m'
DANGER_RED = '\033[38;5;196m'
EARTH_BROWN = '\033[38;5;94m'
RESET = Style.RESET_ALL

# --- Jurassic Park ASCII Art Banners by Feature ---
FEATURE_ASCII_ART = {
    'create_issue': r'\n   __\n  / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🦖\n',
    'update_issue': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🦕\n',
    'bulk_operations': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🦴\n',
    'user_team_analytics': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🧬\n',
    'integration_tools': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🔗\n',
    'time_tracking_worklogs': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n⏳\n',
    'automated_documentation': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n📄\n',
    'sprint_board_management': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🌋\n',
    'advanced_metrics': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n📊\n',
    'gather_metrics': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n📈\n',
    'summarize_tickets': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🗂️\n',
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

PROMPT_ICON = "🦖"
PROMPT_COLOR = Fore.YELLOW

def styled_prompt(text):
    return f"{PROMPT_COLOR}{PROMPT_ICON} {text}{Style.RESET_ALL}"

def prompt_text(message, **kwargs):
    return questionary.text(styled_prompt(message), **kwargs).ask()

def prompt_select(message, choices, **kwargs):
    return questionary.select(styled_prompt(message), choices=choices, **kwargs).ask()

def prompt_password(message, **kwargs):
    return questionary.password(styled_prompt(message), **kwargs).ask()

def prompt_checkbox(message, choices, **kwargs):
    return questionary.checkbox(styled_prompt(message), choices=choices, **kwargs).ask()

def prompt_path(message, **kwargs):
    return questionary.path(styled_prompt(message), **kwargs).ask()

def ensure_output_dir(directory: str) -> None:
    """
    Ensure the output directory exists, creating it if necessary.
    Used by all features to guarantee output files can be written.
    """
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

def print_section_header(title: str, feature_key: Optional[str] = None) -> None:
    """
    Print a section header with per-feature ASCII art and color theme.
    """
    color = FEATURE_COLORS.get(feature_key, EARTH_BROWN)
    art = FEATURE_ASCII_ART.get(feature_key, '')
    try:
        header = pyfiglet.figlet_format(title, font="mini")
    except Exception:
        header = title
    print(color + art + RESET)
    print(color + header + RESET)
    print(f"[Section: {title}]")  # For screen readers

def celebrate_success() -> None:
    """
    Print a celebratory success message.
    """
    print(JUNGLE_GREEN + "🎉 Success! 🎉" + RESET)

def retry_or_skip(action_desc: str, func, *args, **kwargs):
    """
    Retry a function on failure, or allow the user to skip or exit.
    """
    while True:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(DANGER_RED + f"🦖 Error during {action_desc}: {e}" + RESET)
            choice = prompt_select(
                f"🦖 {action_desc} failed. What would you like to do?",
                choices=["Retry", "Skip", "Exit"]
            )
            if choice == "Retry":
                continue
            elif choice == "Skip":
                return None
            else:
                sys.exit(1)

def print_batch_summary(results):
    print(WARNING_YELLOW + "\n🦖 Batch Summary:" + RESET)
    print("Feature         | Status")
    print("----------------|--------")
    for name, status in results:
        color = JUNGLE_GREEN if status == "Success" else DANGER_RED
        print(f"{name:<15} | {color}{status}{RESET}")

def pretty_print_result(result):
    import json
    print("\n" + WARNING_YELLOW + json.dumps(result, indent=2) + RESET)

def halt_cli(reason=None):
    """Gracefully halt the CLI, printing a friendly message and logging the halt."""
    msg = f"🦖 CLI halted. {reason}" if reason else "🦖 CLI halted."
    print(f"{DANGER_RED}{msg}{RESET}")
    contextual_log('warning', msg, extra={"feature": "cli"})
    sys.exit(0)

def get_validated_input(prompt, validate_fn=None, error_msg=None, default=None, regex=None, date_format=None, min_date=None, max_date=None):
    retry_count = 0
    while True:
        value = questionary.text(prompt, default=default or '').ask()
        contextual_log('info', f"🦖 [CLI] User prompted for validated input: {prompt}", operation="user_prompt", status="answered", params={"prompt": prompt}, retry_count=retry_count, extra={"feature": "get_validated_input"})
        # Regex validation
        if regex:
            import re
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

@contextlib.contextmanager
def spinner(message="Working..."):
    """A simple CLI spinner context manager for visual feedback during long operations."""
    stop = False
    def spin():
        spinner_cycle = '|/-\\'
        idx = 0
        while not stop:
            sys.stdout.write(f"\r{message} {spinner_cycle[idx % len(spinner_cycle)]}")
            sys.stdout.flush()
            time.sleep(0.1)
            idx += 1
    t = threading.Thread(target=spin)
    t.start()
    try:
        yield
    finally:
        stop = True
        t.join()
        sys.stdout.write("\r" + " " * (len(message) + 4) + "\r")
        sys.stdout.flush()

# Simple progress_bar generator for iterating with progress feedback
import itertools

def progress_bar(iterable, desc="Progress"):
    """A simple progress bar for CLI batch operations."""
    total = len(iterable) if hasattr(iterable, '__len__') else None
    for i, item in enumerate(iterable, 1):
        if total:
            sys.stdout.write(f"\r{desc}: {i}/{total}")
        else:
            sys.stdout.write(f"\r{desc}: {i}")
        sys.stdout.flush()
        yield item
    sys.stdout.write("\n")
    sys.stdout.flush()

def error(message, extra=None, feature=None):
    """
    Print an error message in red and log it if contextual_log is available.
    """
    print(Fore.RED + "🦖 " + str(message) + Style.RESET_ALL)
    try:
        from jirassicpack.utils.logging import contextual_log
        context = extra or {}
        if feature:
            context["feature"] = feature
        contextual_log('error', str(message), extra=context)
    except Exception:
        pass  # Logging is best-effort

def info(message, extra=None, feature=None):
    """
    Print an info message in yellow and log it if contextual_log is available.
    """
    print(Fore.YELLOW + str(message) + Style.RESET_ALL)
    try:
        from jirassicpack.utils.logging import contextual_log
        context = extra or {}
        if feature:
            context["feature"] = feature
        contextual_log('info', str(message), extra=context)
    except Exception:
        pass

def info_spared_no_expense():
    """
    Print a Jurassic Park reference for successful completion.
    """
    print(Fore.GREEN + "🦖 Spared no expense!" + Style.RESET_ALL)

def prompt_with_validation(prompt, validate_fn=None, error_msg=None, default=None):
    while True:
        value = prompt_text(prompt, default=default or '')
        if validate_fn and not validate_fn(value):
            print(Fore.RED + (error_msg or 'Invalid input.') + Style.RESET_ALL)
            continue
        if not value or not value.strip():
            print(Fore.RED + 'Input is required.' + Style.RESET_ALL)
            continue
        return value

def get_option(options, key, prompt=None, default=None, choices=None, required=False, validate=None, password=False):
    value = options.get(key, default)
    if value:
        return value
    while True:
        if choices:
            value = prompt_select(prompt or f"Select {key}:", choices=choices)
        elif password:
            value = prompt_password(prompt or f"Enter {key}:")
        else:
            value = prompt_text(prompt or f"Enter {key}:", default=default or '')
        if validate and not validate(value):
            print(Fore.RED + f"Invalid value for {key}." + Style.RESET_ALL)
            continue
        if required and (not value or not value.strip()):
            print(Fore.RED + f"{key} is required." + Style.RESET_ALL)
            continue
        break
    return value

def validate_required(value):
    """
    Return True if the value is not None and not empty (after stripping).
    """
    return value is not None and str(value).strip() != ""

def validate_date(date_str):
    """
    Return True if the string is a valid date in YYYY-MM-DD format.
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except Exception:
        return False 

def render_markdown_report(
    feature, user, batch, suffix, feature_title, summary_section, main_content_section
):
    """
    Generate a Markdown report for Jirassic Pack output.
    """
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

def write_markdown_file(filename, lines, feature, user_email, batch_index, unique_suffix, context=None):
    """
    Write lines to a Markdown file with robust error handling and logging.
    """
    ctx = context or {}
    try:
        with open(filename, 'w') as f:
            for line in lines:
                f.write(line)
        info(f"File written to {filename}", extra=ctx)
        from jirassicpack.utils.logging import contextual_log
        contextual_log('info', f"🛠️ [Utils] Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=ctx)
    except Exception as e:
        error(f"Failed to write file: {e}. Check if the directory '{filename}' exists and is writable.", extra=ctx)
        from jirassicpack.utils.logging import contextual_log
        contextual_log('error', f"🛠️ [Utils] Failed to write markdown file: {e}", operation="output_write", output_file=filename, status="error", error_type=type(e).__name__, extra=ctx)

def require_param(params, key, context, message=None):
    """
    Validate that a required parameter is present. If not, log an error and return False.
    """
    if not params.get(key):
        error(message or f"{key} is required.", extra=context)
        return False
    return True 