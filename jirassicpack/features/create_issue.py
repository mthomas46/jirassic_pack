# create_issue.py
# This feature allows users to create a new Jira issue by prompting for project, summary, description, and issue type.
# It writes the created issue's key and summary to a Markdown file for record-keeping.

from jirassicpack.utils.io import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, spinner, info_spared_no_expense, prompt_with_validation, info, get_option, make_output_filename, render_markdown_report_template, status_emoji
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.utils.jira import get_valid_project_key, get_valid_issue_type
from jirassicpack.utils.io import validate_required, error, render_markdown_report
from typing import Any, Dict
import logging
import json
import time
from marshmallow import Schema, fields, ValidationError, pre_load, validate
from jirassicpack.utils.rich_prompt import rich_error
import re
from jirassicpack.utils.fields import IssueKeyField, ProjectKeyField, BaseOptionsSchema, validate_nonempty
from datetime import datetime
from mdutils.mdutils import MdUtils

class CreateIssueOptionsSchema(BaseOptionsSchema):
    project = ProjectKeyField(required=True, error_messages={"required": "Project key is required."})
    summary = fields.Str(required=True, error_messages={"required": "Summary is required."}, validate=validate_nonempty)
    description = fields.Str(load_default='', validate=validate_nonempty)
    issue_type = fields.Str(load_default='Task', validate=validate.OneOf(['Task', 'Bug', 'Story']))
    # output_dir and unique_suffix are inherited

def prompt_create_issue_options(opts: Dict[str, Any], jira: Any = None) -> Dict[str, Any]:
    """
    Prompt for create issue options using Jira-aware helpers for project and issue type.
    Args:
        opts (Dict[str, Any]): Options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.
    Returns:
        Dict[str, Any]: Validated options for the feature.
    """
    schema = CreateIssueOptionsSchema()
    data = dict(opts)
    while True:
        try:
            validated = schema.load(data)
            return validated
        except ValidationError as err:
            for field, msgs in err.messages.items():
                suggestion = None
                if isinstance(msgs, list) and msgs and isinstance(msgs[0], tuple):
                    # Marshmallow 4+ error tuples: (message, suggestion)
                    message, suggestion = msgs[0]
                elif isinstance(msgs, list) and msgs:
                    message = msgs[0]
                else:
                    message = str(msgs)
                if field == 'project' and jira:
                    data['project'] = get_valid_project_key(jira)
                else:
                    data[field] = get_option(data, field, prompt=f"🦖 {field.replace('_', ' ').title()}: ", required=True)
                rich_error(f"Input validation error for '{field}': {message}", suggestion)
            continue

def write_create_issue_file(
    filename: str,
    issue_key: str,
    summary: str,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None,
    context: dict = None,
    issue: dict = None
) -> None:
    """
    Write a Markdown file for a created Jira issue, including a report header, summary, and standardized layout.
    Args:
        filename (str): Output file path.
        issue_key (str): Key of the created issue.
        summary (str): Summary of the created issue.
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
        context (dict, optional): Additional context for logging.
        issue (dict, optional): Full issue data from Jira.
    Returns:
        None. Writes a Markdown report to disk.
    """
    from jirassicpack.config import ConfigLoader
    jira_conf = ConfigLoader().get_jira_config()
    base_url = jira_conf['url'].rstrip('/')
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M')
    link = f"{base_url}/browse/{issue_key}"
    # Report header
    header = f"# 📝 Create Issue Report\n\n"
    header += f"**Feature:** Create Issue  "
    header += f"**Issue Key:** [{issue_key}]({link})  "
    header += f"**Project:** {issue.get('fields', {}).get('project', {}).get('key', 'N/A')}  "
    header += f"**Type:** {issue.get('fields', {}).get('issuetype', {}).get('name', 'N/A')}  "
    header += f"**Created by:** {user_email}  "
    header += f"**Created at:** {created_at}  "
    if batch_index is not None:
        header += f"**Batch index:** {batch_index}  "
    header += "\n\n---\n\n"
    # Table of contents (not needed for single issue, but placeholder)
    toc = ""
    # Report summary table
    summary_table = "| Field | Value |\n|---|---|\n"
    fields = [
        ("Key", issue_key),
        ("Project", issue.get('fields', {}).get('project', {}).get('key', 'N/A')),
        ("Type", issue.get('fields', {}).get('issuetype', {}).get('name', 'N/A')),
        ("Summary", summary),
        ("Description", issue.get('fields', {}).get('description', '')),
        ("Reporter", issue.get('fields', {}).get('reporter', {}).get('displayName', 'N/A')),
        ("Assignee", issue.get('fields', {}).get('assignee', {}).get('displayName', 'N/A')),
        ("Status", issue.get('fields', {}).get('status', {}).get('name', 'N/A')),
        ("Created", issue.get('fields', {}).get('created', '')),
        ("Updated", issue.get('fields', {}).get('updated', '')),
    ]
    for k, v in fields:
        summary_table += f"| {k} | {v} |\n"
    summary_table += "\n---\n\n"
    # Action items (e.g., if not assigned or not in Done)
    action_items = "## Action Items\n"
    status = issue.get('fields', {}).get('status', {}).get('name', '').lower()
    assignee = issue.get('fields', {}).get('assignee', {}).get('displayName', '')
    if not assignee:
        action_items += "- ⚠️ No assignee set.\n"
    if status not in ['done', 'closed', 'resolved']:
        action_items += f"- ⏳ Issue is not resolved (status: {status.title()})\n"
    if action_items.strip() == "## Action Items":
        action_items += "- No immediate action items.\n"
    # Top N lists (not as relevant for single issue, but placeholder)
    top_n_lists = ""
    # Related links
    related_links = f"## Related Links\n- [View in Jira]({link})\n- [Project Dashboard]({base_url}/projects)\n"
    # Grouped issue section (single issue)
    grouped_section = "## Issue Details\n\n"
    grouped_section += "| Field | Value |\n|---|---|\n"
    for k, v in fields:
        grouped_section += f"| {k} | {v} |\n"
    grouped_section += "\n---\n\n"
    grouped_section += f"- [View in Jira]({link})\n"
    if issue:
        grouped_section += "<details><summary>Raw Issue JSON</summary>\n\n"
        grouped_section += "```json\n" + json.dumps(issue, indent=2) + "\n```"
        grouped_section += "\n</details>\n"
    # Export metadata
    export_metadata = f"---\n**Report generated by:** {user_email}  \n**Run at:** {created_at}  \n"
    # Glossary
    glossary = "## Glossary\n- ⚠️ Needs attention\n- ⏳ Not resolved\n"
    # Next steps
    next_steps = "## Next Steps\n"
    if not assignee:
        next_steps += "- Assign this issue to a team member.\n"
    if status not in ['done', 'closed', 'resolved']:
        next_steps += "- Move the issue to Done/Closed when resolved.\n"
    if next_steps.strip() == "## Next Steps":
        next_steps += "- No immediate next steps.\n"
    # Compose final report
    report = render_markdown_report_template(
        report_header=header,
        table_of_contents=toc,
        report_summary=summary_table,
        action_items=action_items,
        top_n_lists=top_n_lists,
        related_links=related_links,
        grouped_issue_sections=grouped_section,
        export_metadata=export_metadata,
        glossary=glossary,
        next_steps=next_steps
    )
    output_path = filename
    md_file = MdUtils(file_name=output_path, title="Create Issue Report")
    md_file.new_line(f"_Generated: {datetime.now()}_")
    md_file.new_header(level=2, title="Summary")
    md_file.new_line(report)
    md_file.create_md_file()
    info(f"🦖 Create issue report written to {output_path}")

def write_create_issue_json(filename: str, issue: dict, user_email: str = None, batch_index: int = None, unique_suffix: str = None, context: dict = None) -> None:
    """
    Write the created issue details to a JSON file for record-keeping.
    Args:
        filename (str): Output file path.
        issue (dict): Issue data from Jira.
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
        context (dict, optional): Additional context for logging.
    Returns:
        None. Writes a JSON file to disk.
    """
    try:
        with open(filename, 'w') as f:
            json.dump(issue, f, indent=2)
        info(f"🦖 Created issue details written to {filename}", extra=context)
    except Exception as e:
        error(f"Failed to write created issue JSON file: {e}", extra=context)

def create_issue(jira: Any, params: Dict[str, Any], user_email: str = None, batch_index: int = None, unique_suffix: str = None) -> None:
    """
    Main feature entrypoint for creating a Jira issue. Handles validation, creation, and report writing.
    Args:
        jira (Any): Authenticated Jira client instance.
        params (Dict[str, Any]): Parameters for the issue (project, summary, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
    Returns:
        None. Writes Markdown and JSON reports to disk.
    """
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
        params_list = [("project", project), ("summary", summary), ("issue_type", params.get("issue_type"))]
        filename = make_output_filename("create_issue", params_list, output_dir)
        write_create_issue_file(filename, issue.get('key', 'N/A'), params['summary'], user_email, batch_index, unique_suffix, context=context, issue=issue)
        contextual_log('info', f"Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=context, feature='create_issue')
        json_filename = make_output_filename("create_issue", params_list, output_dir, ext="json")
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