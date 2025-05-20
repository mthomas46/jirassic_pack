"""
user_team_analytics.py

Feature module for analyzing team workload and user activity in Jira via the CLI.
Prompts for team members and timeframe, then aggregates and reports on issues assigned to each member.
Outputs a Markdown report with workload, bottleneck, and breakdown analysis for audit and improvement.
"""

# user_team_analytics.py
# This feature analyzes team workload in Jira by counting issues assigned to each team member in a given timeframe.
# It prompts for team members, start/end dates, and outputs a Markdown report with workload and bottleneck analysis.

from jirassicpack.utils.output_utils import ensure_output_dir, celebrate_success, write_report
from jirassicpack.utils.message_utils import retry_or_skip, info, error
from jirassicpack.utils.validation_utils import get_option, safe_get, require_param
from jirassicpack.utils.decorators import feature_error_handler
from jirassicpack.utils.progress_utils import spinner
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.utils.jira import select_jira_user
from jirassicpack.utils.fields import validate_date
from typing import Any, Dict
import logging
import time
from jirassicpack.analytics.helpers import aggregate_issue_stats, make_markdown_table, make_summary_section, make_breakdown_section, make_reporter_section, build_report_sections

logger = logging.getLogger(__name__)

# Module-level cache for Jira users
_CACHED_JIRA_USERS = None

def prompt_user_team_analytics_options(opts: Dict[str, Any], jira: Any = None) -> Dict[str, Any]:
    """
    Prompt for user/team analytics options, always requiring explicit team member selection. Config/env value is only used if the user selects it.
    Args:
        opts (Dict[str, Any]): Options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.
    Returns:
        Dict[str, Any]: Validated options for the feature.
    """
    info(f"[DEBUG] prompt_user_team_analytics_options called. jira is {'present' if jira else 'None'}. opts: {opts}")
    team = None
    users = []
    if not team and jira:
        info("Please select Jira team members for analytics.")
        label_user_tuples = select_jira_user(jira, allow_multiple=True)
        if not label_user_tuples:
            info("Aborted team member selection.")
            return None
        # Use accountId for each user
        users = [user_obj.get('accountId') for label, user_obj in label_user_tuples if user_obj and user_obj.get('accountId')]
        if not users:
            info("No valid users selected for team analytics.")
            return None
        team = ','.join(users)
    elif not team:
        team = get_option(opts, 'team', prompt="Team members (comma-separated usernames):", required=True)
    start = get_option(opts, 'start_date', prompt="Start date (YYYY-MM-DD):", default='2024-01-01', required=True, validate=validate_date)
    end = get_option(opts, 'end_date', prompt="End date (YYYY-MM-DD):", default='2024-01-31', required=True, validate=validate_date)
    out_dir = get_option(opts, 'output_dir', default='output')
    suffix = opts.get('unique_suffix', '')
    return {
        'team': team,
        'start_date': start,
        'end_date': end,
        'output_dir': out_dir,
        'unique_suffix': suffix
    }

@feature_error_handler('user_team_analytics')
def user_team_analytics(
    jira: Any,
    params: Dict[str, Any],
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Main feature entrypoint for user/team analytics in Jira.
    Aggregates issue stats for each selected user and generates a detailed Markdown report.
    Args:
        jira (Any): Authenticated Jira client instance.
        params (Dict[str, Any]): Parameters for the analytics (team, start_date, end_date, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
    Returns:
        None. Writes Markdown report to disk.
    """
    correlation_id = params.get('correlation_id')
    context = build_context("user_team_analytics", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    contextual_log('info', f"🧬 [User/Team Analytics] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='user_team_analytics')
    orig_search_issues = getattr(jira, 'search_issues', None)
    if orig_search_issues:
        def log_search_issues(*args, **kwargs):
            contextual_log('debug', f"Jira search_issues: args={args}, kwargs={redact_sensitive(kwargs)}", extra=context, feature='user_team_analytics')
            resp = orig_search_issues(*args, **kwargs)
            contextual_log('debug', f"Jira search_issues response: {resp}", extra=context, feature='user_team_analytics')
            return resp
        jira.search_issues = log_search_issues
    team = params.get('team')
    if not team:
        error("team is required.", extra=context, feature='user_team_analytics')
        return
    start_date = params.get('start_date')
    if not start_date:
        error("start_date is required.", extra=context, feature='user_team_analytics')
        return
    end_date = params.get('end_date')
    if not end_date:
        error("end_date is required.", extra=context, feature='user_team_analytics')
        return
    output_dir = params.get('output_dir', 'output')
    unique_suffix = params.get('unique_suffix', '')
    ensure_output_dir(output_dir)
    users = [u.strip() for u in team.split(",") if u.strip()]
    all_user_data = {}
    team_stats = {
        "total_issues": 0,
        "created": 0,
        "resolved": 0,
        "blockers": [],
        "critical": [],
        "blocked": [],
        "oldest_unresolved": None,
        "age_buckets": {"30d": 0, "60d": 0, "90d": 0},
        "unresolved_ages": [],
        "self_assigned": 0,
        "assigned_by_others": 0,
        "linked": 0,
        "blocking": [],
        "blocked_by": [],
        "reporters": {},
    }
    for user in users:
        user_jql = (
            f"assignee = '{user}' "
            f"AND updated >= '{start_date}' "
            f"AND updated <= '{end_date}'"
        )
        def do_user_analytics():
            # Spinner and retry logic for robust user analytics
            with spinner(f"🧬 Fetching issues for {user}..."):
                return jira.search_issues(
                    user_jql,
                    fields=[
                        "key", "summary", "status", "issuetype", "priority", "created", "updated", "resolutiondate",
                        "reporter", "labels", "issuelinks"
                    ],
                    max_results=100
                )
        issues = retry_or_skip(f"Fetching issues for {user}", do_user_analytics)
        if not issues:
            all_user_data[user] = {"issues": [], "summary": {}}
            continue
        # Aggregate analytics
        summary = aggregate_issue_stats(issues)
        all_user_data[user] = {
            "issues": issues,
            "summary": summary
        }
        # Team summary aggregation
        team_stats["total_issues"] += len(issues)
        team_stats["created"] += summary['created']
        team_stats["resolved"] += summary['resolved']
        team_stats["age_buckets"]["30d"] += summary['age_buckets']['30d']
        team_stats["age_buckets"]["60d"] += summary['age_buckets']['60d']
        team_stats["age_buckets"]["90d"] += summary['age_buckets']['90d']
        team_stats["unresolved_ages"].extend(summary['unresolved_ages'])
        team_stats["self_assigned"] += summary['self_assigned']
        team_stats["assigned_by_others"] += summary['assigned_by_others']
        for reporter, count in summary['reporters'].items():
            team_stats["reporters"][reporter] = team_stats["reporters"].get(reporter, 0) + count
    if not any(len(data["issues"]) for data in all_user_data.values()):
        info("🦖 See, Nobody Cares. No analytics data found.", extra=context, feature='user_team_analytics')
        contextual_log('info', "🦖 See, Nobody Cares. No analytics data found.", extra=context, feature='user_team_analytics')
        return
    # Write expanded analytics to Markdown
    filename = f"{output_dir}/user_team_analytics{unique_suffix}.md"
    try:
        summary_section = make_summary_section(team_stats)
        # Team breakdowns
        status_breakdown = make_breakdown_section(team_stats["status_counts"], "Status Breakdown") if "status_counts" in team_stats else ""
        type_breakdown = make_breakdown_section(team_stats["type_counts"], "Type Breakdown") if "type_counts" in team_stats else ""
        priority_breakdown = make_breakdown_section(team_stats["priority_counts"], "Priority Breakdown") if "priority_counts" in team_stats else ""
        breakdowns = f"{status_breakdown}\n{type_breakdown}\n{priority_breakdown}"
        # Top N reporters
        top_reporters = make_reporter_section(team_stats["reporters"], "Top Reporters") if "reporters" in team_stats else ""
        # Per-user sections
        grouped_sections = ""
        for user, data in all_user_data.items():
            summary = data["summary"]
            issues = data["issues"]
            grouped_sections += f"\n## {user}\n"
            grouped_sections += make_summary_section(summary) + "\n"
            grouped_sections += make_breakdown_section(summary["status_counts"], "Status Breakdown")
            grouped_sections += make_breakdown_section(summary["type_counts"], "Type Breakdown")
            grouped_sections += make_breakdown_section(summary["priority_counts"], "Priority Breakdown")
            grouped_sections += make_reporter_section(summary["reporters"], "Reporters")
            grouped_sections += "\n### Issue List\n"
            grouped_sections += make_markdown_table(["Key", "Summary", "Status", "Resolved"], [[i.get('key', ''), safe_get(i, ['fields', 'summary'], ''), safe_get(i, ['fields', 'status', 'name'], ''), safe_get(i, ['fields', 'resolutiondate'], '')] for i in issues])
            grouped_sections += "\n---\n"
        # Compose final report using build_report_sections
        sections = {
            'header': f"# 🧬 User/Team Analytics Report\n**Timeframe:** {start_date} to {end_date}\n",
            'summary': summary_section,
            'breakdowns': breakdowns,
            'top_n': top_reporters,
            'grouped_sections': grouped_sections,
        }
        content = build_report_sections(sections)
        write_report(filename, content, context, filetype='md', feature='user_team_analytics', item_name='User/team analytics report')
        info(f"🧬 User/team analytics written to {filename}", extra=context, feature='user_team_analytics')
        duration = int((time.time() - start_time) * 1000)
        contextual_log('info', f"🧬 [User/Team Analytics] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}). Duration: {duration}ms.", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='user_team_analytics')
    except Exception as e:
        contextual_log('error', f"Failed to write analytics file: {e}", exc_info=True, operation="output_write", error_type=type(e).__name__, status="error", extra=context, feature='user_team_analytics')
        error(f"Failed to write analytics file: {e}", extra=context, feature='user_team_analytics')
        contextual_log('error', f"[User/Team Analytics] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", extra=context, feature='user_team_analytics')
    celebrate_success()
    info_spared_no_expense()
    info(f"🧬 User/team analytics written to {filename}", extra=context, feature='user_team_analytics') 