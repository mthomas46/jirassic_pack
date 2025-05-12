import os
import questionary
from jirassicpack.cli import ensure_output_dir
from datetime import datetime
from jirassicpack.utils import get_option, validate_required, validate_date, spinner, error, info, safe_get, build_context, write_markdown_file, require_param, render_markdown_report, redact_sensitive, contextual_log
from jirassicpack.features.time_tracking_worklogs import select_jira_user
import time

def prompt_summarize_tickets_options(options, jira=None):
    """
    Prompt for summarize tickets options, always requiring explicit user selection. Config/env value is only used if the user selects it.
    """
    info(f"[DEBUG] prompt_summarize_tickets_options called. jira is {'present' if jira else 'None'}. options: {options}")
    config_user = options.get('user') or os.environ.get('JIRA_USER')
    user_obj = None
    username = None
    if jira:
        info("Please select a Jira user for ticket summarization.")
        menu_choices = [
            "Search for a user",
            "Pick from list",
            "Use current user",
        ]
        if config_user:
            menu_choices.append(f"Use value from config/env: {config_user}")
        menu_choices += ["Enter manually", "Abort"]
        while True:
            method = questionary.select("How would you like to select the user?", choices=menu_choices).ask()
            if method == "Search for a user":
                label, user_obj = select_jira_user(jira)
                username = user_obj.get('accountId') if user_obj else None
            elif method == "Pick from list":
                label, user_obj = select_jira_user(jira)
                username = user_obj.get('accountId') if user_obj else None
            elif method == "Use current user":
                try:
                    me = jira.get_current_user()
                    username = me.get('accountId')
                except Exception:
                    info("Could not retrieve current user from Jira.")
                    continue
            elif method.startswith("Use value from config/env"):
                username = config_user
            elif method == "Enter manually":
                username = questionary.text("Enter Jira accountId or username:").ask()
            elif method == "Abort":
                info("Aborted user selection for ticket summarization.")
                return None
            if username:
                break
    else:
        username = get_option(options, 'user', prompt="Jira Username for summary:", default=config_user, required=True)
    config_start = options.get('start_date') or os.environ.get('JIRA_START_DATE', '2024-01-01')
    config_end = options.get('end_date') or os.environ.get('JIRA_END_DATE', '2024-01-31')
    start_date = get_option(options, 'start_date', prompt="Start date (YYYY-MM-DD):", default=config_start, required=True, validate=validate_date)
    end_date = get_option(options, 'end_date', prompt="End date (YYYY-MM-DD):", default=config_end, required=True, validate=validate_date)
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
    Summarize tickets for a user or team and write to a Markdown file.
    """
    context = build_context("summarize_tickets", user_email, batch_index, unique_suffix)
    try:
        contextual_log('info', f"📝 [Summarize Tickets] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='summarize_tickets')
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
            with spinner("📝 Summarizing Tickets..."):
                issues = jira.search_issues(jql, fields=fields, max_results=100)
        except Exception as e:
            contextual_log('error', f"📝 [Summarize Tickets] Failed to fetch issues: {e}", exc_info=True, operation="api_call", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='summarize_tickets')
            error(f"Failed to fetch issues: {e}. Please check your Jira connection, credentials, and network.", extra=context)
            return
        total_issues = len(issues)
        lines = [
            f"# Ticket Summary for {username}\n",
            f"Timeframe: {start_date} to {end_date}\n\n",
            f"**Total issues completed:** {total_issues}\n\n",
            "## Issues List\n"
        ]
        for issue in issues:
            key = issue.get('key', 'N/A')
            summary = safe_get(issue, ['fields', 'summary'])
            status = safe_get(issue, ['fields', 'status', 'name'])
            resolved = safe_get(issue, ['fields', 'resolutiondate'])
            lines.append(f"- **{key}**: {summary} (Status: {status}, Resolved: {resolved})\n")
        filename = f"{output_dir}/{username}_{start_date}_to_{end_date}_summary{unique_suffix}.md"
        summary_section = f"**Total tickets summarized:** {total_issues}\n\n**Highlights:** ..."
        details_section = "| Key | Summary | Status | Resolved |\n|-----|---------|--------|----------|\n"
        for issue in issues:
            details_section += f"| {issue.get('key', 'N/A')} | {safe_get(issue, ['fields', 'summary'])} | {safe_get(issue, ['fields', 'status', 'name'])} | {safe_get(issue, ['fields', 'resolutiondate'])} |\n"
        content = render_markdown_report(
            feature="summarize_tickets",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="Ticket Summary",
            summary_section=summary_section,
            main_content_section=details_section
        )
        with open(filename, 'w') as f:
            f.write(content)
        contextual_log('info', f"📝 [Summarize Tickets] Summary report written to {filename}", operation="output_write", output_file=filename, status="success", extra=context, feature='summarize_tickets')
        info(f"📝 Summary report written to {filename}", extra=context)
        duration = int((time.time() - context.get('start_time', 0)) * 1000) if context.get('start_time') else None
        contextual_log('info', f"📝 [Summarize Tickets] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}).", operation="feature_end", status="success", params=redact_sensitive(params), extra=context, feature='summarize_tickets')
    except KeyboardInterrupt:
        contextual_log('warning', "📝 [Summarize Tickets] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context, feature='summarize_tickets')
        info("Graceful exit from Summarize Tickets feature.", extra=context)
    except Exception as e:
        contextual_log('error', f"📝 [Summarize Tickets] Exception occurred: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='summarize_tickets')
        error(f"📝 [Summarize Tickets] Exception: {e}", extra=context)
        raise 