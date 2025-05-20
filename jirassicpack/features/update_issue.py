"""
update_issue.py

Feature module for updating a field on an existing Jira issue via the CLI.
Prompts the user for issue key, field, and new value, then updates the issue in Jira.
Outputs a Markdown and JSON report with the updated field and value for record-keeping and audit.
"""

# update_issue.py
# This feature allows users to update a field on an existing Jira issue by prompting for the issue key, field, and new value.
# It writes the updated field and value to a Markdown file for record-keeping.

from jirassicpack.utils.output_utils import ensure_output_dir, celebrate_success, write_report
from jirassicpack.utils.message_utils import retry_or_skip, info, error
from jirassicpack.utils.validation_utils import prompt_with_schema
from jirassicpack.utils.decorators import feature_error_handler
from jirassicpack.utils.progress_utils import spinner
from jirassicpack.utils.logging import contextual_log, redact_sensitive
from jirassicpack.utils.logging import build_context
from typing import Any
import time
from marshmallow import fields
from jirassicpack.utils.fields import IssueKeyField, BaseOptionsSchema, validate_nonempty
from jirassicpack.analytics.helpers import build_report_sections
from jirassicpack.constants import FAILED_TO

class UpdateIssueOptionsSchema(BaseOptionsSchema):
    """
    Marshmallow schema for validating update issue options.
    Fields: issue_key, field, value.
    """
    issue_key = IssueKeyField(required=True, error_messages={"required": "Issue key is required."})
    field = fields.Str(required=True, error_messages={"required": "Field is required."}, validate=validate_nonempty)
    value = fields.Str(required=True, error_messages={"required": "Value is required."}, validate=validate_nonempty)
    # output_dir and unique_suffix are inherited

def prompt_update_issue_options(opts: dict, jira: Any = None) -> dict:
    """
    Prompt for update issue options using Marshmallow schema for validation and Jira-aware helpers.

    Args:
        opts (dict): Initial options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.

    Returns:
        dict: Validated options for the feature, or None if aborted.
    """
    schema = UpdateIssueOptionsSchema()
    result = prompt_with_schema(schema, dict(opts), jira=jira, abort_option=True)
    if result == "__ABORT__":
        info("❌ Aborted update issue prompt.")
        return None
    return result

@feature_error_handler('update_issue')
def update_issue(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Main feature entrypoint for updating a field on an existing Jira issue.

    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the update (issue_key, field, value, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.

    Returns:
        None. Writes Markdown and JSON reports to disk.
    """
    correlation_id = params.get('correlation_id')
    context = build_context("update_issue", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    contextual_log('info', f"🦕 [Update Issue] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='update_issue')
    issue_key = params.get('issue_key')
    if not issue_key:
        error(FAILED_TO.format(field='issue_key'), extra=context)
        contextual_log('error', "🦕 [Update Issue] Issue key is required but missing.", operation="validation", status="error", extra=context, feature='update_issue')
        return
    field = params.get('field')
    if not field:
        error(FAILED_TO.format(field='field'), extra=context)
        contextual_log('error', "🦕 [Update Issue] Field is required but missing.", operation="validation", status="error", extra=context, feature='update_issue')
        return
    value = params.get('value')
    if not value:
        error(FAILED_TO.format(field='value'), extra=context)
        contextual_log('error', "🦕 [Update Issue] Value is required but missing.", operation="validation", status="error", extra=context, feature='update_issue')
        return
    output_dir = params.get('output_dir', 'output')
    unique_suffix = params.get('unique_suffix', '')
    ensure_output_dir(output_dir)
    # Patch JiraClient for logging
    orig_update_issue = getattr(jira, 'update_issue', None)
    if orig_update_issue:
        def log_update_issue(*args, **kwargs):
            # Log the call and response for auditing
            contextual_log('debug', "🦕 [Update Issue] Jira update_issue called with args and redacted kwargs.", extra=context, feature='update_issue')
            resp = orig_update_issue(*args, **kwargs)
            contextual_log('debug', f"🦕 [Update Issue] Jira update_issue response: {redact_sensitive(resp)}", extra=context, feature='update_issue')
            return resp
        jira.update_issue = log_update_issue
    def do_update():
        # Spinner and retry logic for robust update
        with spinner("🦕 Running Update Issue..."):
            return jira.update_issue(
                issue_key=issue_key,
                fields={field: value}
            )
    result = retry_or_skip("Updating Jira issue", do_update)
    if result is None:
        # If update failed or was skipped, log and exit
        from jirassicpack.constants import SEE_NOBODY_CARES
        info(SEE_NOBODY_CARES, extra=context)
        contextual_log('warning', "No update was made.", operation="feature_end", status="skipped", extra=context, feature='update_issue')
        return
    filename = f"{output_dir}/{issue_key}_updated_issue{unique_suffix}.md"
    summary_section = f"**Key:** {issue_key}\n\n**Field Updated:** {field}\n\n**New Value:** {value}"
    details_section = ""
    if result:
        details_section = "| Field | Value |\n|-------|-------|\n"
        for field_name, field_value in (result.items() if isinstance(result, dict) else []):
            details_section += f"| {field_name} | {field_value} |\n"
    header = f"# Update Issue Report\n\nIssue Key: {issue_key}\nField: {field}"
    action_items = ""  # No specific action items for update issue
    report = build_report_sections({
        'header': header,
        'summary': summary_section,
        'action_items': action_items,
        'grouped_sections': details_section,
    })
    write_report(filename, report, context, filetype='md', feature='update_issue', item_name='Update issue report')
    contextual_log('info', f"Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=context, feature='update_issue')
    json_filename = f"{output_dir}/{issue_key}_updated_issue{unique_suffix}.json"
    json_data = {
        "issue_key": issue_key,
        "field": field,
        "value": value,
        "result": result or {}
    }
    write_report(json_filename, json_data, context, filetype='json', feature='update_issue', item_name='Update issue JSON report')
    contextual_log('info', f"JSON file written: {json_filename}", operation="output_write", output_file=json_filename, status="success", extra=context, feature='update_issue')
    celebrate_success()
    info_spared_no_expense()
    info(f"🦕 Updated issue written to {filename}", extra=context, feature='update_issue')
    duration = int((time.time() - start_time) * 1000)
    contextual_log('info', f"🦕 [Update Issue] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}). Duration: {duration}ms.", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='update_issue') 