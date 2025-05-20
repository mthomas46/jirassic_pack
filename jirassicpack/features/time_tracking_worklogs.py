# time_tracking_worklogs.py
# This feature summarizes worklogs for a given Jira user and timeframe.
# It prompts for user, start/end dates, fetches issues with worklogs, and outputs a Markdown report with worklog details per issue.

from jirassicpack.utils.io import ensure_output_dir, celebrate_success, retry_or_skip, info, validate_date, error, spinner, info_spared_no_expense, safe_get, require_param, feature_error_handler, prompt_with_schema, write_report
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from datetime import datetime
from typing import Any, Dict, List
import time
from jirassicpack.utils.fields import BaseOptionsSchema, validate_nonempty
from marshmallow import fields
from collections import Counter
from jirassicpack.analytics.helpers import build_report_sections, aggregate_issue_stats, make_summary_section, make_top_n_list
from jirassicpack.constants import NO_WORKLOGS_FOUND, REPORT_WRITE_ERROR

# Module-level cache for Jira users
_CACHED_JIRA_USERS = None

class TimeTrackingOptionsSchema(BaseOptionsSchema):
    user = fields.Str(required=True, error_messages={"required": "User is required."}, validate=validate_nonempty)
    start_date = fields.Str(required=True, error_messages={"required": "Start date is required."}, validate=validate_date)
    end_date = fields.Str(required=True, error_messages={"required": "End date is required."}, validate=validate_date)
    # output_dir and unique_suffix are inherited

def prompt_worklog_options(opts: dict, jira: Any = None) -> dict:
    """
    Prompt for worklog options using Marshmallow schema for validation.

    Args:
        opts (dict): Initial options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.

    Returns:
        dict: Validated options for the feature, or None if aborted.
    """
    schema = TimeTrackingOptionsSchema()
    result = prompt_with_schema(schema, dict(opts), jira=jira, abort_option=True)
    if result == "__ABORT__":
        info("❌ Aborted worklog options prompt.")
        return None
    return result

def write_worklog_summary_file(filename: str, user: str, start_date: str, end_date: str, issues: list, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
    """
    Write a Markdown file for worklog summary using build_report_sections for robust file writing and logging.
    Args:
        filename (str): Output file path.
        user (str): User for whom the worklog is summarized.
        start_date (str): Start date.
        end_date (str): End date.
        issues (list): List of issues.
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
        context (dict, optional): Additional context for logging.
    Returns:
        None. Writes a Markdown report to disk.
    """
    try:
        # Header
        header = "# ⏳ Worklog Summary Report\n\n"
        header += "**Feature:** Time Tracking & Worklogs  "
        header += f"**User:** {user}  "
        header += f"**Timeframe:** {start_date} to {end_date}  "
        header += f"**Total Issues with Worklogs:** {len(issues)}  "
        header += "\n\n---\n\n"
        # Aggregate stats
        stats = aggregate_issue_stats(issues)
        summary = make_summary_section(stats)
        # Action items: highlight issues with no worklog
        no_worklog = [i for i in issues if not safe_get(i, ['fields', 'worklog', 'worklogs'])]
        action_items = "## Action Items\n"
        if no_worklog:
            action_items += "### Issues with No Worklog\n"
            for issue in no_worklog:
                key = issue.get('key', '')
                summary_ = safe_get(issue, ['fields', 'summary'], '')[:40]
                action_items += f"- ⚠️ [{key}] {summary_}\n"
        else:
            action_items += "All issues have worklogs.\n"
        # Top N users by worklog hours
        user_worklog_totals = Counter()
        for issue in issues:
            worklogs = safe_get(issue, ['fields', 'worklog', 'worklogs'], [])
            for worklog in worklogs:
                author = safe_get(worklog, ['author', 'displayName'], 'N/A')
                user_worklog_totals[author] += worklog.get('timeSpentSeconds', 0)
        top_n = [(name, round(seconds / 3600, 2)) for name, seconds in user_worklog_totals.most_common(5)]
        top_n_lists = make_top_n_list(top_n, "Top 5 Users by Worklog Hours")
        # Grouped issue section (detailed worklogs)
        grouped_section = "## Worklog Details\n\n"
        grouped_section += "| Issue Key | Summary | Worklog Author | Time Spent (h) | Started | Comment |\n|---|---|---|---|---|---|\n"
        for issue in issues:
            key = issue.get('key', 'N/A')
            summary_ = safe_get(issue, ['fields', 'summary'], 'N/A')[:40]
            worklogs = safe_get(issue, ['fields', 'worklog', 'worklogs'], [])
            for worklog in worklogs:
                author = safe_get(worklog, ['author', 'displayName'], 'N/A')
                time_spent = round(worklog.get('timeSpentSeconds', 0) / 3600, 2)
                started = worklog.get('started', '')
                comment = worklog.get('comment', '')
                grouped_section += f"| {key} | {summary_} | {author} | {time_spent} | {started} | {comment} |\n"
        # Export metadata
        export_metadata = f"---\n**Report generated by:** {user_email}  \n**Run at:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n"
        # Glossary
        glossary = "## Glossary\n- ⚠️ No worklog\n"
        # Next steps
        next_steps = "## Next Steps\n- Review issues with missing worklogs.\n- Investigate outliers in worklog hours.\n"
        # Compose final report using build_report_sections
        sections = {
            'header': header,
            'summary': summary,
            'action_items': action_items,
            'top_n': top_n_lists,
            'grouped_sections': grouped_section,
            'metadata': export_metadata,
            'glossary': glossary,
            'next_steps': next_steps,
        }
        report = build_report_sections(sections)
        write_report(filename, report, context, filetype='md', feature='time_tracking_worklogs', item_name='Worklog summary report')
        info(f"⏳ Worklog summary written to {filename}", extra=context, feature='time_tracking_worklogs')
    except Exception as e:
        error(REPORT_WRITE_ERROR.format(error=e), extra=context, feature='time_tracking_worklogs')

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
        for worklog in fields.get('worklog', {}).get('worklogs', []):
            wl_date = worklog.get('started', '')[:10]
            try:
                wl_dt = datetime.strptime(wl_date, "%Y-%m-%d")
                if start <= wl_dt <= end:
                    filtered_worklogs.append(worklog)
            except Exception:
                continue
        if filtered_worklogs:
            filtered_issue = dict(issue)
            filtered_issue['fields'] = dict(fields)
            filtered_issue['fields']['worklog'] = {'worklogs': filtered_worklogs}
            filtered_issues.append(filtered_issue)
    return filtered_issues

@feature_error_handler('time_tracking_worklogs')
def time_tracking_worklogs(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Main feature entrypoint for time tracking and worklog analytics. Handles validation, fetching, and report writing.

    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the time tracking (user, date range, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.

    Returns:
        None. Writes a Markdown report to disk.
    """
    correlation_id = params.get('correlation_id')
    context = build_context("time_tracking_worklogs", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    try:
        contextual_log('info', f"⏳ [time_tracking_worklogs] Feature entry | User: {user_email} | Params: {redact_sensitive(params)} | Suffix: {unique_suffix}", operation="feature_start", params=redact_sensitive(params), status="started", extra=context, feature='time_tracking_worklogs')
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
                contextual_log('debug', f"Jira GET: args={args}, kwargs={redact_sensitive(kwargs)}", extra=context, feature='time_tracking_worklogs')
                resp = orig_get(*args, **kwargs)
                contextual_log('debug', f"Jira GET response: {resp}", extra=context, feature='time_tracking_worklogs')
                return resp
            jira.get = log_get
        jql = (
            f"worklogAuthor = '{user}' "
            f"AND worklogDate >= '{start_date}' "
            f"AND worklogDate <= '{end_date}'"
        )
        info(f"[DEBUG] Using JQL: {jql}")
        info(f"[DEBUG] Using user: {user}")
        contextual_log('debug', f"[DEBUG] Using JQL: {jql}", extra=context, feature='time_tracking_worklogs')
        contextual_log('debug', f"[DEBUG] Using user: {user}", extra=context, feature='time_tracking_worklogs')
        def do_worklogs():
            with spinner("⏳ Running Time Tracking Worklogs..."):
                issues = jira.search_issues(jql, fields=["worklog", "key", "summary"], max_results=100)
                return generate_worklog_summary(issues, start_date, end_date)
        filtered_issues = retry_or_skip("Generating worklog summary from Jira issues", do_worklogs)
        if not filtered_issues:
            info(NO_WORKLOGS_FOUND, extra={**context, "feature": "time_tracking_worklogs"})
            return
        filename = f"{output_dir}/worklog_summary{unique_suffix}.md"
        write_worklog_summary_file(filename, user, start_date, end_date, filtered_issues, user_email, batch_index, unique_suffix, context)
        celebrate_success()
        info_spared_no_expense()
        duration = int((time.time() - start_time) * 1000)
        contextual_log('info', f"⏳ [time_tracking_worklogs] Feature complete | Suffix: {unique_suffix}", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='time_tracking_worklogs')
    except KeyboardInterrupt:
        contextual_log('warning', "[time_tracking_worklogs] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context, feature='time_tracking_worklogs')
        info("Graceful exit from Time Tracking Worklogs feature.", extra={**context, "feature": "time_tracking_worklogs"})
    except Exception as e:
        contextual_log('error', f"[time_tracking_worklogs] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='time_tracking_worklogs')
        error(f"[time_tracking_worklogs] Exception: {e}", extra={**context, "feature": "time_tracking_worklogs"})
        raise 