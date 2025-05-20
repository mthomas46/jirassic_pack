"""
deep_ticket_summary.py

Feature module for generating a deep summary report for a single Jira ticket via the CLI.
Fetches all available information (description, comments, changelog, fields, etc.) and outputs a detailed Markdown report for audit and review.
"""

from jirassicpack.utils.io import ensure_output_dir, info, spinner, safe_get, get_option, status_emoji, feature_error_handler, write_report
from jirassicpack.utils.logging import contextual_log, build_context
from jirassicpack.config import ConfigLoader
from datetime import datetime
import os
from typing import Any
from jirassicpack.analytics.helpers import build_report_sections


@feature_error_handler('deep_ticket_summary')
def deep_ticket_summary(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Generate a deep summary report for a single Jira ticket, including all available information:
    - Description
    - Comments/discussion
    - Edits/changelog
    - Acceptance criteria
    - Resolution
    - Contextual fields (priority, type, status, reporter, assignee, components, labels, etc.)
    - Professional summary of the ticket's lifecycle

    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the summary (issue key, output_dir, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
    Returns:
        None. Writes a Markdown report to disk.
    """
    issue_key = params.get("issue_key")
    output_dir = params.get("output_dir", "output")
    ensure_output_dir(output_dir)
    context = build_context("deep_ticket_summary", user_email, batch_index, unique_suffix, issue_key=issue_key)
    with spinner(f"Fetching issue {issue_key}..."):
        issue = jira.get_task(issue_key, expand=["changelog", "renderedFields"])
    if not issue or not issue.get('fields'):
        info(f"🦖 See, Nobody Cares. No data found for issue {issue_key}.", extra=context)
        contextual_log('info', f"🦖 See, Nobody Cares. No data found for issue {issue_key}.", extra=context)
        return
    fields = issue.get("fields", {})
    changelog = issue.get("changelog", {}).get("histories", [])
    description = fields.get("description", "")
    config = ConfigLoader()
    ac_field = params.get("acceptance_criteria_field") or config.get("acceptance_criteria_field", "customfield_10001")
    acceptance_criteria = fields.get(ac_field, "")
    comments = safe_get(fields, ["comment", "comments"], [])
    resolution = fields.get("resolution", {}).get("name", "N/A")
    status = fields.get("status", {}).get("name", "N/A")
    reporter = fields.get("reporter", {}).get("displayName", "N/A")
    assignee = fields.get("assignee", {}).get("displayName", "N/A")
    priority = fields.get("priority", {}).get("name", "N/A")
    issue_type = fields.get("issuetype", {}).get("name", "N/A")
    created = fields.get("created", "")
    updated = fields.get("updated", "")
    resolved = fields.get("resolutiondate", "")
    components = ', '.join([c['name'] for c in fields.get('components', [])])
    labels = ', '.join(fields.get('labels', []))
    project = safe_get(fields, ["project", "key"], "N/A")
    # --- Compose report sections ---
    header = "# 🦖 Deep Ticket Summary\n\n"
    header += f"**Key:** {issue_key}  "
    header += f"**Project:** {project}  "
    header += f"**Type:** {issue_type}  "
    header += f"**Status:** {status_emoji(status)} {status}  "
    header += f"**Priority:** {priority}  "
    header += f"**Reporter:** {reporter}  "
    header += f"**Assignee:** {assignee}  "
    header += f"**Created:** {created}  "
    header += f"**Updated:** {updated}  "
    header += f"**Resolved:** {resolved}  "
    header += f"**Components:** {components}  "
    header += f"**Labels:** {labels}  "
    header += f"**Resolution:** {resolution}  "
    header += "\n\n---\n\n"
    toc = "## Table of Contents\n- [Description](#description)\n- [Acceptance Criteria](#acceptance-criteria)\n- [Comments & Discussion](#comments--discussion)\n- [Changelog & Edits](#changelog--edits)\n- [Resolution](#resolution)\n- [Lifecycle Summary](#lifecycle-summary)\n\n"
    summary_table = "| Field | Value |\n|---|---|\n"
    summary_table += f"| Key | {issue_key} |\n"
    summary_table += f"| Project | {project} |\n"
    summary_table += f"| Type | {issue_type} |\n"
    summary_table += f"| Status | {status} |\n"
    summary_table += f"| Priority | {priority} |\n"
    summary_table += f"| Reporter | {reporter} |\n"
    summary_table += f"| Assignee | {assignee} |\n"
    summary_table += f"| Created | {created} |\n"
    summary_table += f"| Updated | {updated} |\n"
    summary_table += f"| Resolved | {resolved} |\n"
    summary_table += f"| Components | {components} |\n"
    summary_table += f"| Labels | {labels} |\n"
    summary_table += f"| Resolution | {resolution} |\n"
    summary_table += "\n---\n\n"
    # Comments Section
    comments_section = ""
    if comments:
        for comment in comments:
            author = comment.get('author', {}).get('displayName', 'Unknown')
            body = comment.get('body', '')
            created_c = comment.get('created', '')
            comments_section += f"- **{author}** ({created_c}): {body}\n"
    else:
        comments_section = "_No comments found._\n"
    # Changelog Section
    changelog_section = ""
    if changelog:
        for entry in changelog:
            author = entry.get('author', {}).get('displayName', 'Unknown')
            created_e = entry.get('created', '')
            items = entry.get('items', [])
            for change_item in items:
                field = change_item.get('field', '')
                from_val = change_item.get('fromString', '')
                to_val = change_item.get('toString', '')
                changelog_section += f"- **{author}** ({created_e}): Changed **{field}** from '{from_val}' to '{to_val}'\n"
    else:
        changelog_section = "_No changelog entries found._\n"
    # Lifecycle Summary
    lifecycle_summary = f"This ticket was created by **{reporter}** on {created}, assigned to **{assignee}**, and went through status changes as detailed above. It was resolved as **{resolution}** on {resolved or 'N/A'}.\n\nFor more context, see the full changelog and comments above."
    # Compose final report using build_report_sections
    sections = {
        'header': header,
        'toc': toc,
        'summary': summary_table,
        'grouped_sections': f"## Description\n{description or '_No description provided._'}\n\n## Acceptance Criteria\n{acceptance_criteria or '_No acceptance criteria provided._'}\n\n## Comments & Discussion\n{comments_section}\n\n## Changelog & Edits\n{changelog_section}\n\n## Resolution\n{resolution or '_No resolution provided._'}\n\n## Lifecycle Summary\n{lifecycle_summary}",
        'metadata': f"---\n**Report generated by:** {user_email}  \n**Run at:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n",
        'glossary': "",
        'next_steps': "",
    }
    report = build_report_sections(sections)
    filename = os.path.join(output_dir, f"deep_ticket_summary_{issue_key}.md")
    write_report(filename, report, context, filetype='md', feature='deep_ticket_summary', item_name='Deep ticket summary report')
    info(f"🦖 Deep ticket summary written to {filename}", extra=context)


def prompt_deep_ticket_summary_options(opts: dict, jira: Any = None) -> dict:
    """
    Prompt for deep ticket summary options for the CLI.

    Args:
        opts (dict): Initial options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.

    Returns:
        dict: Validated options for the feature, or None if aborted.
    """
    issue_key = get_option(opts, 'issue_key', prompt="🦖 Jira Issue Key (e.g., DEMO-123):", required=True, abort_option=True)
    if issue_key == "__ABORT__":
        info("❌ Aborted deep ticket summary prompt.")
        return None
    output_dir = get_option(opts, 'output_dir', default='output', abort_option=True)
    if output_dir == "__ABORT__":
        info("❌ Aborted deep ticket summary prompt.")
        return None
    unique_suffix = opts.get('unique_suffix', '')
    ac_field = get_option(opts, 'acceptance_criteria_field', prompt="Acceptance Criteria Field (optional):", default=None, abort_option=True)
    if ac_field == "__ABORT__":
        info("❌ Aborted deep ticket summary prompt.")
        return None
    return {
        'issue_key': issue_key,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix,
        'acceptance_criteria_field': ac_field,
    } 