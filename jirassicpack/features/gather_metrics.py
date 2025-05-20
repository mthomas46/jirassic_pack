"""
gather_metrics.py

Gathers and reports metrics for Jira issues, including grouping by type and summary statistics. Provides interactive prompts for user/date selection and outputs professional Markdown reports. Used for analytics and reporting features in Jirassic Pack CLI.
"""
import os
from jirassicpack.utils.io import ensure_output_dir, spinner, error, info, get_option, validate_date, safe_get, require_param, make_output_filename, feature_error_handler
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.utils.jira import select_jira_user
import time
from marshmallow import Schema, fields, ValidationError
from jirassicpack.utils.rich_prompt import rich_error
from typing import Any
from jirassicpack.analytics.helpers import build_report_sections, group_issues_by_field, aggregate_issue_stats, make_summary_section, make_breakdown_section

def prompt_gather_metrics_options(options: dict, jira: Any = None) -> dict:
    """
    Prompt for metrics options, always requiring explicit user selection. Config/env value is only used if the user selects it.
    Args:
        options (dict): Options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.
    Returns:
        dict: Validated options for the feature.
    """
    info(f"[DEBUG] prompt_gather_metrics_options called. jira is {'present' if jira else 'None'}. options: {options}")
    config_user = options.get('user') or os.environ.get('JIRA_USER')
    user_obj = None
    username = None
    if jira:
        info("Please select a Jira user for metrics gathering.")
        label, user_obj = select_jira_user(jira, default_user=config_user)
        username = user_obj.get('accountId') if user_obj else None
        if not username:
            info("Aborted user selection for metrics gathering.")
            return None
    else:
        username = get_option(options, 'user', prompt="Jira Username for metrics:", default=config_user, required=True)
    # Start/end date: same pattern
    config_start = options.get('start_date') or os.environ.get('JIRA_START_DATE', '2024-01-01')
    config_end = options.get('end_date') or os.environ.get('JIRA_END_DATE', '2024-01-31')
    while True:
        start_date = get_option(options, 'start_date', prompt="Start date (YYYY-MM-DD):", default=config_start, required=True, validate=validate_date)
        end_date = get_option(options, 'end_date', prompt="End date (YYYY-MM-DD):", default=config_end, required=True, validate=validate_date)
        output_dir = get_option(options, 'output_dir', default=os.environ.get('JIRA_OUTPUT_DIR', 'output'))
        unique_suffix = options.get('unique_suffix', '')
        schema = Schema.from_dict({
            'user': fields.Str(required=True),
            'start_date': fields.Date(required=True),
            'end_date': fields.Date(required=True),
        })()
        try:
            validated = schema.load({
                'user': username,
                'start_date': start_date,
                'end_date': end_date,
            })
            break
        except ValidationError as err:
            rich_error(f"Input validation error: {err.messages}")
            continue
    # Use validated values
    user = validated['user']
    config_start = str(validated['start_date'])
    config_end = str(validated['end_date'])
    return {
        'user': user,
        'start_date': start_date,
        'end_date': end_date,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix
    }

@feature_error_handler('gather_metrics')
def gather_metrics(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Gather and report metrics for Jira issues based on the provided parameters.
    Outputs a Markdown report with summary and details.
    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the metrics (dates, filters, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
    Returns:
        None. Writes a Markdown report to disk.
    """
    context = build_context("gather_metrics", user_email, batch_index, unique_suffix)
    try:
        contextual_log('info', f"📈 [Gather Metrics] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='gather_metrics')
        if not require_param(params, 'user', context):
            return
        if not require_param(params, 'start_date', context):
            return
        if not require_param(params, 'end_date', context):
            return
        username = params.get('user')
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        ensure_output_dir(output_dir)
        # Try to get display name/accountId for header
        display_name = username
        account_id = username
        try:
            user_obj = jira.get_user(account_id=username)
            display_name = user_obj.get('displayName', username)
            account_id = user_obj.get('accountId', username)
        except Exception:
            pass
        jql = (
            f"assignee = '{username}' "
            f"AND statusCategory = Done "
            f"AND resolved >= '{start_date}' "
            f"AND resolved <= '{end_date}'"
        )
        fields = ["summary", "status", "issuetype", "resolutiondate", "key"]
        try:
            with spinner("📈 Gathering Metrics..."):
                issues = jira.search_issues(jql, fields=fields, max_results=100)
        except Exception as e:
            contextual_log('error', f"📈 [Gather Metrics] Failed to fetch issues: {e}", exc_info=True, operation="api_call", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='gather_metrics')
            error(f"Failed to fetch issues: {e}. Please check your Jira connection, credentials, and network.", extra=context)
            return
        total_issues = len(issues)
        # Group by issue type using helper
        grouped = group_issues_by_field(issues, ["fields", "issuetype", "name"], "Other")
        stats = aggregate_issue_stats(issues)
        # Header section
        header = f"# Metrics for {display_name}\nAccountId: {account_id}\nTimeframe: {start_date} to {end_date}\n**Total issues completed:** {total_issues}\n\n---\n"
        # Summary section
        summary = make_summary_section(stats)
        # Breakdown sections
        status_breakdown = make_breakdown_section(stats["status_counts"], "Status Breakdown")
        type_breakdown = make_breakdown_section(stats["type_counts"], "Type Breakdown")
        priority_breakdown = make_breakdown_section(stats["priority_counts"], "Priority Breakdown")
        breakdowns = f"{status_breakdown}\n{type_breakdown}\n{priority_breakdown}"
        # Grouped issue sections
        grouped_sections = ""
        for itype, group in grouped.items():
            grouped_sections += f"\n## {itype} Issues\n| Key | Summary | Status | Resolved |\n|-----|---------|--------|----------|\n"
            for issue in group:
                key = issue.get('key', 'N/A')
                summary_ = safe_get(issue, ['fields', 'summary'])
                status = safe_get(issue, ['fields', 'status', 'name'])
                resolved = safe_get(issue, ['fields', 'resolutiondate'])
                grouped_sections += f"| {key} | {summary_} | {status} | {resolved} |\n"
            grouped_sections += "\n"
        # Compose final report using build_report_sections
        sections = {
            'header': header,
            'summary': summary,
            'breakdowns': breakdowns,
            'grouped_sections': grouped_sections,
        }
        filename = make_output_filename("metrics", [("user", display_name), ("start", start_date), ("end", end_date)], output_dir)
        content = build_report_sections(sections)
        from jirassicpack.utils.io import write_report
        write_report(filename, content, context, filetype='md', feature='gather_metrics', item_name='Metrics report')
        info(f"🦖 Metrics report written to {filename}")
        duration = int((time.time() - context.get('start_time', 0)) * 1000) if context.get('start_time') else None
        contextual_log('info', f"📈 [Gather Metrics] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}).", operation="feature_end", status="success", params=redact_sensitive(params), extra=context, feature='gather_metrics')
    except KeyboardInterrupt:
        contextual_log('warning', "📈 [Gather Metrics] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context, feature='gather_metrics')
        info("Graceful exit from Gather Metrics feature.", extra=context)
    except Exception as e:
        contextual_log('error', f"📈 [Gather Metrics] Exception occurred: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='gather_metrics')
        error(f"📈 [Gather Metrics] Exception: {e}", extra=context)
        raise 