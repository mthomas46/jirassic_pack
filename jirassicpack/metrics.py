"""
metrics.py

Gathers and reports metrics for Jira issues, including grouping by type and summary statistics. Provides interactive prompts for user/date selection and outputs professional Markdown reports. Used for analytics and reporting features in Jirassic Pack CLI.
"""
from datetime import datetime
import os
import questionary
from jirassicpack.utils.io import ensure_output_dir, spinner, error, info, get_option, validate_required, validate_date, safe_get, write_markdown_file, require_param, render_markdown_report, make_output_filename, status_emoji
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.features.time_tracking_worklogs import select_jira_user
import time
from marshmallow import Schema, fields, ValidationError
from jirassicpack.utils.rich_prompt import rich_error
from mdutils.mdutils import MdUtils
from typing import Any

class GatherMetricsOptionsSchema(Schema):
    user = fields.Str(required=True)
    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)

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
        menu_choices = [
            "Search for a user",
            "Pick from list",
            "Use current user",
        ]
        if config_user:
            menu_choices.append(f"Use value from config/env: {config_user}")
        menu_choices += ["Enter manually", "Abort"]
        while True:
            method = questionary.select("How would you like to select the user?", choices=menu_choices).ask()
            if method == "Search for a user":
                label, user_obj = select_jira_user(jira)
                username = user_obj.get('accountId') if user_obj else None
            elif method == "Pick from list":
                label, user_obj = select_jira_user(jira)
                username = user_obj.get('accountId') if user_obj else None
            elif method == "Use current user":
                try:
                    me = jira.get_current_user()
                    username = me.get('accountId')
                except Exception:
                    info("Could not retrieve current user from Jira.")
                    continue
            elif method.startswith("Use value from config/env"):
                username = config_user
            elif method == "Enter manually":
                username = questionary.text("Enter Jira accountId or username:").ask()
            elif method == "Abort":
                info("Aborted user selection for metrics gathering.")
                return None
            if username:
                break
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
        schema = GatherMetricsOptionsSchema()
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
        # Order by issue key
        issues = sorted(issues, key=lambda i: i.get('key', ''))
        # Group by issue type
        from collections import defaultdict
        grouped = defaultdict(list)
        for issue in issues:
            itype = safe_get(issue, ['fields', 'issuetype', 'name'], 'Other')
            grouped[itype].append(issue)
        # Header section
        lines = [
            f"# Metrics for {display_name}",
            f"AccountId: {account_id}",
            f"Timeframe: {start_date} to {end_date}",
            f"**Total issues completed:** {total_issues}",
            "\n---\n"
        ]
        # Summary by type
        lines.append("## Issue Type Breakdown\n")
        for itype, group in grouped.items():
            lines.append(f"- {itype}: {len(group)}")
        lines.append("\n---\n")
        # Detailed sections by type
        for itype, group in grouped.items():
            lines.append(f"## {itype} Issues\n")
            lines.append("| Key | Summary | Status | Resolved |\n|-----|---------|--------|----------|\n")
            for issue in group:
                key = issue.get('key', 'N/A')
                summary = safe_get(issue, ['fields', 'summary'])
                status = safe_get(issue, ['fields', 'status', 'name'])
                resolved = safe_get(issue, ['fields', 'resolutiondate'])
                lines.append(f"| {key} | {summary} | {status} | {resolved} |\n")
            lines.append("\n")
        params_list = [("user", display_name), ("start", start_date), ("end", end_date)]
        filename = make_output_filename("metrics", params_list, output_dir)
        summary_section = f"**Total metrics gathered:** {total_issues}\n\n**Highlights:** ..."
        details_section = "\n".join(lines)
        content = render_markdown_report(
            feature="gather_metrics",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="Metrics Gathering",
            summary_section=summary_section,
            main_content_section=details_section
        )
        md_file = MdUtils(file_name=filename, title="Metrics Report")
        md_file.new_line(f"_Generated: {datetime.now()}_")
        md_file.new_header(level=2, title="Summary")
        md_file.new_line(summary_section)
        md_file.new_header(level=2, title="Issue Type Breakdown")
        for itype, group in grouped.items():
            md_file.new_line(f"- {itype}: {len(group)}")
        md_file.new_header(level=2, title="Detailed Sections by Type")
        for itype, group in grouped.items():
            md_file.new_header(level=3, title=itype)
            md_file.new_line("| Key | Summary | Status | Resolved |")
            md_file.new_line("|-----|---------|--------|----------|")
            for issue in group:
                key = issue.get('key', 'N/A')
                summary = safe_get(issue, ['fields', 'summary'])
                status = safe_get(issue, ['fields', 'status', 'name'])
                resolved = safe_get(issue, ['fields', 'resolutiondate'])
                md_file.new_line(f"| {key} | {summary} | {status} | {resolved} |")
            md_file.new_line("")
        md_file.create_md_file()
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