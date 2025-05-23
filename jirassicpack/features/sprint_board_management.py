"""
sprint_board_management.py

Feature module for summarizing the state of a Jira board and its sprints via the CLI.
Prompts for board and sprint name, fetches board/sprint/issue data, and outputs a Markdown report for review or sharing.
"""

from typing import Any, Dict
from jirassicpack.utils.output_utils import ensure_output_dir, celebrate_success, write_report
from jirassicpack.utils.message_utils import retry_or_skip, info, error
from jirassicpack.utils.validation_utils import prompt_with_schema
from jirassicpack.utils.decorators import feature_error_handler
from jirassicpack.utils.progress_utils import spinner
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
import time
from marshmallow import fields
from jirassicpack.utils.fields import BaseOptionsSchema
from jirassicpack.constants import SEE_NOBODY_CARES, FAILED_TO, REPORT_WRITE_ERROR
from jirassicpack.analytics.helpers import build_report_sections

class SprintBoardManagementOptionsSchema(BaseOptionsSchema):
    """
    Marshmallow schema for validating sprint/board management options.
    Fields: board_name, sprint_name.
    """
    board_name = fields.Str(required=True, error_messages={"required": "Board name is required."})
    sprint_name = fields.Str(required=True, error_messages={"required": "Sprint name is required."})
    # output_dir and unique_suffix are inherited

def prompt_sprint_board_options(opts: dict, jira: Any = None) -> dict:
    """
    Prompt for sprint/board management options using Marshmallow schema for validation.

    Args:
        opts (dict): Initial options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.

    Returns:
        dict: Validated options for the feature, or None if aborted.
    """
    schema = SprintBoardManagementOptionsSchema()
    result = prompt_with_schema(schema, dict(opts), jira=jira, abort_option=True)
    if result == "__ABORT__":
        info("❌ Aborted sprint/board management prompt.")
        return None
    return result

def write_sprint_board_file(filename: str, board_name: str, sprints: list, issues: list, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
    """
    Write the sprint/board summary to a Markdown file using write_report for robust file writing and logging.
    Args:
        filename (str): Output file path.
        board_name (str): Name of the board.
        sprints (list): List of sprints.
        issues (list): List of issues in the active sprint.
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
        context (dict, optional): Additional context for logging.
    Returns:
        None. Writes a Markdown report to disk.
    """
    try:
        summary_section = f"**Board:** {board_name}\n\n**Total Sprints:** {len(sprints)}\n\n**Total Issues in Active Sprint:** {len(issues)}"
        details_section = "## Sprints\n"
        for sprint in sprints:
            details_section += f"- {sprint.get('name', 'N/A')} (State: {sprint.get('state', 'N/A')})\n"
        details_section += "\n## Issues in Active Sprint\n"
        for issue in issues:
            key = issue.get('key', 'N/A')
            fields = issue.get('fields', {})
            summary = fields.get('summary', 'N/A')
            details_section += f"- {key}: {summary}\n"
        content = build_report_sections({
            'header': f"# 🏁 Sprint/Board Summary\n\n**Board:** {board_name}",
            'summary': summary_section,
            'grouped_sections': details_section,
        })
        write_report(filename, content, context, filetype='md', feature='sprint_board_management', item_name='Sprint/Board summary report')
        info(f"🌋 Sprint/Board summary written to {filename}", extra=context, feature='sprint_board_management')
    except Exception as e:
        error(REPORT_WRITE_ERROR.format(error=e), extra=context, feature='sprint_board_management')

def generate_sprint_summary(sprint: Any) -> Dict[str, Any]:
    """
    Generate a summary dictionary for a sprint. This is a placeholder for actual summary logic.
    """
    return {
        'key': sprint.get('id', 'N/A'),
        'fields': {
            'summary': sprint.get('name', 'N/A') + f" (State: {sprint.get('state', 'N/A')})"
        }
    }

@feature_error_handler('sprint_board_management')
def sprint_board_management(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Main feature entrypoint for managing Jira sprint boards. Handles validation, sprint actions, and report writing.

    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the sprint (board, action, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.

    Returns:
        None. Writes a Markdown report to disk.
    """
    correlation_id = params.get('correlation_id')
    context = build_context("sprint_board_management", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    try:
        contextual_log('info', f"🏁 [Sprint/Board Management] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='sprint_board_management')
        # Patch JiraClient for logging
        orig_get = getattr(jira, 'get', None)
        if orig_get:
            def log_get(*args, **kwargs):
                contextual_log('debug', f"Jira GET: args={args}, kwargs={redact_sensitive(kwargs)}", extra=context, feature='sprint_board_management')
                resp = orig_get(*args, **kwargs)
                contextual_log('debug', f"Jira GET response: {resp}", extra=context, feature='sprint_board_management')
                return resp
            jira.get = log_get
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        board_name = params.get('board_name')
        if not board_name:
            error("board_name is required.", extra=context, feature='sprint_board_management')
            return
        sprint_name = params.get('sprint_name')
        if not sprint_name:
            error("sprint_name is required.", extra=context, feature='sprint_board_management')
            return
        ensure_output_dir(output_dir)
        def do_manage():
            with spinner("🌋 Running Sprint Board Management..."):
                boards = jira.list_boards(name=board_name)
                if not boards:
                    raise Exception(f"No board found with name '{board_name}'")
                board = boards[0]
                sprints = jira.list_sprints(board['id'])
                sprint = next((s for s in sprints if s.get('name') == sprint_name), None)
                if not sprint:
                    raise Exception(f"No sprint found with name '{sprint_name}' on board '{board_name}'")
                summary = generate_sprint_summary(sprint)
                return board, sprint, summary
        try:
            result = retry_or_skip(f"Managing sprint '{sprint_name}' on board '{board_name}'", do_manage)
        except Exception as e:
            error(FAILED_TO.format(action='fetch board or sprint data', error=e), extra=context, feature='sprint_board_management')
            contextual_log('error', f"[sprint_board_management] Failed to fetch board or sprint data: {e}", exc_info=True, extra=context, feature='sprint_board_management')
            return
        if not result:
            info(SEE_NOBODY_CARES, extra=context, feature='sprint_board_management')
            return
        board, sprint, summary = result
        filename = f"{output_dir}/sprint_board_{board_name}_{sprint_name}{unique_suffix}.md"
        try:
            write_sprint_board_file(filename, board_name, [sprint], [summary], user_email, batch_index, unique_suffix, context=context)
        except Exception as e:
            error(f"Failed to write sprint board file: {e}. Check if the directory '{output_dir}' exists and is writable.", extra=context, feature='sprint_board_management')
            contextual_log('error', f"[sprint_board_management] Failed to write sprint board file: {e}", exc_info=True, extra=context, feature='sprint_board_management')
            return
        celebrate_success()
        info(f"🌋 Sprint/Board summary written to {filename}", extra=context, feature='sprint_board_management')
        duration = int((time.time() - start_time) * 1000)
        contextual_log('info', f"🏁 [Sprint/Board Management] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}).", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='sprint_board_management')
    except KeyboardInterrupt:
        contextual_log('warning', "[sprint_board_management] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context, feature='sprint_board_management')
        info("Graceful exit from Sprint Board Management feature.", extra=context, feature='sprint_board_management')
    except Exception as e:
        contextual_log('error', f"🏁 [Sprint/Board Management] Exception occurred: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='sprint_board_management')
        error(f"[sprint_board_management] Exception: {e}", extra=context, feature='sprint_board_management')
        raise 