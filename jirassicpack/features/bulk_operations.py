"""
bulk_operations.py

Feature module for performing bulk operations on Jira issues via the CLI.
Supports bulk transitions, comments, and assignments on multiple issues selected by JQL.
Outputs a Markdown and JSON report with the results for traceability and audit.
"""

# bulk_operations.py
# This feature provides bulk operations for Jira issues, such as transitioning, commenting, or assigning multiple issues at once.
# It prompts the user for the desired action, the JQL to select issues, and the value for the action (if needed).
# Results are written to a Markdown report for traceability.

from jirassicpack.utils.io import ensure_output_dir, celebrate_success, retry_or_skip, spinner, progress_bar, info_spared_no_expense, info, error, prompt_select, feature_error_handler, make_output_filename, prompt_with_schema, write_report
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from typing import Any
import time
from marshmallow import fields, validate
from jirassicpack.utils.fields import BaseOptionsSchema, validate_nonempty
from jirassicpack.analytics.helpers import build_report_sections
from jirassicpack.constants import SEE_NOBODY_CARES, BULK_OPERATION_CANCELLED

def prompt_bulk_options(opts: dict, jira: Any = None) -> dict:
    """
    Prompt for bulk operation options using Marshmallow schema for validation and Jira-aware helpers.

    Args:
        opts (dict): Initial options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.

    Returns:
        dict: Validated options for the feature, or None if aborted.
    """
    schema = BulkOptionsSchema()
    result = prompt_with_schema(schema, dict(opts), jira=jira, abort_option=True)
    if result == "__ABORT__":
        info("❌ Aborted bulk operation prompt.")
        return None
    return result

@feature_error_handler('bulk_operations')
def bulk_operations(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Main feature entrypoint for bulk operations on Jira issues (transition, comment, assign).

    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the bulk operation.
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.

    Returns:
        None. Writes Markdown and JSON reports to disk.
    """
    correlation_id = params.get('correlation_id')
    context = build_context("bulk_operations", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    contextual_log('info', f"🦴 [Bulk Operations] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='bulk_operations')
    # Patch JiraClient for logging
    orig_create_issue = getattr(jira, 'create_issue', None)
    orig_update_issue = getattr(jira, 'update_issue', None)
    if orig_create_issue:
        def log_create_issue(*args, **kwargs):
            # Log the call and response for auditing
            contextual_log('debug', "🦴 [Bulk Operations] Jira create_issue called with args and redacted kwargs.", extra=context, feature='bulk_operations')
            resp = orig_create_issue(*args, **kwargs)
            contextual_log('debug', f"🦴 [Bulk Operations] Jira create_issue response: {redact_sensitive(resp)}", extra=context, feature='bulk_operations')
            return resp
        jira.create_issue = log_create_issue
    if orig_update_issue:
        def log_update_issue(*args, **kwargs):
            # Log the call and response for auditing
            contextual_log('debug', "🦴 [Bulk Operations] Jira update_issue called with args and redacted kwargs.", extra=context, feature='bulk_operations')
            resp = orig_update_issue(*args, **kwargs)
            contextual_log('debug', f"🦴 [Bulk Operations] Jira update_issue response: {redact_sensitive(resp)}", extra=context, feature='bulk_operations')
            return resp
        jira.update_issue = log_update_issue
    action = params.get('action')
    if not action:
        error("action is required.", extra=context, feature='bulk_operations')
        contextual_log('error', "🦴 [Bulk Operations] Action is required but missing.", operation="validation", status="error", extra=context, feature='bulk_operations')
        return
    jql = params.get('jql')
    if not jql:
        error("jql is required.", extra=context, feature='bulk_operations')
        contextual_log('error', "🦴 [Bulk Operations] JQL is required but missing.", operation="validation", status="error", extra=context, feature='bulk_operations')
        return
    value = params.get('value', '')
    output_dir = params.get('output_dir', 'output')
    unique_suffix = params.get('unique_suffix', '')
    ensure_output_dir(output_dir)
    confirm = prompt_select(
        "Are you sure you want to proceed? This could affect many issues.\n🦖 God help us, we're in the hands of devs.",
        choices=["Yes, proceed", "Cancel"]
    )
    if confirm != "Yes, proceed":
        info(BULK_OPERATION_CANCELLED, extra=context, feature='bulk_operations')
        return
    def do_search():
        # Spinner and retry logic for robust search
        with spinner("🦴 Running Bulk Operations..."):
            return jira.search_issues(jql, fields=["key"], max_results=100)
    issues = retry_or_skip("Fetching issues for bulk operation", do_search)
    if not issues:
        info(SEE_NOBODY_CARES, extra=context, feature='bulk_operations')
        return
    results = []
    summary = []
    for issue in progress_bar(issues, desc=f"🦴 Bulk: {action}"):
        key = issue.get('key', 'N/A')
        def do_action():
            # Spinner and retry logic for each bulk action
            with spinner(f"🦴 Running Bulk {action} for {key}..."):
                if action == 'transition':
                    jira.transition_issue(key, value)
                    return f"{key}: transitioned to {value}"
                elif action == 'comment':
                    jira.add_comment(key, value)
                    return f"{key}: commented '{value}'"
                elif action == 'assign':
                    jira.assign_issue(key, value)
                    return f"{key}: assigned to {value}"
                else:
                    return f"{key}: unknown action '{action}'"
        try:
            result = retry_or_skip(f"🦴 Bulk {action} for {key}", do_action)
            if result:
                results.append(result)
                summary.append((key, "Success", ""))
            else:
                results.append(f"{key}: skipped")
                summary.append((key, "Skipped", ""))
        except Exception as e:
            results.append(f"{key}: failed - {e}")
            summary.append((key, "Failed", str(e)))
    params_list = [("action", action), ("jql", jql)]
    filename = make_output_filename("bulk_operations", params_list, output_dir)
    # Compose Markdown report content
    summary_section = f"**Bulk Action:** {action}\n\n**Total Issues:** {len(results)}"
    details_section = "| Issue Key | Status | Error Message |\n|-----------|--------|--------------|\n"
    if summary:
        for key, status, err in summary:
            details_section += f"| {key} | {status} | {err} |\n"
    else:
        for result in results:
            details_section += f"| {result} |  |  |\n"
    header = f"# Bulk Operations Report\n\nAction: {action}\nJQL: {jql}"
    action_items = ""  # No specific action items for bulk ops
    report = build_report_sections({
        'header': header,
        'summary': summary_section,
        'action_items': action_items,
        'grouped_sections': details_section,
    })
    write_report(filename, report, context, filetype='md', feature='bulk_operations', item_name='Bulk operation report')
    contextual_log('info', f"Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=context, feature='bulk_operations')
    json_filename = make_output_filename("bulk_operations", params_list, output_dir, ext="json")
    json_data = {
        "action": action,
        "results": [
            {"key": key, "status": status, "error": err} for key, status, err in summary
        ] if summary else []
    }
    write_report(json_filename, json_data, context, filetype='json', feature='bulk_operations', item_name='Bulk operation JSON report')
    contextual_log('info', f"JSON file written: {json_filename}", operation="output_write", output_file=json_filename, status="success", extra=context, feature='bulk_operations')
    celebrate_success()
    info_spared_no_expense()
    info(f"🦴 Bulk operation report written to {filename}", extra=context, feature='bulk_operations')
    duration = int((time.time() - start_time) * 1000)
    contextual_log('info', f"🦴 [Bulk Operations] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}). Duration: {duration}ms.", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='bulk_operations')

class BulkOptionsSchema(BaseOptionsSchema):
    """
    Marshmallow schema for validating bulk operation options.
    Fields: action, jql, value.
    """
    action = fields.Str(required=True, validate=validate.OneOf(['transition', 'comment', 'assign']), error_messages={"required": "Action is required."})
    jql = fields.Str(required=True, validate=validate_nonempty, error_messages={"required": "JQL is required."})
    value = fields.Str(allow_none=True, validate=validate_nonempty)
    # output_dir and unique_suffix are inherited 