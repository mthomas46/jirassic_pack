"""
io.py
This module provides all CLI I/O utilities for Jirassic Pack, including prompts, output formatting, file writing, validation, and rich Jurassic Park–themed UX. All user interaction, output, and report generation is handled here.
"""
import os
import sys
import questionary
from colorama import Fore, Style as ColoramaStyle
from typing import Optional
import pyfiglet
from jirassicpack.utils.logging import contextual_log
from datetime import datetime
import contextlib
from rich.traceback import install as rich_traceback_install
from jirassicpack.utils.rich_prompt import rich_info, rich_error, rich_success, rich_prompt_text, rich_panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from InquirerPy import inquirer
from marshmallow import ValidationError
import re
import functools
import json
from jirassicpack.constants import FAILED_TO, WRITTEN_TO
import logging
import traceback
from functools import wraps
from questionary import Choice, Style as QStyle
from InquirerPy.utils import get_style

rich_traceback_install()

# --- Enhanced Logging for Recursion Debugging ---
def log_entry_exit(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Recursion depth counter (thread-local, per function)
        depth = getattr(wrapper, '_depth', 0)
        wrapper._depth = depth + 1
        logging.debug(f"[ENTRY] {func.__name__} (depth={wrapper._depth}) args={args}, kwargs={kwargs}")
        logging.debug(f"[STACK] {func.__name__} call stack:\n{''.join(traceback.format_stack(limit=10))}")
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            logging.error(f"[EXCEPTION] {func.__name__}: {e}\n{traceback.format_exc()}")
            wrapper._depth = depth  # Reset depth on exception
            raise
        wrapper._depth = depth  # Decrement depth after return
        logging.debug(f"[EXIT] {func.__name__} (depth={wrapper._depth})")
        return result
    wrapper._depth = 0
    return wrapper

# Ensure debug-level logging is enabled
logging.basicConfig(level=logging.DEBUG)

# Apply the decorator to all functions in this file as an example
# (You can copy this decorator to other modules and apply as needed)

JUNGLE_GREEN = '\033[38;5;34m'
WARNING_YELLOW = '\033[38;5;226m'
DANGER_RED = '\033[38;5;196m'
EARTH_BROWN = '\033[38;5;94m'
RESET = ColoramaStyle.RESET_ALL

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
    return f"{PROMPT_COLOR}{PROMPT_ICON} {text}{RESET}"
styled_prompt = log_entry_exit(styled_prompt)

def prompt_text(message, **kwargs):
    return rich_prompt_text(message, **kwargs)
prompt_text = log_entry_exit(prompt_text)

# Define a default style for questionary prompts
DEFAULT_PROMPT_STYLE = QStyle([
    ("selected", "fg:#22bb22 bold"),  # Jungle green
    ("pointer", "fg:#ffcc00 bold"),   # Yellow
    ("question", "fg:#00aaee bold"),
    ("answer", "fg:#ffaa00 bold"),
    ("highlighted", "fg:#ffcc00 bold"),
])
# Define a style dict for InquirerPy and convert to Style object
INQUIRERPY_STYLE = get_style({
    "selected": "fg:#22bb22 bold",
    "pointer": "fg:#ffcc00 bold",
    "question": "fg:#00aaee bold",
    "answer": "fg:#ffaa00 bold",
    "highlighted": "fg:#ffcc00 bold",
})

def prompt_select(message, choices, **kwargs):
    style = kwargs.pop('style', DEFAULT_PROMPT_STYLE)
    # If choices are dicts with 'name' and 'value', use questionary.Choice
    if choices and isinstance(choices[0], dict) and 'name' in choices[0] and 'value' in choices[0]:
        q_choices = [Choice(title=c['name'], value=c['value']) for c in choices]
        rich_panel(message, style="prompt")
        picked = questionary.select(message, choices=q_choices, style=style, **kwargs).ask()
        if isinstance(picked, Choice):
            picked = picked.value
        return picked
    # Use questionary for select, but print the message with rich first
    if (isinstance(choices, list) and (
        choices == ["Yes", "No"] or choices == ["No", "Yes"] or len(choices) <= 4
    )):
        rich_panel(message, style="prompt")
        picked = questionary.select(message, choices=choices, style=style, **kwargs).ask()
        if isinstance(picked, Choice):
            picked = picked.value
        return picked
    else:
        # Use the private helper for long lists
        return _select_from_list(
            items=choices,
            message=message,
            display_fn=str,
            multi=False,
            allow_abort=False,
            style=style
        )
prompt_select = log_entry_exit(prompt_select)

def prompt_password(message, **kwargs):
    return questionary.password(message, **kwargs).ask()
prompt_password = log_entry_exit(prompt_password)

def prompt_checkbox(message, choices, **kwargs):
    style = kwargs.pop('style', DEFAULT_PROMPT_STYLE)
    if choices and isinstance(choices[0], dict) and 'name' in choices[0] and 'value' in choices[0]:
        q_choices = [Choice(title=c['name'], value=c['value']) for c in choices]
        rich_panel(message, style="prompt")
        picked = questionary.checkbox(message, choices=q_choices, style=style, **kwargs).ask()
        if picked and isinstance(picked[0], Choice):
            picked = [p.value for p in picked]
        return picked
    else:
        rich_panel(message, style="prompt")
        picked = questionary.checkbox(message, choices=choices, style=style, **kwargs).ask()
        if picked and isinstance(picked[0], Choice):
            picked = [p.value for p in picked]
        return picked
prompt_checkbox = log_entry_exit(prompt_checkbox)

def prompt_path(message, **kwargs):
    return questionary.path(message, **kwargs).ask()
prompt_path = log_entry_exit(prompt_path)

def print_section_header(title: str, feature_key: Optional[str] = None) -> None:
    art = FEATURE_ASCII_ART.get(feature_key, '')
    try:
        header = pyfiglet.figlet_format(title, font="mini")
    except Exception:
        header = title
    rich_panel(f"{art}\n{header}", title=title, style="banner")
    rich_info(f"[Section: {title}]")
print_section_header = log_entry_exit(print_section_header)

def celebrate_success() -> None:
    """
    Print a celebratory success message.
    """
    print(JUNGLE_GREEN + "🎉 Success! 🎉" + RESET)
celebrate_success = log_entry_exit(celebrate_success)

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
retry_or_skip = log_entry_exit(retry_or_skip)

def print_batch_summary(results):
    rich_panel("🦖 Batch Summary:", style="info")
    rich_info("Feature         | Status")
    rich_info("----------------|--------")
    for name, status in results:
        color = "success" if status == "Success" else "error"
        rich_info(f"{name:<15} | [{color}]{status}[/{color}]")
print_batch_summary = log_entry_exit(print_batch_summary)

def pretty_print_result(result):
    import json
    rich_panel(json.dumps(result, indent=2), style="info")
pretty_print_result = log_entry_exit(pretty_print_result)

def halt_cli(reason=None):
    """Gracefully halt the CLI, printing a friendly message and logging the halt."""
    msg = f"🦖 CLI halted. {reason}" if reason else "🦖 CLI halted."
    print(f"{DANGER_RED}{msg}{RESET}")
    contextual_log('warning', msg, extra={"feature": "cli"})
    sys.exit(0)
halt_cli = log_entry_exit(halt_cli)

# --- Prompt/Validation Utilities ---
# Legacy functions get_validated_input and prompt_with_validation have been removed.
# Use prompt_with_schema and get_option for all prompts/validation throughout the codebase.

@contextlib.contextmanager
def spinner(message="Working..."):
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(message, total=None)
        try:
            yield
        finally:
            progress.remove_task(task)
spinner = log_entry_exit(spinner)

def progress_bar(iterable, desc="Progress"):
    total = len(iterable) if hasattr(iterable, '__len__') else None
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(desc, total=total)
        for index, element in enumerate(iterable, 1):
            progress.update(task, completed=index)
            yield element
progress_bar = log_entry_exit(progress_bar)

def error(message, extra=None, feature=None):
    rich_error(message)
    try:
        from jirassicpack.utils.logging import contextual_log
        context = extra or {}
        if feature:
            context["feature"] = feature
        contextual_log('error', str(message), extra=context)
    except Exception:
        pass  # Logging is best-effort
error = log_entry_exit(error)

def info(message, extra=None, feature=None):
    rich_info(message)
    try:
        from jirassicpack.utils.logging import contextual_log
        context = extra or {}
        if feature:
            context["feature"] = feature
        contextual_log('info', str(message), extra=context)
    except Exception:
        pass
info = log_entry_exit(info)

def info_spared_no_expense():
    rich_success("🦖 Spared no expense!")
info_spared_no_expense = log_entry_exit(info_spared_no_expense)

def get_option(options, key, prompt=None, default=None, choices=None, required=False, validate=None, password=False, marshmallow_field=None, marshmallow_schema=None):
    value = options.get(key, default)
    if value:
        # Marshmallow field validation
        if marshmallow_field:
            try:
                marshmallow_field.deserialize(value)
            except ValidationError as err:
                suggestion = None
                if hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages and isinstance(err.messages[0], tuple):
                    message, suggestion = err.messages[0]
                elif hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages:
                    message = err.messages[0]
                else:
                    message = str(err)
                rich_error(f"Input validation error: {message}", suggestion)
                value = None
        # Marshmallow schema validation
        if marshmallow_schema:
            try:
                marshmallow_schema.load({key: value})
            except ValidationError as err:
                suggestion = None
                if hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages and isinstance(err.messages[0], tuple):
                    message, suggestion = err.messages[0]
                elif hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages:
                    message = err.messages[0]
                else:
                    message = str(err)
                rich_error(f"Input validation error: {message}", suggestion)
                value = None
        if value:
            return value
    while True:
        if choices:
            value = prompt_select(prompt or f"Select {key}:", choices=choices)
        elif password:
            value = prompt_password(prompt or f"Enter {key}:")
        else:
            value = prompt_text(prompt or f"Enter {key}:", default=default or '')
        # Marshmallow field validation
        if marshmallow_field:
            try:
                marshmallow_field.deserialize(value)
            except ValidationError as err:
                suggestion = None
                if hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages and isinstance(err.messages[0], tuple):
                    message, suggestion = err.messages[0]
                elif hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages:
                    message = err.messages[0]
                else:
                    message = str(err)
                rich_error(f"Input validation error: {message}", suggestion)
                continue
        # Marshmallow schema validation
        if marshmallow_schema:
            try:
                marshmallow_schema.load({key: value})
            except ValidationError as err:
                suggestion = None
                if hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages and isinstance(err.messages[0], tuple):
                    message, suggestion = err.messages[0]
                elif hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages:
                    message = err.messages[0]
                else:
                    message = str(err)
                rich_error(f"Input validation error: {message}", suggestion)
                continue
        if validate and not validate(value):
            rich_error(f"Invalid value for {key}.")
            continue
        if required and (not value or not value.strip()):
            rich_error(f"{key} is required.")
            continue
        break
    return value
get_option = log_entry_exit(get_option)

def validate_required(value):
    """
    Return True if the value is not None and not empty (after stripping).
    """
    return value is not None and str(value).strip() != ""
validate_required = log_entry_exit(validate_required)

def validate_date(date_str):
    """
    Return True if the string is a valid date in YYYY-MM-DD format.
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except Exception:
        return False 
validate_date = log_entry_exit(validate_date)

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
render_markdown_report = log_entry_exit(render_markdown_report)

def require_param(params, key, context, message=None):
    """
    Validate that a required parameter is present. If not, log an error and return False.
    """
    if not params.get(key):
        error(message or f"{key} is required.", extra=context)
        return False
    return True 
require_param = log_entry_exit(require_param)

def select_with_pagination_and_fuzzy(choices, message="Select an item:", page_size=15, fuzzy_threshold=30):
    """
    Combines pagination, jump-to-letter, and fuzzy finder for large lists.
    Uses InquirerPy fuzzy finder for very large lists, otherwise paginates and allows jump-to-letter.
    """
    if len(choices) > fuzzy_threshold:
        # Use fuzzy finder for very large lists
        return inquirer.fuzzy(
            message=message,
            choices=choices,
            max_height="70%"
        ).execute()
    elif len(choices) > page_size:
        # Paginate and allow jump to letter
        page = 0
        total_pages = (len(choices) - 1) // page_size + 1
        while True:
            start = page * page_size
            end = start + page_size
            page_choices = choices[start:end]
            nav = []
            if page > 0:
                nav.append("⬅️ Previous page")
            if end < len(choices):
                nav.append("➡️ Next page")
            nav.append("🔤 Jump to letter")
            nav.append("🔢 Jump to page")
            nav.append("❌ Exit")
            selection = prompt_select(
                f"{message} (Page {page+1}/{total_pages})",
                choices=page_choices + nav
            )
            if selection == "⬅️ Previous page":
                page -= 1
            elif selection == "➡️ Next page":
                page += 1
            elif selection == "🔢 Jump to page":
                page = int(prompt_text("Enter page number:", default=str(page+1))) - 1
            elif selection == "🔤 Jump to letter":
                letter = prompt_text("Type a letter to jump:")
                idx = next((index for index, choice in enumerate(choices) if choice.lower().startswith(letter.lower())), None)
                if idx is not None:
                    page = idx // page_size
                else:
                    info("No items found for that letter.")
            elif selection == "❌ Exit":
                return None
            else:
                return selection
    else:
        return prompt_select(message, choices=choices) 
select_with_pagination_and_fuzzy = log_entry_exit(select_with_pagination_and_fuzzy)

def make_output_filename(feature, params, output_dir='output', ext='md'):
    """
    Build a human-readable output filename for reports.
    - feature: string, e.g. 'metrics', 'create_issue'
    - params: ordered list of (param_name, value) tuples
    - output_dir: directory for output files
    - ext: file extension (default 'md')
    Returns: full path to the output file
    """
    def sanitize(val):
        # Remove/replace unsafe chars, spaces, etc.
        return re.sub(r'[^\w\-]', '', str(val).replace(' ', '_'))
    def prettify_param(k, v):
        # Format dates as YYYYMMDD
        if isinstance(v, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            v = v.replace('-', '')
        # Truncate summaries/titles
        if k in ("summary", "title") and isinstance(v, str):
            v = v[:20]
        # Usernames as display names: lowercase, underscores
        if k in ("user", "username", "assignee") and isinstance(v, str):
            v = v.lower().replace(' ', '_')
        return sanitize(v)
    param_str = '_'.join(f"{sanitize(param_key)}-{prettify_param(param_key, param_value)}" for param_key, param_value in params if param_value)
    date_str = datetime.now().strftime('%m-%d-%y')
    parts = [feature]
    if param_str:
        parts.append(param_str)
    parts.append(date_str)
    filename = '_'.join(parts) + f'.{ext}'
    return f"{output_dir}/{filename}" 
make_output_filename = log_entry_exit(make_output_filename)

def render_markdown_report_template(
    report_header: str = '',
    table_of_contents: str = '',
    report_summary: str = '',
    action_items: str = '',
    top_n_lists: str = '',
    related_links: str = '',
    grouped_issue_sections: str = '',
    export_metadata: str = '',
    glossary: str = '',
    next_steps: str = ''
) -> str:
    """
    Standardized Markdown report template for all output features.
    """
    return f"""
{report_header}

{table_of_contents}

{report_summary}

---

{action_items}

{top_n_lists}

{related_links}

---

{grouped_issue_sections}

---

{next_steps}

{export_metadata}

{glossary}
""" 
render_markdown_report_template = log_entry_exit(render_markdown_report_template)

def status_emoji(status: str) -> str:
    """
    Map a Jira status string to a corresponding emoji for visual reporting.
    Args:
        status (str): The status name (e.g., 'Done', 'In Progress').
    Returns:
        str: Emoji representing the status.
    """
    s = status.lower() if status else ''
    if s in ['done', 'closed', 'resolved']:
        return '✅'
    elif s in ['in progress', 'in review', 'doing']:
        return '🟡'
    elif s in ['blocked', 'on hold', 'overdue']:
        return ''
    return '⬜️' 
status_emoji = log_entry_exit(status_emoji)

def feature_error_handler(feature_name):
    """
    Universal decorator for feature entrypoints. Handles error logging, context, and user feedback.
    Usage: @feature_error_handler('create_issue')
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from jirassicpack.utils.logging import contextual_log, build_context
            user_email = kwargs.get('user_email')
            batch_index = kwargs.get('batch_index')
            unique_suffix = kwargs.get('unique_suffix')
            context = build_context(feature_name, user_email, batch_index, unique_suffix)
            try:
                return func(*args, **kwargs)
            except KeyboardInterrupt:
                contextual_log('warning', f"[{feature_name}] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", extra=context, feature=feature_name)
                info(f"Graceful exit from {feature_name} feature.", extra=context, feature=feature_name)
            except Exception as e:
                contextual_log('error', f"[{feature_name}] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", extra=context, feature=feature_name)
                error(f"[{feature_name}] Exception: {e}", extra=context, feature=feature_name)
                raise
        return wrapper
    return decorator
feature_error_handler = log_entry_exit(feature_error_handler)

def write_report(filename: str, content, context=None, filetype='md', feature=None, item_name='Report'):
    """
    Unified report writing utility for Markdown and JSON. Handles error logging, context, and uses centralized messages.
    Args:
        filename (str): Output file path.
        content (str or dict): Content to write. If filetype is 'json', must be dict.
        context (dict, optional): Context for logging.
        filetype (str): 'md' for Markdown, 'json' for JSON.
        feature (str, optional): Feature name for logging.
        item_name (str): Human-readable name for the report/item being written.
    Returns:
        None. Writes file to disk and logs success or error.
    """
    ctx = context or {}
    try:
        if filetype == 'json':
            with open(filename, 'w') as f:
                json.dump(content, f, indent=2)
        else:
            with open(filename, 'w') as f:
                f.write(content)
        info(WRITTEN_TO.format(item=item_name, filename=filename), extra=ctx, feature=feature)
        from jirassicpack.utils.logging import contextual_log
        contextual_log('info', f"🛠️ [Utils] {item_name} written: {filename}", operation="output_write", output_file=filename, status="success", extra=ctx, feature=feature)
    except Exception as e:
        error(FAILED_TO.format(action=f'write {item_name.lower()}', error=e), extra=ctx, feature=feature)
        from jirassicpack.utils.logging import contextual_log
        contextual_log('error', f"🛠️ [Utils] Failed to write {item_name.lower()}: {e}", operation="output_write", output_file=filename, status="error", error_type=type(e).__name__, extra=ctx, feature=feature)
write_report = log_entry_exit(write_report)

# Optionally, refactor write_output_file to use write_report
write_output_file = write_report

def prompt_with_schema(schema, data, field_prompt_map=None, jira=None):
    """
    Prompt for and validate options using a Marshmallow schema. Prompts for missing/invalid fields using get_option.
    Args:
        schema: Marshmallow schema instance.
        data: Initial data dict.
        field_prompt_map: Optional dict mapping field names to prompt kwargs (prompt, choices, etc).
        jira: Optional Jira client for custom field selection.
    Returns:
        dict: Validated options dict, or None if user aborts.
    """
    field_prompt_map = field_prompt_map or {}
    while True:
        try:
            validated = schema.load(data)
            return validated
        except ValidationError as err:
            for field, msgs in err.messages.items():
                suggestion = None
                if isinstance(msgs, list) and msgs and isinstance(msgs[0], tuple):
                    message, suggestion = msgs[0]
                elif isinstance(msgs, list) and msgs:
                    message = msgs[0]
                else:
                    message = str(msgs)
                prompt_kwargs = field_prompt_map.get(field, {})
                # Custom Jira-aware field selection logic
                if jira and field == 'user':
                    from jirassicpack.utils.jira import select_jira_user
                    label, user_obj = select_jira_user(jira)
                    data['user'] = user_obj.get('accountId') if user_obj else ''
                elif jira and field == 'team':
                    from jirassicpack.utils.jira import select_jira_user
                    label_user_tuples = select_jira_user(jira, allow_multiple=True)
                    users = [u.get('accountId') for _, u in label_user_tuples if u and u.get('accountId')]
                    data['team'] = ','.join(users)
                else:
                    data[field] = get_option(data, field, **prompt_kwargs)
                rich_error(f"Input validation error for '{field}': {message}", suggestion)
            # Optionally, allow user to abort here
            # if prompt_select('Continue?', ['Retry', 'Abort']) == 'Abort':
            #     return None
            continue
        except Exception as e:
            error(f"Unexpected error: {e}")
            return None 
prompt_with_schema = log_entry_exit(prompt_with_schema)

# --- Core Utilities (migrated from common.py) ---
def safe_get(dct, keys, default=None):
    """
    Safely get a nested value from a dict using a list of keys.
    Args:
        dct (dict): The dictionary to traverse.
        keys (list): List of keys to traverse.
        default: Value to return if any key is missing.
    Returns:
        The value at the nested key, or default if not found.
    """
    val = dct
    for key in keys:
        if isinstance(val, dict) and key in val:
            val = val[key]
        else:
            return default
    return val
safe_get = log_entry_exit(safe_get)

def ensure_output_dir(output_dir):
    """
    Ensure the output directory exists.
    Args:
        output_dir (str): Path to the output directory.
    """
    os.makedirs(output_dir, exist_ok=True)
ensure_output_dir = log_entry_exit(ensure_output_dir)

def _select_from_list(
    items,
    message="Select an item:",
    display_fn=None,
    multi=False,
    page_size=15,
    fuzzy_threshold=30,
    allow_abort=True,
    style=DEFAULT_PROMPT_STYLE
):
    """
    Always returns only serializable values (e.g., str, int) for both single and multi-select.
    For multi-select, returns a list of values. For single-select, returns a value.
    """
    display_fn = display_fn or (lambda x: str(x))
    # If items are dicts with 'name' and 'value', use questionary.Choice
    if items and isinstance(items[0], dict) and 'name' in items[0] and 'value' in items[0]:
        choices = [Choice(title=item['name'], value=item['value']) for item in items]
    else:
        choices = [display_fn(item) for item in items]
    if allow_abort:
        abort_label = "❌ Abort"
        choices = choices + [abort_label]
    if multi:
        picked = questionary.checkbox(message, choices=choices, style=style).ask()
        # Extract .value if Choice objects are returned
        if picked and isinstance(picked[0], Choice):
            picked = [p.value for p in picked]
        if allow_abort and abort_label in picked:
            return None
        # Always return a list of serializable values
        if items and isinstance(items[0], dict) and 'name' in items[0] and 'value' in items[0]:
            return picked
        return [items[choices.index(p)] for p in picked if p != abort_label]
    if len(choices) > fuzzy_threshold:
        # If choices are Choice objects, use their titles for display
        display_map = {}
        display_choices = []
        for choice in choices:
            if isinstance(choice, Choice):
                display_map[choice.title] = choice.value
                display_choices.append(choice.title)
            else:
                display_map[choice] = choice
                display_choices.append(choice)
        if allow_abort and abort_label not in display_choices:
            display_choices.append(abort_label)
        picked = inquirer.fuzzy(message=message, choices=display_choices, max_height="70%", style=INQUIRERPY_STYLE).execute()
        if allow_abort and picked == abort_label:
            return None
        # Always return the value (serializable)
        return display_map.get(picked, picked)
    elif len(choices) > page_size:
        page = 0
        total_pages = (len(choices) - 1) // page_size + 1
        while True:
            start = page * page_size
            end = start + page_size
            page_choices = choices[start:end]
            nav = []
            if page > 0:
                nav.append("⬅️ Previous page")
            if end < len(choices):
                nav.append("➡️ Next page")
            nav.append("🔤 Jump to letter")
            nav.append("🔢 Jump to page")
            if allow_abort:
                nav.append(abort_label)
            selection = questionary.select(f"{message} (Page {page+1}/{total_pages})", choices=page_choices + nav, style=style).ask()
            if isinstance(selection, Choice):
                selection = selection.value
            if selection == "⬅️ Previous page":
                page -= 1
            elif selection == "➡️ Next page":
                page += 1
            elif selection == "🔢 Jump to page":
                page = int(prompt_text("Enter page number:", default=str(page+1))) - 1
            elif selection == "🔤 Jump to letter":
                letter = prompt_text("Type a letter to jump:")
                idx = next((index for index, choice in enumerate(choices) if isinstance(choice, str) and choice.lower().startswith(letter.lower())), None)
                if idx is not None:
                    page = idx // page_size
                else:
                    info("No items found for that letter.")
            elif allow_abort and selection == abort_label:
                return None
            else:
                # Always return the value (serializable)
                if items and isinstance(items[0], dict) and 'name' in items[0] and 'value' in items[0]:
                    return selection
                return items[choices.index(selection)]
    else:
        picked = questionary.select(message, choices=choices, style=style).ask()
        if isinstance(picked, Choice):
            picked = picked.value
        if allow_abort and picked == abort_label:
            return None
        # Always return the value (serializable)
        if items and isinstance(items[0], dict) and 'name' in items[0] and 'value' in items[0]:
            return picked
        return items[choices.index(picked)]

select_from_list = _select_from_list 