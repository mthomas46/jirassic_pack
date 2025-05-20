"""
advanced_metrics.py

Feature module for generating advanced metrics reports for Jira issues via the CLI.
Prompts for user and timeframe, fetches completed issues, and outputs a Markdown report with bottleneck analysis, breakdowns, and top-N analytics.
"""

# advanced_metrics.py
# This feature calculates advanced metrics for Jira issues, such as cycle time and lead time, for a given user and timeframe.
# It prompts for user, start/end dates, fetches completed issues, and outputs a Markdown report with a metrics table.

from jirassicpack.utils.io import ensure_output_dir, spinner, info, make_output_filename, feature_error_handler, safe_get, validate_date, error, require_param, prompt_with_schema, write_report
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from typing import Any
from collections import defaultdict
import logging
import time
from marshmallow import fields, pre_load
from jirassicpack.utils.fields import BaseOptionsSchema, validate_nonempty
from jirassicpack.analytics.helpers import aggregate_issue_stats, make_summary_section, make_breakdown_section, make_reporter_section, build_report_sections
from jirassicpack.constants import SEE_NOBODY_CARES, FAILED_TO

logger = logging.getLogger(__name__)

class AdvancedMetricsOptionsSchema(BaseOptionsSchema):
    """
    Marshmallow schema for validating advanced metrics options.
    Fields: user, start_date, end_date, output_dir, unique_suffix.
    """
    user = fields.Str(required=True, error_messages={"required": "Jira user is required."}, validate=validate_nonempty)
    start_date = fields.Str(required=True, error_messages={"required": "Start date is required."}, validate=validate_date)
    end_date = fields.Str(required=True, error_messages={"required": "End date is required."}, validate=validate_date)
    output_dir = fields.Str(load_default='output')
    unique_suffix = fields.Str(load_default='')

    @pre_load
    def normalize(self, data, **kwargs):
        for k, v in data.items():
            if isinstance(v, str):
                data[k] = v.strip()
        return data

def prompt_advanced_metrics_options(options: dict, jira: Any = None) -> dict:
    """
    Prompt for advanced metrics options using Marshmallow schema for validation and normalization.

    Args:
        options (dict): Initial options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.

    Returns:
        dict: Validated options for the feature.
    """
    schema = AdvancedMetricsOptionsSchema()
    return prompt_with_schema(schema, dict(options), jira=jira)

@feature_error_handler('advanced_metrics')
def advanced_metrics(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Generate an advanced metrics report for Jira issues, including bottleneck analysis, overdue issues, and top assignees.
    Outputs a Markdown report with detailed sections and visual enhancements.

    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the report (dates, filters, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.

    Returns:
        None. Writes a Markdown report to disk.
    """
    context = build_context("advanced_metrics", user_email, batch_index, unique_suffix)
    start_time = time.time()
    try:
        # Enhanced feature entry log
        contextual_log('info', f"📊 [Advanced Metrics] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='advanced_metrics')
        if not require_param(params, 'user', context):
            return
        if not require_param(params, 'start_date', context):
            return
        if not require_param(params, 'end_date', context):
            return
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        user = params['user']
        start_date = params['start_date']
        end_date = params['end_date']
        ensure_output_dir(output_dir)
        # Fetch more fields for richer analytics
        jql = (
            f"assignee = '{user}' "
            f"AND statusCategory = Done "
            f"AND resolved >= '{start_date}' "
            f"AND resolved <= '{end_date}'"
        )
        fields = ["summary", "created", "resolutiondate", "status", "key", "issuetype", "priority", "duedate", "assignee", "changelog"]
        try:
            with spinner("📊 Running Advanced Metrics..."):
                issues = jira.search_issues(jql, fields=fields, max_results=200, context=context)
        except Exception as e:
            contextual_log('error', f"📊 [Advanced Metrics] Failed to fetch issues: {e}", exc_info=True, operation="api_call", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='advanced_metrics')
            error(FAILED_TO.format(action='fetch issues', error=e), extra=context, feature='advanced_metrics')
            return
        if not issues:
            info(SEE_NOBODY_CARES, extra=context, feature='advanced_metrics')
            contextual_log('info', SEE_NOBODY_CARES, extra=context, feature='advanced_metrics')
            return
        # Try to get display name/accountId for header
        display_name = user
        try:
            user_obj = jira.get_user(account_id=user)
            display_name = user_obj.get('displayName', user)
        except Exception:
            pass
        # Aggregate stats
        stats = aggregate_issue_stats(issues)
        # Header
        header = f"# 📊 Advanced Metrics Report\n**User:** {display_name}  **Timeframe:** {start_date} to {end_date}  **Total issues:** {len(issues)}\n\n---\n"
        # Summary
        summary = make_summary_section(stats)
        # Breakdowns
        status_breakdown = make_breakdown_section(stats["status_counts"], "Status Breakdown")
        type_breakdown = make_breakdown_section(stats["type_counts"], "Type Breakdown")
        priority_breakdown = make_breakdown_section(stats["priority_counts"], "Priority Breakdown")
        breakdowns = f"{status_breakdown}\n{type_breakdown}\n{priority_breakdown}"
        # Top N reporters
        top_reporters = make_reporter_section(stats["reporters"], "Top Reporters")
        # Grouped issue sections
        grouped = defaultdict(list)
        for issue in issues:
            group_label = safe_get(issue, ['fields', 'issuetype', 'name'], 'Other')
            grouped[group_label].append(issue)
        grouped_sections = ""
        for group_label, issues_in_group in grouped.items():
            grouped_sections += f"\n## {group_label} Issues\n| Key | Summary | Status | Resolved |\n|---|---|---|---|\n"
            for issue in issues_in_group:
                key = issue.get('key', 'N/A')
                summary_ = safe_get(issue, ['fields', 'summary'], '')
                status = safe_get(issue, ['fields', 'status', 'name'], '')
                resolved = safe_get(issue, ['fields', 'resolutiondate'], '')
                grouped_sections += f"| {key} | {summary_} | {status} | {resolved} |\n"
            grouped_sections += "\n"
        # Compose final report using build_report_sections
        sections = {
            'header': header,
            'summary': summary,
            'breakdowns': breakdowns,
            'top_n': top_reporters,
            'grouped_sections': grouped_sections,
        }
        filename = make_output_filename(output_dir, f"advanced_metrics_{user_email}_{start_date}_{end_date}_{unique_suffix}")
        content = build_report_sections(sections)
        write_report(filename, content)
        info(f"🦖 Advanced metrics report written to {filename}")
        # Enhanced feature end log
        duration = int((time.time() - start_time) * 1000)
        contextual_log('info', f"📊 [advanced_metrics] Feature complete | Suffix: {unique_suffix}", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='advanced_metrics')
    except KeyboardInterrupt:
        contextual_log('warning', "[advanced_metrics] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context, feature='advanced_metrics')
        info("Graceful exit from Advanced Metrics feature.", extra=context, feature='advanced_metrics')
    except Exception as e:
        if 'list index out of range' in str(e):
            info(SEE_NOBODY_CARES, extra=context, feature='advanced_metrics')
            contextual_log('info', SEE_NOBODY_CARES, extra=context, feature='advanced_metrics')
            return
        contextual_log('error', f"[advanced_metrics] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='advanced_metrics')
        error(f"[advanced_metrics] Exception: {e}", extra=context, feature='advanced_metrics')
        raise 