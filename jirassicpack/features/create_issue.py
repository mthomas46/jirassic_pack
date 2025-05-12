# create_issue.py
# This feature allows users to create a new Jira issue by prompting for project, summary, description, and issue type.
# It writes the created issue's key and summary to a Markdown file for record-keeping.

from jirassicpack.utils.io import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, spinner, info_spared_no_expense, prompt_with_validation, info, get_option
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.utils.jira import get_valid_project_key, get_valid_issue_type
from jirassicpack.utils.io import validate_required, error, render_markdown_report
from typing import Any, Dict
import logging
import json
import time

def prompt_create_issue_options(opts: Dict[str, Any], jira=None) -> Dict[str, Any]:
    """
    Prompt for create issue options using Jira-aware helpers for project and issue type.
    """
    proj = opts.get('project')
    if not proj and jira:
        proj = get_valid_project_key(jira)
    elif not proj:
        proj = get_option(opts, 'project', prompt="🦖 Jira Project Key:")
    summ = get_option(opts, 'summary', prompt="🦖 Issue Summary:")
    desc = get_option(opts, 'description', prompt="🦖 Issue Description:", default='')
    itype = opts.get('issue_type')
    if not itype and jira and proj:
        itype = get_valid_issue_type(jira, proj)
    elif not itype:
        itype = get_option(opts, 'issue_type', prompt="🦖 Issue Type:", default='Task')
    out_dir = get_option(opts, 'output_dir', default='output')
    suffix = opts.get('unique_suffix', '')
    return {
        'project': proj,
        'summary': summ,
        'description': desc,
        'issue_type': itype,
        'output_dir': out_dir,
        'unique_suffix': suffix
    }

def write_create_issue_file(filename: str, issue_key: str, summary: str, user_email=None, batch_index=None, unique_suffix=None, context=None, issue=None) -> None:
    try:
        summary_section = f"**Key:** {issue_key}\n\n**Summary:** {summary}"
        details_section = ""
        if issue:
            details_section = "| Field | Value |\n|-------|-------|\n"
            for k, v in issue.items():
                details_section += f"| {k} | {v} |\n"
        content = render_markdown_report(
            feature="create_issue",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="Create Issue",
            summary_section=summary_section,
            main_content_section=details_section
        )
        with open(filename, 'w') as f:
            f.write(content)
        info(f"🦖 Created issue details written to {filename}", extra=context)
    except Exception as e:
        error(f"Failed to write created issue file: {e}", extra=context)

def write_create_issue_json(filename: str, issue: dict, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
    try:
        with open(filename, 'w') as f:
            json.dump(issue, f, indent=2)
        info(f"🦖 Created issue details written to {filename}", extra=context)
    except Exception as e:
        error(f"Failed to write created issue JSON file: {e}", extra=context)

def create_issue(jira: Any, params: Dict[str, Any], user_email=None, batch_index=None, unique_suffix=None) -> None:
    correlation_id = params.get('correlation_id')
    context = build_context("create_issue", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    try:
        contextual_log('info', f"🦖 [Create Issue] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='create_issue')
        # Patch JiraClient for logging
        orig_create_issue = getattr(jira, 'create_issue', None)
        if orig_create_issue:
            def log_create_issue(*args, **kwargs):
                contextual_log('debug', f"🦖 [Create Issue] Jira create_issue called with args and redacted kwargs.", extra=context, feature='create_issue')
                resp = orig_create_issue(*args, **kwargs)
                contextual_log('debug', f"🦖 [Create Issue] Jira create_issue response: {redact_sensitive(resp)}", extra=context, feature='create_issue')
                return resp
            jira.create_issue = log_create_issue
        project = params.get('project')
        if not project:
            error("project is required.", extra=context, feature='create_issue')
            contextual_log('error', "🦖 [Create Issue] Project is required but missing.", operation="validation", status="error", extra=context, feature='create_issue')
            return
        summary = params.get('summary')
        if not summary:
            error("summary is required.", extra=context, feature='create_issue')
            contextual_log('error', "🦖 [Create Issue] Summary is required but missing.", operation="validation", status="error", extra=context, feature='create_issue')
            return
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        ensure_output_dir(output_dir)
        def do_create():
            with spinner("🦖 Running Create Issue..."):
                return jira.create_issue(
                    project=project,
                    summary=summary,
                    description=params['description'],
                    issuetype={'name': params['issue_type']}
                )
        issue = retry_or_skip("Creating Jira issue", do_create)
        if not issue:
            info("🦖 See, Nobody Cares. No issue was created.", extra=context, feature='create_issue')
            contextual_log('warning', "No issue was created.", operation="feature_end", status="skipped", extra=context, feature='create_issue')
            return
        filename = f"{output_dir}/{params['project']}_created_issue{unique_suffix}.md"
        write_create_issue_file(filename, issue.get('key', 'N/A'), params['summary'], user_email, batch_index, unique_suffix, context=context, issue=issue)
        contextual_log('info', f"Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=context, feature='create_issue')
        json_filename = f"{output_dir}/{params['project']}_created_issue{unique_suffix}.json"
        write_create_issue_json(json_filename, issue, user_email, batch_index, unique_suffix, context=context)
        contextual_log('info', f"JSON file written: {json_filename}", operation="output_write", output_file=json_filename, status="success", extra=context, feature='create_issue')
        celebrate_success()
        info_spared_no_expense()
        info(f"🦖 Created issue written to {filename}", extra=context, feature='create_issue')
        duration = int((time.time() - start_time) * 1000)
        contextual_log('info', f"🦖 [Create Issue] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}). Duration: {duration}ms.", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='create_issue')
    except KeyboardInterrupt:
        contextual_log('warning', "[create_issue] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", extra=context, feature='create_issue')
        info("Graceful exit from Create Issue feature.", extra=context, feature='create_issue')
    except Exception as e:
        contextual_log('error', f"🦖 [Create Issue] Exception occurred: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", extra=context, feature='create_issue')
        error(f"🦖 [Create Issue] Exception: {e}", extra=context, feature='create_issue')
        raise 