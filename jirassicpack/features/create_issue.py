# create_issue.py
# This feature allows users to create a new Jira issue by prompting for project, summary, description, and issue type.
# It writes the created issue's key and summary to a Markdown file for record-keeping.

from jirassicpack.utils.io import ensure_output_dir, celebrate_success, retry_or_skip, spinner, info_spared_no_expense, info, make_output_filename, feature_error_handler, write_output_file, prompt_with_schema
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.utils.io import error
from typing import Any
import json
import time
from marshmallow import fields, validate
from jirassicpack.utils.fields import ProjectKeyField, BaseOptionsSchema, validate_nonempty
from datetime import datetime
from jirassicpack.constants import SEE_NOBODY_CARES, IS_REQUIRED
from jirassicpack.analytics.helpers import build_report_sections

class CreateIssueOptionsSchema(BaseOptionsSchema):
    project = ProjectKeyField(required=True, error_messages={"required": "Project key is required."})
    summary = fields.Str(required=True, error_messages={"required": "Summary is required."}, validate=validate_nonempty)
    description = fields.Str(load_default='', validate=validate_nonempty)
    issue_type = fields.Str(load_default='Task', validate=validate.OneOf(['Task', 'Bug', 'Story']))
    # output_dir and unique_suffix are inherited

def prompt_create_issue_options(opts: dict, jira: Any = None) -> dict:
    """
    Prompt for create issue options using Marshmallow schema for validation and Jira-aware helpers.

    Args:
        opts (dict): Initial options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.

    Returns:
        dict: Validated options for the feature, or None if aborted.
    """
    schema = CreateIssueOptionsSchema()
    result = prompt_with_schema(schema, dict(opts), jira=jira, abort_option=True)
    if result == "__ABORT__":
        info("❌ Aborted create issue prompt.")
        return None
    return result

@feature_error_handler('create_issue')
def create_issue(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Main feature entrypoint for creating a new Jira issue.

    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the issue (project, summary, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.

    Returns:
        None. Writes Markdown and JSON reports to disk.
    """
    correlation_id = params.get('correlation_id')
    context = build_context("create_issue", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
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
        error(IS_REQUIRED.format(field='project'), extra=context, feature='create_issue')
        contextual_log('error', "🦖 [Create Issue] Project is required but missing.", operation="validation", status="error", extra=context, feature='create_issue')
        return
    summary = params.get('summary')
    if not summary:
        error(IS_REQUIRED.format(field='summary'), extra=context, feature='create_issue')
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
        info(SEE_NOBODY_CARES, extra=context, feature='create_issue')
        contextual_log('warning', "No issue was created.", operation="feature_end", status="skipped", extra=context, feature='create_issue')
        return
    params_list = [("project", project), ("summary", summary), ("issue_type", params.get("issue_type"))]
    filename = make_output_filename("create_issue", params_list, output_dir)
    # Compose the markdown report content
    from jirassicpack.config import ConfigLoader
    jira_conf = ConfigLoader().get_jira_config()
    base_url = jira_conf['url'].rstrip('/')
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M')
    link = f"{base_url}/browse/{issue.get('key', 'N/A')}"
    header = f"# 📝 Create Issue Report\n\n"
    header += f"**Feature:** Create Issue  "
    header += f"**Issue Key:** [{issue.get('key', 'N/A')}]({link})  "
    header += f"**Project:** {issue.get('fields', {}).get('project', {}).get('key', 'N/A')}  "
    header += f"**Type:** {issue.get('fields', {}).get('issuetype', {}).get('name', 'N/A')}  "
    header += f"**Created by:** {user_email}  "
    header += f"**Created at:** {created_at}  "
    if batch_index is not None:
        header += f"**Batch index:** {batch_index}  "
    header += "\n\n---\n\n"
    toc = ""
    summary_table = "| Field | Value |\n|---|---|\n"
    fields = [
        ("Key", issue.get('key', 'N/A')),
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
    action_items = "## Action Items\n"
    status = issue.get('fields', {}).get('status', {}).get('name', '').lower()
    assignee = issue.get('fields', {}).get('assignee', {}).get('displayName', '')
    if not assignee:
        action_items += "- ⚠️ No assignee set.\n"
    if status not in ['done', 'closed', 'resolved']:
        action_items += f"- ⏳ Issue is not resolved (status: {status.title()})\n"
    if action_items.strip() == "## Action Items":
        action_items += "- No immediate action items.\n"
    top_n_lists = ""
    related_links = f"## Related Links\n- [View in Jira]({link})\n- [Project Dashboard]({base_url}/projects)\n"
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
    export_metadata = f"---\n**Report generated by:** {user_email}  \n**Run at:** {created_at}  \n"
    glossary = "## Glossary\n- ⚠️ Needs attention\n- ⏳ Not resolved\n"
    next_steps = "## Next Steps\n"
    if not assignee:
        next_steps += "- Assign this issue to a team member.\n"
    if status not in ['done', 'closed', 'resolved']:
        next_steps += "- Move the issue to Done/Closed when resolved.\n"
    if next_steps.strip() == "## Next Steps":
        next_steps += "- No immediate next steps.\n"
    report = build_report_sections({
        'header': header,
        'toc': toc,
        'summary': summary_table,
        'action_items': action_items,
        'top_n': top_n_lists,
        'related_links': related_links,
        'grouped_sections': grouped_section,
        'metadata': export_metadata,
        'glossary': glossary,
        'next_steps': next_steps,
    })
    write_output_file(filename, report, context, filetype='md', feature='create_issue')
    contextual_log('info', f"Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=context, feature='create_issue')
    json_filename = make_output_filename("create_issue", params_list, output_dir, ext="json")
    write_output_file(json_filename, issue, context, filetype='json', feature='create_issue')
    contextual_log('info', f"JSON file written: {json_filename}", operation="output_write", output_file=json_filename, status="success", extra=context, feature='create_issue')
    celebrate_success()
    info_spared_no_expense()
    info(f"🦖 Created issue written to {filename}", extra=context, feature='create_issue')
    duration = int((time.time() - start_time) * 1000)
    contextual_log('info', f"🦖 [Create Issue] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}). Duration: {duration}ms.", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='create_issue') 