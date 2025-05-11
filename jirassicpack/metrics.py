from datetime import datetime
import os
import questionary
from jirassicpack.cli import ensure_output_dir
from jirassicpack.utils import get_option, validate_required, validate_date, spinner, error, info, safe_get, build_context, write_markdown_file, require_param, render_markdown_report
from jirassicpack.features.time_tracking_worklogs import select_jira_user

def prompt_gather_metrics_options(options, jira=None):
    """
    Prompt for metrics options, always prompting for user selection (no default to current user).
    """
    username = options.get('user')
    if not username and jira:
        info("Please select a Jira user for metrics gathering.")
        username = select_jira_user(jira)
        if not username:
            info("Aborted user selection for metrics gathering.")
            return None
    elif not username:
        username = get_option(options, 'user', prompt="Jira Username for metrics:", required=True)
    start_date = get_option(options, 'start_date', prompt="Start date (YYYY-MM-DD):", default=os.environ.get('JIRA_START_DATE', '2024-01-01'), required=True, validate=validate_date)
    end_date = get_option(options, 'end_date', prompt="End date (YYYY-MM-DD):", default=os.environ.get('JIRA_END_DATE', '2024-01-31'), required=True, validate=validate_date)
    output_dir = get_option(options, 'output_dir', default=os.environ.get('JIRA_OUTPUT_DIR', 'output'))
    unique_suffix = options.get('unique_suffix', '')
    return {
        'user': username,
        'start_date': start_date,
        'end_date': end_date,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix
    }

def gather_metrics(jira, params, user_email=None, batch_index=None, unique_suffix=None):
    """
    Gather metrics for a specific user over a timeframe and write to a Markdown file.
    """
    context = build_context("gather_metrics", user_email, batch_index, unique_suffix)
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
    ensure_output_dir(output_dir)
    jql = (
        f"assignee = '{username}' "
        f"AND statusCategory = Done "
        f"AND resolved >= '{start_date}' "
        f"AND resolved <= '{end_date}'"
    )
    fields = ["summary", "status", "issuetype", "resolutiondate", "key"]
    try:
        with spinner("📈 Gathering Metrics..."):
            issues = jira.search_issues(jql, fields=fields, max_results=100)
    except Exception as e:
        error(f"Failed to fetch issues: {e}. Please check your Jira connection, credentials, and network.", extra=context)
        return
    total_issues = len(issues)
    issue_types = {}
    for issue in issues:
        issue_type = safe_get(issue, ['fields', 'issuetype', 'name'], 'Unknown')
        issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
    lines = [
        f"# Metrics for {username}\n",
        f"Timeframe: {start_date} to {end_date}\n\n",
        f"**Total issues completed:** {total_issues}\n\n",
        "## Issue Types\n"
    ]
    for t, count in issue_types.items():
        lines.append(f"- {t}: {count}\n")
    lines.append("\n## Issues List\n")
    for issue in issues:
        key = issue.get('key', 'N/A')
        summary = safe_get(issue, ['fields', 'summary'])
        status = safe_get(issue, ['fields', 'status', 'name'])
        resolved = safe_get(issue, ['fields', 'resolutiondate'])
        lines.append(f"- **{key}**: {summary} (Status: {status}, Resolved: {resolved})\n")
    filename = f"{output_dir}/{username}_{start_date}_to_{end_date}_metrics{unique_suffix}.md"
    summary_section = f"**Total metrics gathered:** {total_issues}\n\n**Highlights:** ..."
    details_section = "| Metric | Value |\n|--------|-------|\n"
    for metric, value in issue_types.items():
        details_section += f"| {metric} | {value} |\n"
    content = render_markdown_report(
        feature="gather_metrics",
        user=user_email,
        batch=batch_index,
        suffix=unique_suffix,
        feature_title="Metrics Gathering",
        summary_section=summary_section,
        main_content_section=details_section
    )
    with open(filename, 'w') as f:
        f.write(content)
    info(f"📈 Metrics report written to {filename}", extra=context) 