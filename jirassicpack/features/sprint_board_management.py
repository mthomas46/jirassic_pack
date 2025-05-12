# sprint_board_management.py
# This feature summarizes the state of a Jira board, including all sprints and issues in the active sprint.
# It prompts for the board name, fetches board/sprint/issue data, and outputs a Markdown report for review or sharing.

from typing import Any, Dict, List
from jirassicpack.cli import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, logger
from jirassicpack.utils import error, info, spinner, info_spared_no_expense, prompt_with_validation, build_context, render_markdown_report, redact_sensitive, get_option, select_board_name, select_sprint_name, contextual_log
import time

def prompt_sprint_board_management_options(options: Dict[str, Any], jira=None) -> Dict[str, Any]:
    """
    Prompt for sprint board options using get_option utility.
    Prompts for the board name, sprint name, and output directory.
    Returns a dictionary of all options needed for the board summary.
    """
    board_name = options.get('board_name')
    board_id = None
    if not board_name and jira:
        # Use select_board_name and also get the board_id
        while True:
            board_name = select_board_name(jira)
            if not board_name:
                continue
            boards = jira.list_boards(name=board_name)
            for b in boards:
                if b.get('name') == board_name:
                    board_id = b.get('id')
                    break
            if board_id:
                break
            info(f"No board found with name '{board_name}'. Please try again.", feature='sprint_board_management')
    elif not board_name:
        board_name = get_option(options, 'board_name', prompt="Jira Board Name:", required=True)
    else:
        # If board_name is provided, try to get board_id
        if jira:
            boards = jira.list_boards(name=board_name)
            for b in boards:
                if b.get('name') == board_name:
                    board_id = b.get('id')
                    break
    sprint_name = options.get('sprint_name')
    if not sprint_name and jira:
        sprint_name = select_sprint_name(jira, board_name, board_id)
    elif not sprint_name:
        sprint_name = get_option(options, 'sprint_name', prompt="Sprint Name:", required=True)
    output_dir = get_option(options, 'output_dir', default='output')
    unique_suffix = options.get('unique_suffix', '')
    return {
        'board_name': board_name,
        'sprint_name': sprint_name,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix
    }

def write_sprint_board_file(filename: str, board_name: str, sprints: list, issues: list, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
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
        content = render_markdown_report(
            feature="sprint_board_management",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="Sprint Board Management",
            summary_section=summary_section,
            main_content_section=details_section
        )
        with open(filename, 'w') as f:
            f.write(content)
        info(f"🌋 Sprint/Board summary written to {filename}", extra=context, feature='sprint_board_management')
    except Exception as e:
        error(f"Failed to write sprint board file: {e}. Check if the directory '{filename}' exists and is writable.", extra=context, feature='sprint_board_management')

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

def sprint_board_management(jira: Any, params: Dict[str, Any], user_email=None, batch_index=None, unique_suffix=None) -> None:
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
                board = jira.board(board_name)
                sprint = jira.sprint(sprint_name, board.id)
                summary = generate_sprint_summary(sprint)
                return board, sprint, summary
        try:
            result = retry_or_skip(f"Managing sprint '{sprint_name}' on board '{board_name}'", do_manage)
        except Exception as e:
            error(f"Failed to fetch board or sprint data: {e}. Please check your Jira connection, credentials, and network.", extra=context, feature='sprint_board_management')
            contextual_log('error', f"[sprint_board_management] Failed to fetch board or sprint data: {e}", exc_info=True, extra=context, feature='sprint_board_management')
            return
        if not result:
            info("🦖 See, Nobody Cares. No board or sprint data found.", extra=context, feature='sprint_board_management')
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
        info_spared_no_expense()
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