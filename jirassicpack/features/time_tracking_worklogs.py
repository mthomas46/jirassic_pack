# time_tracking_worklogs.py
# This feature summarizes worklogs for a given Jira user and timeframe.
# It prompts for user, start/end dates, fetches issues with worklogs, and outputs a Markdown report with worklog details per issue.

from jirassicpack.cli import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, logger, redact_sensitive
from jirassicpack.utils import prompt_with_validation, get_option, validate_required, validate_date, error, info, spinner, info_spared_no_expense, safe_get, build_context, write_markdown_file, require_param, render_markdown_report, contextual_log
from datetime import datetime
from typing import Any, Dict, List

def prompt_time_tracking_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prompt for time tracking options using get_option utility.
    Prompts for user, start date, and end date.
    Returns a dictionary of all options needed for the worklog summary.
    """
    user = get_option(options, 'user', prompt="Jira Username for worklogs:", required=True)
    start_date = get_option(options, 'start_date', prompt="Start date (YYYY-MM-DD):", default='2024-01-01', required=True, validate=validate_date)
    end_date = get_option(options, 'end_date', prompt="End date (YYYY-MM-DD):", default='2024-01-31', required=True, validate=validate_date)
    output_dir = get_option(options, 'output_dir', default='output')
    unique_suffix = options.get('unique_suffix', '')
    return {
        'user': user,
        'start_date': start_date,
        'end_date': end_date,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix
    }

def write_worklog_summary_file(filename: str, user: str, start_date: str, end_date: str, issues: list, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
    try:
        summary_section = f"**User:** {user}\n\n**Timeframe:** {start_date} to {end_date}\n\n**Total Issues with Worklogs:** {len(issues)}"
        details_section = ""
        for issue in issues:
            key = issue.get('key', 'N/A')
            summary = safe_get(issue, ['fields', 'summary'], 'N/A')
            worklogs = safe_get(issue, ['fields', 'worklog', 'worklogs'], [])
            details_section += f"\n### {key}: {summary}\n"
            if not worklogs:
                details_section += "No worklogs found.\n"
            for wl in worklogs:
                author = safe_get(wl, ['author', 'displayName'], 'Unknown')
                started = safe_get(wl, ['started'], 'N/A')
                time_spent = safe_get(wl, ['timeSpent'], 'N/A')
                details_section += f"- {author}: {time_spent} on {started}\n"
        content = render_markdown_report(
            feature="time_tracking_worklogs",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="Time Tracking & Worklogs",
            summary_section=summary_section,
            main_content_section=details_section
        )
        with open(filename, 'w') as f:
            f.write(content)
        info(f"⏳ Worklog summary written to {filename}", extra=context)
    except Exception as e:
        error(f"Failed to write worklog summary file: {e}", extra=context)

def generate_worklog_summary(issues: List[Dict[str, Any]], start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    Filter worklogs in issues by date range. Returns filtered issues with worklogs in range.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    filtered_issues = []
    for issue in issues:
        fields = issue.get('fields', {})
        filtered_worklogs = []
        for wl in fields.get('worklog', {}).get('worklogs', []):
            wl_date = wl.get('started', '')[:10]
            try:
                wl_dt = datetime.strptime(wl_date, "%Y-%m-%d")
                if start <= wl_dt <= end:
                    filtered_worklogs.append(wl)
            except Exception:
                continue
        if filtered_worklogs:
            filtered_issue = dict(issue)
            filtered_issue['fields'] = dict(fields)
            filtered_issue['fields']['worklog'] = {'worklogs': filtered_worklogs}
            filtered_issues.append(filtered_issue)
    return filtered_issues

def time_tracking_worklogs(jira: Any, params: Dict[str, Any], user_email=None, batch_index=None, unique_suffix=None) -> None:
    context = build_context("time_tracking_worklogs", user_email, batch_index, unique_suffix)
    if not require_param(params, 'user', context):
        return
    if not require_param(params, 'start_date', context):
        return
    if not require_param(params, 'end_date', context):
        return
    user = params.get('user')
    start_date = params.get('start_date')
    end_date = params.get('end_date')
    output_dir = params.get('output_dir', 'output')
    unique_suffix = params.get('unique_suffix', '')
    ensure_output_dir(output_dir)
    orig_get = getattr(jira, 'get', None)
    if orig_get:
        def log_get(*args, **kwargs):
            contextual_log('debug', f"Jira GET: args={args}, kwargs={redact_sensitive(kwargs)}", extra=context)
            resp = orig_get(*args, **kwargs)
            contextual_log('debug', f"Jira GET response: {resp}", extra=context)
            return resp
        jira.get = log_get
    jql = (
        f"worklogAuthor = '{user}' "
        f"AND worklogDate >= '{start_date}' "
        f"AND worklogDate <= '{end_date}'"
    )
    def do_worklogs():
        with spinner("⏳ Running Time Tracking Worklogs..."):
            issues = jira.search_issues(jql, fields=["worklog", "key", "summary"], max_results=100)
            return generate_worklog_summary(issues, start_date, end_date)
    try:
        filtered_issues = retry_or_skip("Generating worklog summary from Jira issues", do_worklogs)
    except Exception as e:
        error(f"Failed to fetch worklogs: {e}. Please check your Jira connection, credentials, and network.", extra=context)
        contextual_log('error', f"[time_tracking_worklogs] Failed to fetch worklogs: {e}", exc_info=True, extra=context)
        return
    if not filtered_issues:
        info("🦖 See, Nobody Cares. No worklogs found.", extra=context)
        return
    filename = f"{output_dir}/worklog_summary{unique_suffix}.md"
    write_worklog_summary_file(filename, user, start_date, end_date, filtered_issues, user_email, batch_index, unique_suffix, context)
    celebrate_success()
    info_spared_no_expense()
    contextual_log('info', f"⏳ [time_tracking_worklogs] Feature complete | Suffix: {unique_suffix}", extra=context) 