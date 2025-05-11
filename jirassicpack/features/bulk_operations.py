# bulk_operations.py
# This feature provides bulk operations for Jira issues, such as transitioning, commenting, or assigning multiple issues at once.
# It prompts the user for the desired action, the JQL to select issues, and the value for the action (if needed).
# Results are written to a Markdown report for traceability.

from jirassicpack.cli import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, print_batch_summary, logger, get_valid_transition, get_valid_user, get_option
from jirassicpack.utils import validate_required, error, info, spinner, progress_bar, BULK_ACTIONS, info_spared_no_expense, prompt_with_validation, build_context, render_markdown_report, contextual_log, redact_sensitive
from typing import Any, Dict, List, Tuple
import questionary
import json
import time

def prompt_bulk_options(opts: Dict[str, Any], jira=None) -> Dict[str, Any]:
    """
    Prompt for bulk operation options using Jira-aware helpers for value selection.
    """
    act = get_option(opts, 'action', prompt="🦴 Bulk action:", choices=BULK_ACTIONS)
    jql = get_option(opts, 'jql', prompt="🦴 JQL for selecting issues:")
    val = opts.get('value', '')
    if not val and jira and act == 'transition':
        key = opts.get('issue_key') or get_option(opts, 'issue_key', prompt="🦴 Issue Key for transition:")
        val = get_valid_transition(jira, key)
    elif not val and jira and act == 'assign':
        val = get_valid_user(jira)
    elif not val:
        val = get_option(opts, 'value', prompt="🦴 Value for action (if applicable):", default='')
    out_dir = get_option(opts, 'output_dir', default='output')
    suffix = opts.get('unique_suffix', '')
    return {
        'action': act,
        'jql': jql,
        'value': val,
        'output_dir': out_dir,
        'unique_suffix': suffix
    }

def write_bulk_report(filename: str, action: str, results: list, user_email=None, batch_index=None, unique_suffix=None, context=None, summary=None) -> None:
    try:
        summary_section = f"**Bulk Action:** {action}\n\n**Total Issues:** {len(results)}"
        details_section = "| Issue Key | Status | Error Message |\n|-----------|--------|--------------|\n"
        if summary:
            for key, status, err in summary:
                details_section += f"| {key} | {status} | {err} |\n"
        else:
            for r in results:
                details_section += f"| {r} |  |  |\n"
        content = render_markdown_report(
            feature="bulk_operations",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="Bulk Operations",
            summary_section=summary_section,
            main_content_section=details_section
        )
        with open(filename, 'w') as f:
            f.write(content)
        contextual_log('info', f"🦴 Bulk operation report written to {filename}", operation="output_write", output_file=filename, status="success", extra=context)
    except Exception as e:
        error(f"Failed to write bulk operation report: {e}", extra=context)

def write_bulk_report_json(filename: str, action: str, summary: list, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
    try:
        data = {
            "action": action,
            "results": [
                {"key": key, "status": status, "error": err} for key, status, err in summary
            ]
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        contextual_log('info', f"🦴 Bulk operation JSON report written to {filename}", operation="output_write", output_file=filename, status="success", extra=context)
    except Exception as e:
        error(f"Failed to write bulk operation JSON file: {e}", extra=context)

def bulk_operations(jira: Any, params: Dict[str, Any], user_email=None, batch_index=None, unique_suffix=None) -> None:
    correlation_id = params.get('correlation_id')
    context = build_context("bulk_operations", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    try:
        contextual_log('info', f"🦴 [bulk_operations] Feature entry | User: {user_email} | Params: {redact_sensitive(params)} | Suffix: {unique_suffix}", operation="feature_start", params=params, extra=context)
        # Patch JiraClient for logging
        orig_create_issue = getattr(jira, 'create_issue', None)
        orig_update_issue = getattr(jira, 'update_issue', None)
        if orig_create_issue:
            def log_create_issue(*args, **kwargs):
                contextual_log('debug', f"Jira create_issue: args={args}, kwargs={redact_sensitive(kwargs)}", extra=context)
                resp = orig_create_issue(*args, **kwargs)
                contextual_log('debug', f"Jira create_issue response: {resp}", extra=context)
                return resp
            jira.create_issue = log_create_issue
        if orig_update_issue:
            def log_update_issue(*args, **kwargs):
                contextual_log('debug', f"Jira update_issue: args={args}, kwargs={redact_sensitive(kwargs)}", extra=context)
                resp = orig_update_issue(*args, **kwargs)
                contextual_log('debug', f"Jira update_issue response: {resp}", extra=context)
                return resp
            jira.update_issue = log_update_issue
        action = params.get('action')
        if not action:
            error("action is required.", extra=context)
            contextual_log('error', "action is required.", operation="validation", status="error", extra=context)
            return
        jql = params.get('jql')
        if not jql:
            error("jql is required.", extra=context)
            contextual_log('error', "jql is required.", operation="validation", status="error", extra=context)
            return
        value = params.get('value', '')
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        ensure_output_dir(output_dir)
        # Confirmation prompt before proceeding
        confirm = questionary.confirm(
            "Are you sure you want to proceed? This could affect many issues.\n🦖 God help us, we're in the hands of devs."
        ).ask()
        if not confirm:
            info("🦖 Bulk operation cancelled by user.", extra=context)
            return
        def do_search():
            with spinner("🦴 Running Bulk Operations..."):
                return jira.search_issues(jql, fields=["key"], max_results=100)
        issues = retry_or_skip("Fetching issues for bulk operation", do_search)
        if not issues:
            info("🦖 See, Nobody Cares. No issues matched your criteria.", extra=context)
            return
        results = []
        summary = []
        for issue in progress_bar(issues, desc=f"🦴 Bulk: {action}"):
            key = issue.get('key', 'N/A')
            def do_action():
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
        filename = f"{output_dir}/bulk_operation_{action}{unique_suffix}.md"
        write_bulk_report(filename, action, results, user_email, batch_index, unique_suffix, context=context, summary=summary)
        json_filename = f"{output_dir}/bulk_operation_{action}{unique_suffix}.json"
        write_bulk_report_json(json_filename, action, summary, user_email, batch_index, unique_suffix, context=context)
        celebrate_success()
        info_spared_no_expense()
        info("\nBatch Summary:", extra=context)
        info("Feature         | Status   | Error Message", extra=context)
        info("----------------|----------|--------------", extra=context)
        for key, status, err in summary:
            info(f"{key:<15} | {status:<8} | {err}", extra=context)
        info(f"🦴 Bulk operation report written to {filename}", extra=context)
        duration = int((time.time() - start_time) * 1000)
        contextual_log('info', f"🦴 [bulk_operations] Bulk operation complete | Suffix: {unique_suffix}", operation="feature_end", status="success", duration_ms=duration, params=params, extra=context)
    except KeyboardInterrupt:
        contextual_log('warning', "[bulk_operations] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", extra=context)
        info("Graceful exit from Bulk Operations feature.", extra=context)
    except Exception as e:
        contextual_log('error', f"🦴 [bulk_operations] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", extra=context)
        error(f"🦴 [bulk_operations] Exception: {e}", extra=context)
        raise 