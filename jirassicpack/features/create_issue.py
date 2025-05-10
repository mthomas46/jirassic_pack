# create_issue.py
# This feature allows users to create a new Jira issue by prompting for project, summary, description, and issue type.
# It writes the created issue's key and summary to a Markdown file for record-keeping.

from jirassicpack.cli import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, logger, redact_sensitive
from jirassicpack.utils import get_option, validate_required, error, info, spinner, info_spared_no_expense, prompt_with_validation, build_context, render_markdown_report
from typing import Any, Dict
import logging
import json

def prompt_create_issue_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prompt for create issue options using get_option utility.
    Prompts for project key, summary, description, and issue type.
    Returns a dictionary of all options needed to create the issue.
    """
    project = get_option(options, 'project', prompt="🦖 Jira Project Key:")
    summary = get_option(options, 'summary', prompt="🦖 Issue Summary:")
    description = get_option(options, 'description', prompt="🦖 Issue Description:", default='')
    issue_type = get_option(options, 'issue_type', prompt="🦖 Issue Type:", default='Task')
    output_dir = get_option(options, 'output_dir', default='output')
    unique_suffix = options.get('unique_suffix', '')
    return {
        'project': project,
        'summary': summary,
        'description': description,
        'issue_type': issue_type,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix
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
    context = build_context("create_issue", user_email, batch_index, unique_suffix)
    try:
        logger.info(f"🦖 [create_issue] Feature entry | User: {user_email} | Params: {redact_sensitive(params)} | Suffix: {unique_suffix}")
        # Patch JiraClient for logging
        orig_create_issue = getattr(jira, 'create_issue', None)
        if orig_create_issue:
            def log_create_issue(*args, **kwargs):
                logger.debug(f"Jira create_issue: args={args}, kwargs={redact_sensitive(kwargs)}")
                resp = orig_create_issue(*args, **kwargs)
                logger.debug(f"Jira create_issue response: {resp}")
                return resp
            jira.create_issue = log_create_issue
        project = params.get('project')
        if not project:
            error("project is required.", extra={"feature": "create_issue", "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            return
        summary = params.get('summary')
        if not summary:
            error("summary is required.", extra={"feature": "create_issue", "user": user_email, "batch": batch_index, "suffix": unique_suffix})
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
            info("🦖 See, Nobody Cares. No issue was created.", extra={"feature": "create_issue", "user": user_email, "batch": batch_index, "suffix": unique_suffix})
            logger.info("🦖 See, Nobody Cares. No issue was created.")
            return
        filename = f"{output_dir}/{params['project']}_created_issue{unique_suffix}.md"
        write_create_issue_file(filename, issue.get('key', 'N/A'), params['summary'], user_email, batch_index, unique_suffix, context=context, issue=issue)
        json_filename = f"{output_dir}/{params['project']}_created_issue{unique_suffix}.json"
        write_create_issue_json(json_filename, issue, user_email, batch_index, unique_suffix, context=context)
        celebrate_success()
        info_spared_no_expense()
        info(f"🦖 Created issue written to {filename}", extra={"feature": "create_issue", "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        logger.info(f"🦖 [create_issue] Issue creation complete | Suffix: {unique_suffix}")
    except KeyboardInterrupt:
        logger.warning("[create_issue] Graceful exit via KeyboardInterrupt.")
        info("Graceful exit from Create Issue feature.", extra=context)
    except Exception as e:
        logger.exception(f"🦖 [create_issue] Exception: {e}")
        error(f"🦖 [create_issue] Exception: {e}", extra={"feature": "create_issue", "user": user_email, "batch": batch_index, "suffix": unique_suffix})
        raise 