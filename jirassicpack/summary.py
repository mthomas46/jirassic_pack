import os
import questionary
from jirassicpack.cli import ensure_output_dir
from datetime import datetime
from jirassicpack.utils import get_option, validate_required, validate_date, spinner, error, info, safe_get, build_context, write_markdown_file, require_param, render_markdown_report

def prompt_summarize_tickets_options(options):
    username = get_option(options, 'user', prompt="Jira Username for summary:", default=os.environ.get('JIRA_USER', ''), required=True)
    start_date = get_option(options, 'start_date', prompt="Start date (YYYY-MM-DD):", default=os.environ.get('JIRA_START_DATE', '2024-01-01'), required=True, validate=validate_date)
    end_date = get_option(options, 'end_date', prompt="End date (YYYY-MM-DD):", default=os.environ.get('JIRA_END_DATE', '2024-01-31'), required=True, validate=validate_date)
    output_dir = get_option(options, 'output_dir', default=os.environ.get('JIRA_OUTPUT_DIR', 'output'))
    unique_suffix = options.get('unique_suffix', '')
    ac_field = options.get('acceptance_criteria_field') or os.environ.get('JIRA_ACCEPTANCE_CRITERIA_FIELD', 'customfield_10001')
    return {
        'user': username,
        'start_date': start_date,
        'end_date': end_date,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix,
        'acceptance_criteria_field': ac_field
    }

def summarize_tickets(jira, params, user_email=None, batch_index=None, unique_suffix=None):
    """
    Consolidate comments, descriptions, titles, acceptance criteria, and other info into a summary for a set of tickets.
    Write the summary to a Markdown file.
    """
    context = build_context("summarize_tickets", user_email, batch_index, unique_suffix)
    if not require_param(params, 'user', context):
        return
    if not require_param(params, 'start_date', context):
        return
    if not require_param(params, 'end_date', context):
        return
    username = params.get('user')
    start_date = params.get('start_date')
    end_date = params.get('end_date')
    output_dir = params.get('output_dir', 'output')
    unique_suffix = params.get('unique_suffix', '')
    ac_field = params.get('acceptance_criteria_field', os.environ.get('JIRA_ACCEPTANCE_CRITERIA_FIELD', 'customfield_10001'))
    ensure_output_dir(output_dir)
    jql = (
        f"assignee = '{username}' "
        f"AND updated >= '{start_date}' "
        f"AND updated <= '{end_date}'"
    )
    fields = ["summary", "description", "comment", ac_field, "key"]
    try:
        with spinner("🗂️ Summarizing Tickets..."):
            issues = jira.search_issues(jql, fields=fields, max_results=50)
    except Exception as e:
        error(f"Failed to fetch issues: {e}. Please check your Jira connection, credentials, and network.", extra=context)
        return
    lines = [
        f"# Ticket Summary for {username}\n",
        f"Timeframe: {start_date} to {end_date}\n\n"
    ]
    for issue in issues:
        key = issue.get('key', 'N/A')
        summary = safe_get(issue, ['fields', 'summary'], '')
        description = safe_get(issue, ['fields', 'description'], '')
        acceptance_criteria = safe_get(issue, ['fields', ac_field], '')
        comments = safe_get(issue, ['fields', 'comment', 'comments'], [])
        lines.append(f"## {key}: {summary}\n")
        lines.append(f"**Description:**\n{description}\n\n")
        if acceptance_criteria:
            lines.append(f"**Acceptance Criteria:**\n{acceptance_criteria}\n\n")
        if comments:
            lines.append("**Comments:**\n")
            for c in comments:
                author = safe_get(c, ['author', 'displayName'], 'Unknown')
                body = safe_get(c, ['body'], '')
                lines.append(f"- {author}: {body}\n")
        lines.append("\n---\n\n")
    filename = f"{output_dir}/{username}_{start_date}_to_{end_date}_summary{unique_suffix}.md"
    content = render_markdown_report(
        feature="summarize_tickets",
        user=user_email,
        batch=batch_index,
        suffix=unique_suffix,
        feature_title="Ticket Summarization",
        summary_section="**Total tickets summarized:** {{total}}\n\n**Highlights:** ..."
    )
    with open(filename, 'w') as f:
        f.write(content)
    info(f"🗂️ Ticket summary written to {filename}", extra=context) 