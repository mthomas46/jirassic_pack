from jirassicpack.utils.io import ensure_output_dir, info, error, spinner, safe_get, get_option, status_emoji
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.config import ConfigLoader
from jirassicpack.utils.rich_prompt import rich_error
from mdutils.mdutils import MdUtils
from datetime import datetime
import os
from typing import Any


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
    try:
        with spinner(f"Fetching issue {issue_key}..."):
            issue = jira.get_task(issue_key, expand=["changelog", "renderedFields"])  # fetch changelog for edits
        if not issue or not issue.get('fields'):
            info(f"🦖 See, Nobody Cares. No data found for issue {issue_key}.", extra=context)
            contextual_log('info', f"🦖 See, Nobody Cares. No data found for issue {issue_key}.", extra=context)
            return
        fields = issue.get("fields", {})
        changelog = issue.get("changelog", {}).get("histories", [])
        description = fields.get("description", "")
        ac_field = os.environ.get("JIRA_ACCEPTANCE_CRITERIA_FIELD", "customfield_10001")
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
        filename = os.path.join(output_dir, f"deep_ticket_summary_{issue_key}.md")
        md_file = MdUtils(file_name=filename, title=f"Deep Ticket Summary: {issue_key}")
        md_file.new_line(f"_Generated: {datetime.now()}_")
        md_file.new_header(level=2, title="Ticket Overview")
        md_file.new_line(f"**Key:** {issue_key}")
        md_file.new_line(f"**Project:** {project}")
        md_file.new_line(f"**Type:** {issue_type}")
        md_file.new_line(f"**Status:** {status_emoji(status)} {status}")
        md_file.new_line(f"**Priority:** {priority}")
        md_file.new_line(f"**Reporter:** {reporter}")
        md_file.new_line(f"**Assignee:** {assignee}")
        md_file.new_line(f"**Created:** {created}")
        md_file.new_line(f"**Updated:** {updated}")
        md_file.new_line(f"**Resolved:** {resolved}")
        md_file.new_line(f"**Components:** {components}")
        md_file.new_line(f"**Labels:** {labels}")
        md_file.new_line(f"**Resolution:** {resolution}")
        md_file.new_line('---')
        md_file.new_header(level=2, title="Description")
        md_file.new_line(description or "_No description provided._")
        md_file.new_header(level=2, title="Acceptance Criteria")
        md_file.new_line(acceptance_criteria or "_No acceptance criteria provided._")
        md_file.new_header(level=2, title="Comments & Discussion")
        if comments:
            for c in comments:
                author = c.get('author', {}).get('displayName', 'Unknown')
                body = c.get('body', '')
                created = c.get('created', '')
                md_file.new_line(f"- **{author}** ({created}): {body}")
        else:
            md_file.new_line("_No comments found._")
        md_file.new_header(level=2, title="Changelog & Edits")
        if changelog:
            for entry in changelog:
                author = entry.get('author', {}).get('displayName', 'Unknown')
                created = entry.get('created', '')
                items = entry.get('items', [])
                for item in items:
                    field = item.get('field', '')
                    from_val = item.get('fromString', '')
                    to_val = item.get('toString', '')
                    md_file.new_line(f"- **{author}** ({created}): Changed **{field}** from '{from_val}' to '{to_val}'")
        else:
            md_file.new_line("_No changelog entries found._")
        md_file.new_header(level=2, title="Resolution")
        md_file.new_line(resolution or "_No resolution provided._")
        md_file.new_header(level=2, title="Lifecycle Summary")
        md_file.new_line(f"This ticket was created by **{reporter}** on {created}, assigned to **{assignee}**, and went through status changes as detailed above. It was resolved as **{resolution}** on {resolved or 'N/A'}.\n\nFor more context, see the full changelog and comments above.")
        md_file.create_md_file()
        info(f"🦖 Deep ticket summary written to {filename}", extra=context)
    except Exception as e:
        contextual_log('error', f"🦖 [Deep Ticket Summary] Exception occurred: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=params, extra=context)
        error(f"🦖 [Deep Ticket Summary] Exception: {e}", extra=context)
        raise 