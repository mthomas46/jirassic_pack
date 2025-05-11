# update_issue.py
# This feature allows users to update a field on an existing Jira issue by prompting for the issue key, field, and new value.
# It writes the updated field and value to a Markdown file for record-keeping.

from jirassicpack.cli import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, logger, get_valid_field, get_option
from jirassicpack.utils import validate_required, error, info, spinner, info_spared_no_expense, prompt_with_validation, build_context, render_markdown_report, contextual_log, redact_sensitive
from typing import Any, Dict
import json
import time

def prompt_update_issue_options(opts: Dict[str, Any], jira=None) -> Dict[str, Any]:
    """
    Prompt for update issue options using Jira-aware helpers for field selection.
    """
    key = get_option(opts, 'issue_key', prompt="🦕 Jira Issue Key:")
    fld = opts.get('field')
    proj = opts.get('project')
    itype = opts.get('issue_type')
    if not fld and jira and proj and itype:
        fld = get_valid_field(jira, proj, itype)
    elif not fld:
        fld = get_option(opts, 'field', prompt="🦕 Field to update (e.g., summary, description, status):")
    val = get_option(opts, 'value', prompt="🦕 New value:")
    out_dir = get_option(opts, 'output_dir', default='output')
    suffix = opts.get('unique_suffix', '')
    return {
        'issue_key': key,
        'field': fld,
        'value': val,
        'output_dir': out_dir,
        'unique_suffix': suffix
    }

def write_update_issue_file(filename: str, issue_key: str, field: str, value: str, user_email=None, batch_index=None, unique_suffix=None, context=None, result=None) -> None:
    try:
        summary_section = f"**Key:** {issue_key}\n\n**Field Updated:** {field}\n\n**New Value:** {value}"
        details_section = ""
        if result:
            details_section = "| Field | Value |\n|-------|-------|\n"
            for k, v in (result.items() if isinstance(result, dict) else []):
                details_section += f"| {k} | {v} |\n"
        content = render_markdown_report(
            feature="update_issue",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="Update Issue",
            summary_section=summary_section,
            main_content_section=details_section
        )
        with open(filename, 'w') as f:
            f.write(content)
        info(f"🦕 Updated issue details written to {filename}", extra=context)
    except Exception as e:
        error(f"Failed to write updated issue file: {e}", extra=context)

def write_update_issue_json(filename: str, issue_key: str, field: str, value: str, result: dict = None, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
    try:
        data = {
            "issue_key": issue_key,
            "field": field,
            "value": value,
            "result": result or {}
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        info(f"🦕 Updated issue details written to {filename}", extra=context)
    except Exception as e:
        error(f"Failed to write updated issue JSON file: {e}", extra=context)

def update_issue(jira: Any, params: Dict[str, Any], user_email=None, batch_index=None, unique_suffix=None) -> None:
    correlation_id = params.get('correlation_id')
    context = build_context("update_issue", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    try:
        contextual_log('info', f"🦕 [update_issue] Feature entry | User: {user_email} | Params: {redact_sensitive(params)} | Suffix: {unique_suffix}", operation="feature_start", params=params, extra=context)
        issue_key = params.get('issue_key')
        if not issue_key:
            error("issue_key is required.", extra=context)
            contextual_log('error', "issue_key is required.", operation="validation", status="error", extra=context)
            return
        field = params.get('field')
        if not field:
            error("field is required.", extra=context)
            contextual_log('error', "field is required.", operation="validation", status="error", extra=context)
            return
        value = params.get('value')
        if not value:
            error("value is required.", extra=context)
            contextual_log('error', "value is required.", operation="validation", status="error", extra=context)
            return
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        ensure_output_dir(output_dir)
        # Patch JiraClient for logging
        orig_update_issue = getattr(jira, 'update_issue', None)
        if orig_update_issue:
            def log_update_issue(*args, **kwargs):
                contextual_log('debug', f"Jira update_issue: args={args}, kwargs={redact_sensitive(kwargs)}", extra=context)
                resp = orig_update_issue(*args, **kwargs)
                contextual_log('debug', f"Jira update_issue response: {resp}", extra=context)
                return resp
            jira.update_issue = log_update_issue
        def do_update():
            with spinner("🦕 Running Update Issue..."):
                return jira.update_issue(
                    issue_key=issue_key,
                    fields={field: value}
                )
        result = retry_or_skip("Updating Jira issue", do_update)
        if result is None:
            info("🦖 See, Nobody Cares. No update was made.", extra=context)
            contextual_log('warning', "No update was made.", operation="feature_end", status="skipped", extra=context)
            return
        filename = f"{output_dir}/{issue_key}_updated_issue{unique_suffix}.md"
        write_update_issue_file(filename, issue_key, field, value, user_email, batch_index, unique_suffix, context=context, result=result)
        contextual_log('info', f"Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=context)
        json_filename = f"{output_dir}/{issue_key}_updated_issue{unique_suffix}.json"
        write_update_issue_json(json_filename, issue_key, field, value, result, user_email, batch_index, unique_suffix, context=context)
        contextual_log('info', f"JSON file written: {json_filename}", operation="output_write", output_file=json_filename, status="success", extra=context)
        celebrate_success()
        info_spared_no_expense()
        info(f"🦕 Updated issue written to {filename}", extra=context)
        duration = int((time.time() - start_time) * 1000)
        contextual_log('info', f"🦕 [update_issue] Issue update complete | Suffix: {unique_suffix}", operation="feature_end", status="success", duration_ms=duration, params=params, extra=context)
    except KeyboardInterrupt:
        contextual_log('warning', "[update_issue] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", extra=context)
        info("Graceful exit from Update Issue feature.", extra=context)
    except Exception as e:
        contextual_log('error', f"🦕 [update_issue] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", extra=context)
        error(f"🦕 [update_issue] Exception: {e}", extra=context)
        raise
    return 