"""
Output and reporting utilities for Jirassic Pack CLI.
Handles pretty-printing, report writing, markdown rendering, and output directory management.
"""
import os
import json
from datetime import datetime
from jirassicpack.utils.rich_prompt import rich_panel, rich_info, rich_error, rich_success
from jirassicpack.constants import WRITTEN_TO, FAILED_TO
from jirassicpack.utils.logging import contextual_log

def pretty_print_result(result):
    """
    Pretty-prints a result object as formatted JSON in a rich panel.
    Args:
        result (Any): The object to print.
    """
    rich_panel(json.dumps(result, indent=2), style="info")

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
        rich_success(WRITTEN_TO.format(item=item_name, filename=filename))
        contextual_log('info', f"🛠️ [Utils] {item_name} written: {filename}", operation="output_write", output_file=filename, status="success", extra=ctx, feature=feature)
    except Exception as e:
        rich_error(FAILED_TO.format(action=f'write {item_name.lower()}', error=e))
        contextual_log('error', f"🛠️ [Utils] Failed to write {item_name.lower()}: {e}", operation="output_write", output_file=filename, status="error", error_type=type(e).__name__, extra=ctx, feature=feature)

def render_markdown_report_template(template: str, context: dict) -> str:
    """
    Render a Markdown report template with context variables.
    Args:
        template (str): Markdown template string with {placeholders}.
        context (dict): Dictionary of values to substitute.
    Returns:
        str: Rendered Markdown string.
    """
    return template.format(**context)

def ensure_output_dir(output_dir):
    """
    Ensure the output directory exists.
    Args:
        output_dir (str): Path to the output directory.
    """
    os.makedirs(output_dir, exist_ok=True)

def make_output_filename(feature, params, output_dir='output', ext='md'):
    """
    Build a human-readable output filename for reports.
    - feature: string, e.g. 'metrics', 'create_issue'
    - params: ordered list of (param_name, value) tuples
    - output_dir: directory for output files
    - ext: file extension (default 'md')
    Returns: full path to the output file
    """
    import re
    def sanitize(val):
        return re.sub(r'[^\w\-]', '', str(val).replace(' ', '_'))
    def prettify_param(k, v):
        if isinstance(v, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            v = v.replace('-', '')
        if k in ("summary", "title") and isinstance(v, str):
            v = v[:20]
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

def print_section_header(header: str):
    rich_panel(header, style="info")

def print_batch_summary(results):
    rich_panel("🦖 Batch Summary:", style="info")
    rich_info("Feature         | Status")
    rich_info("----------------|--------")
    for name, status in results:
        color = "success" if status == "Success" else "error"
        rich_info(f"{name:<15} | [{{color}}]{status}[/{{color}}]")

def celebrate_success() -> None:
    print("\033[38;5;34m🎉 Success! 🎉\033[0m") 