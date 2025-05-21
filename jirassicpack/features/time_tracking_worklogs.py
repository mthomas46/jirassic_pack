"""
time_tracking_worklogs.py

Feature module for summarizing Jira worklogs for one or more users and a timeframe via the CLI.
Prompts for user(s) and date range, fetches issues with worklogs, and outputs a Markdown report with worklog details and analytics.
"""

# time_tracking_worklogs.py
# This feature summarizes worklogs for a given Jira user and timeframe.
# It prompts for user, start/end dates, fetches issues with worklogs, and outputs a Markdown report with worklog details per issue.

from jirassicpack.utils.output_utils import ensure_output_dir, celebrate_success, write_report
from jirassicpack.utils.message_utils import retry_or_skip, info, error
from jirassicpack.utils.validation_utils import get_option, safe_get, require_param
from jirassicpack.utils.decorators import feature_error_handler
from jirassicpack.utils.progress_utils import spinner
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from datetime import datetime
from typing import Any, Dict, List
import time
from jirassicpack.utils.fields import validate_date
from collections import Counter
from jirassicpack.analytics.helpers import build_report_sections, aggregate_issue_stats, make_summary_section, make_top_n_list, make_breakdown_section, make_markdown_table
from jirassicpack.constants import NO_WORKLOGS_FOUND, REPORT_WRITE_ERROR
from jirassicpack.utils.jira import select_jira_user

# Module-level cache for Jira users
_CACHED_JIRA_USERS = None

def prompt_worklog_options(opts: dict, jira: Any = None) -> dict:
    """
    Prompt for worklog options, always requiring explicit user selection. Config/env value is only used if the user selects it.
    Args:
        opts (dict): Options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.
    Returns:
        dict: Validated options for the feature.
    """
    info(f"[DEBUG] prompt_worklog_options called. jira is {'present' if jira else 'None'}. opts: {opts}")
    users = []
    if jira:
        info("Please select Jira user(s) for worklog summary.")
        label_user_tuples = select_jira_user(jira, allow_multiple=True)
        if not label_user_tuples:
            info("Aborted or cleared user selection.")
            return None
        info(f"[time_tracking_worklogs] Used fuzzy multi-select for user selection. Selected: {[label for label, _ in label_user_tuples]}")
        users = [user_obj.get('accountId') for label, user_obj in label_user_tuples if user_obj and user_obj.get('accountId')]
        if not users:
            info("No valid users selected for worklog summary.")
            return None
    else:
        users = get_option(opts, 'user', prompt="Jira user(s) (comma-separated accountIds):", required=True)
        if isinstance(users, str):
            users = [u.strip() for u in users.split(',') if u.strip()]
    start = get_option(opts, 'start_date', prompt="Start date (YYYY-MM-DD):", default='2024-01-01', required=True, validate=validate_date)
    end = get_option(opts, 'end_date', prompt="End date (YYYY-MM-DD):", default='2026-01-31', required=True, validate=validate_date)
    out_dir = get_option(opts, 'output_dir', default='output')
    suffix = opts.get('unique_suffix', '')
    return {
        'users': users,
        'start_date': start,
        'end_date': end,
        'output_dir': out_dir,
        'unique_suffix': suffix
    }

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
        params (dict): Parameters for the time tracking (users, date range, etc).
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
        users = params.get('users')
        if not users:
            error("users is required.", extra=context, feature='time_tracking_worklogs')
            return
        start_date = params.get('start_date')
        if not start_date:
            error("start_date is required.", extra=context, feature='time_tracking_worklogs')
            return
        end_date = params.get('end_date')
        if not end_date:
            error("end_date is required.", extra=context, feature='time_tracking_worklogs')
            return
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        ensure_output_dir(output_dir)
        user_display_map = {}
        all_user_data = {}
        for user in users:
            display_name = user
            try:
                user_obj = jira.get_user(account_id=user)
                display_name = user_obj.get('displayName', user)
            except Exception:
                pass
            user_display_map[user] = display_name
            user_jql = (
                f"worklogAuthor = '{user}' "
                f"AND worklogDate >= '{start_date}' "
                f"AND worklogDate <= '{end_date}'"
            )
            def do_user_worklogs():
                with spinner(f"⏳ Fetching worklogs for {display_name}..."):
                    return jira.search_issues(
                        user_jql,
                        fields=["key", "summary", "status", "issuetype", "priority", "created", "updated", "resolutiondate", "reporter", "labels", "issuelinks", "worklog"],
                        max_results=100
                    )
            issues = retry_or_skip(f"Fetching worklogs for {display_name}", do_user_worklogs)
            # Aggregate worklog analytics
            total_worklog_seconds = 0
            worklog_issue_count = 0
            for issue in issues or []:
                worklogs = safe_get(issue, ['fields', 'worklog', 'worklogs'], [])
                for wl in worklogs:
                    if wl.get('author', {}).get('accountId') == user:
                        total_worklog_seconds += wl.get('timeSpentSeconds', 0)
                        worklog_issue_count += 1
            # If no issues, set default summary
            if not issues:
                all_user_data[user] = {"issues": [], "summary": {
                    "status_counts": {},
                    "type_counts": {},
                    "priority_counts": {},
                    "avg_cycle": 'N/A',
                    "med_cycle": 'N/A',
                    "oldest": 'N/A',
                    "newest": 'N/A',
                    "total": 0,
                    "created": 0,
                    "resolved": 0,
                    "created_vs_resolved": 'N/A',
                    "blockers": [],
                    "critical": [],
                    "blocked": [],
                    "age_buckets": {"30d": 0, "60d": 0, "90d": 0},
                    "avg_unresolved_age": 'N/A',
                    "med_unresolved_age": 'N/A',
                    "linked": 0,
                    "blocking": [],
                    "blocked_by": [],
                    "reporters": {},
                    "unresolved_ages": [],
                    "worklog_hours": 0,
                    "worklog_issue_count": 0,
                }}
                continue
            summary = aggregate_issue_stats(issues)
            summary["worklog_hours"] = round(total_worklog_seconds / 3600, 2)
            summary["worklog_issue_count"] = worklog_issue_count
            all_user_data[user] = {
                "issues": issues,
                "summary": summary
            }
            info(f"[time_tracking_worklogs][DEBUG] Summary for user {user}: {summary}")
        if not any(len(data["issues"]) for data in all_user_data.values()):
            info("🦖 See, Nobody Cares. No worklog data found.", extra=context, feature='time_tracking_worklogs')
            contextual_log('info', "🦖 See, Nobody Cares. No worklog data found.", extra=context, feature='time_tracking_worklogs')
            return
        # Write expanded worklog analytics to Markdown
        filename = f"{output_dir}/worklog_summary{unique_suffix}.md"
        try:
            # Team summary aggregation (across all users)
            team_stats = {
                "total_issues": sum(len(data["issues"]) for data in all_user_data.values()),
                "worklog_hours": sum(data["summary"].get("worklog_hours", 0) for data in all_user_data.values()),
                "worklog_issue_count": sum(data["summary"].get("worklog_issue_count", 0) for data in all_user_data.values()),
            }
            summary_section = make_summary_section(team_stats)
            # Per-user sections
            grouped_sections = ""
            for user, data in all_user_data.items():
                summary = data["summary"]
                issues = data["issues"]
                display_name = user_display_map.get(user, user)
                grouped_sections += f"\n## {display_name} ({user})\n"
                grouped_sections += make_summary_section(summary) + "\n"
                grouped_sections += make_breakdown_section(summary.get("status_counts", {}), "Status Breakdown")
                grouped_sections += make_breakdown_section(summary.get("type_counts", {}), "Type Breakdown")
                grouped_sections += make_breakdown_section(summary.get("priority_counts", {}), "Priority Breakdown")
                grouped_sections += "\n### Worklog Details\n"
                grouped_sections += make_markdown_table([
                    "Key", "Summary", "Status", "Worklog Hours", "Resolved"
                ], [
                    [i.get('key', ''), safe_get(i, ['fields', 'summary'], ''), safe_get(i, ['fields', 'status', 'name'], ''), round(sum(wl.get('timeSpentSeconds', 0) for wl in safe_get(i, ['fields', 'worklog', 'worklogs'], [])) / 3600, 2), safe_get(i, ['fields', 'resolutiondate'], '')]
                    for i in issues
                ])
                grouped_sections += "\n---\n"
            # Compose final report using build_report_sections
            sections = {
                'header': f"# ⏳ Worklog Summary Report\n**Timeframe:** {start_date} to {end_date}\n",
                'summary': summary_section,
                'grouped_sections': grouped_sections,
            }
            content = build_report_sections(sections)
            write_report(filename, content, context, filetype='md', feature='time_tracking_worklogs', item_name='Worklog summary report')
            info(f"⏳ Worklog summary written to {filename}", extra=context, feature='time_tracking_worklogs')
            duration = int((time.time() - start_time) * 1000)
            contextual_log('info', f"⏳ [time_tracking_worklogs] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}). Duration: {duration}ms.", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='time_tracking_worklogs')
        except Exception as e:
            contextual_log('error', f"Failed to write worklog summary file: {e}", exc_info=True, operation="output_write", error_type=type(e).__name__, status="error", extra=context, feature='time_tracking_worklogs')
            error(f"Failed to write worklog summary file: {e}", extra=context, feature='time_tracking_worklogs')
            contextual_log('error', f"[time_tracking_worklogs] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", extra=context, feature='time_tracking_worklogs')
        # celebrate_success()
        # info_spared_no_expense()
        info(f"⏳ Worklog summary written to {filename}", extra=context, feature='time_tracking_worklogs')
    except KeyboardInterrupt:
        contextual_log('warning', "[time_tracking_worklogs] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context, feature='time_tracking_worklogs')
        info("Graceful exit from Time Tracking Worklogs feature.", extra={**context, "feature": "time_tracking_worklogs"})
    except Exception as e:
        contextual_log('error', f"[time_tracking_worklogs] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='time_tracking_worklogs')
        error(f"[time_tracking_worklogs] Exception: {e}", extra={**context, "feature": "time_tracking_worklogs"})
        raise

# Expose prompt_worklog_options as an attribute of the module for dynamic dispatch
prompt_worklog_options = prompt_worklog_options 