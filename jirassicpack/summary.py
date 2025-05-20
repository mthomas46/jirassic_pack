"""
summary.py

Generates summary reports for Jira tickets, including grouping, top assignees, and action items. Provides interactive prompts for user/date selection and outputs professional Markdown reports. Used for analytics and reporting features in Jirassic Pack CLI.
"""
import os
from jirassicpack.utils.io import ensure_output_dir, spinner, error, info, get_option, validate_date, safe_get, require_param, render_markdown_report, make_output_filename, status_emoji, write_report, log_entry_exit
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.utils.jira import select_jira_user
from datetime import datetime
import time
from marshmallow import Schema, fields, ValidationError
from jirassicpack.utils.rich_prompt import rich_error
from typing import Any
from jirassicpack.analytics.helpers import build_report_sections, group_issues_by_field, make_top_n_list
import logging
import traceback
from functools import wraps

class SummarizeTicketsOptionsSchema(Schema):
    user = fields.Str(required=True)
    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)

def prompt_summarize_tickets_options(options: dict, jira: Any = None) -> dict:
    """
    Prompt for summarize tickets options, always requiring explicit user selection. Config/env value is only used if the user selects it.

    Args:
        options (dict): Options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.

    Returns:
        dict: Validated options for the feature, or None if aborted.
    """
    info(f"[DEBUG] prompt_summarize_tickets_options called. jira is {'present' if jira else 'None'}. options: {options}")
    config_user = options.get('user') or os.environ.get('JIRA_USER')
    user_obj = None
    username = None
    display_name = None
    if jira:
        info("Please select a Jira user for ticket summarization.")
        label, user_obj = select_jira_user(jira, default_user=config_user)
        username = user_obj.get('accountId') if user_obj else None
        display_name = user_obj.get('displayName') if user_obj else None
        if not username:
            info("❌ Aborted summarize tickets prompt.")
            return None
    else:
        username = get_option(options, 'user', prompt="Jira Username for summary:", default=config_user, required=True, abort_option=True)
        if username == "__ABORT__":
            info("❌ Aborted summarize tickets prompt.")
            return None
        display_name = None
    config_start = options.get('start_date') or os.environ.get('JIRA_START_DATE', '2024-01-01')
    config_end = options.get('end_date') or os.environ.get('JIRA_END_DATE', '2024-01-31')
    while True:
        start_date = get_option(options, 'start_date', prompt="Start date (YYYY-MM-DD):", default=config_start, required=True, validate=validate_date)
        end_date = get_option(options, 'end_date', prompt="End date (YYYY-MM-DD):", default=config_end, required=True, validate=validate_date)
        output_dir = get_option(options, 'output_dir', default=os.environ.get('JIRA_OUTPUT_DIR', 'output'))
        unique_suffix = options.get('unique_suffix', '')
        ac_field = options.get('acceptance_criteria_field') or os.environ.get('JIRA_ACCEPTANCE_CRITERIA_FIELD', 'customfield_10001')
        schema = SummarizeTicketsOptionsSchema()
        try:
            validated = schema.load({
                'user': username,
                'start_date': start_date,
                'end_date': end_date,
            })
            break
        except ValidationError as err:
            rich_error(f"Input validation error: {err.messages}")
            continue
    # Use validated values
    user = validated['user']
    config_start = str(validated['start_date'])
    config_end = str(validated['end_date'])
    return {
        'user': user,
        'user_display_name': display_name,
        'start_date': start_date,
        'end_date': end_date,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix,
        'acceptance_criteria_field': ac_field
    }

prompt_summarize_tickets_options = log_entry_exit(prompt_summarize_tickets_options)

def summarize_tickets(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Generate a summary report of Jira tickets based on the provided parameters.
    Fetches issues, groups by type, and outputs a Markdown report with summary, action items, top assignees, and more.
    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the summary (dates, filters, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
    Returns:
        None. Writes a Markdown report to disk.
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
        display_name = params.get('user_display_name')
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        ensure_output_dir(output_dir)
        # Try to get display name/accountId for header
        if not display_name:
            display_name = username
            account_id = username
            try:
                user_obj = jira.get_user(account_id=username)
                display_name = user_obj.get('displayName', username)
                account_id = user_obj.get('accountId', username)
            except Exception:
                pass
        else:
            account_id = username
        # Build JQL for summary
        jql = (
            f"assignee = '{username}' "
            f"AND resolved >= '{start_date}' "
            f"AND resolved <= '{end_date}'"
        )
        info(f"[summarize_tickets] Using JQL: {jql}")
        info(f"[summarize_tickets] Using user accountId: {username}")
        fields = ["summary", "created", "resolutiondate", "status", "key", "issuetype", "priority", "duedate", "assignee", "changelog"]
        try:
            with spinner("🦖 Summarizing Tickets..."):
                issues = jira.search_issues(jql, fields=fields, max_results=100)
            info(f"[summarize_tickets] Fetched {len(issues) if issues else 0} issues for user {username}.")
            contextual_log('debug', f"[summarize_tickets] Type of issues: {type(issues)} | Length: {len(issues) if issues is not None else 'None'}", extra=context, feature='summarize_tickets')
            if issues:
                contextual_log('debug', f"[summarize_tickets] First 2 issues: {issues[:2]}", extra=context, feature='summarize_tickets')
            info(f"[summarize_tickets][DIAG] Type of issues: {type(issues)} | Length: {len(issues) if issues is not None else 'None'} | id: {id(issues)}")
            if issues:
                info(f"[summarize_tickets][DIAG] First 2 issues: {str(issues[:2])}")
            # --- FORCE ISSUES TO BE A REAL LIST ---
            issues_before = issues
            issues = list(issues) if issues is not None else []
            info(f"[summarize_tickets][DIAG][POST-LIST] Type: {type(issues)}, Length: {len(issues)}, id: {id(issues)}")
            if id(issues) != id(issues_before):
                info(f"[summarize_tickets][DIAG][REASSIGNMENT] issues variable was reassigned after list(). Old id: {id(issues_before)}, New id: {id(issues)}")
            # --------------------------------------
        except Exception as e:
            contextual_log('error', f"🦖 [Summarize Tickets] Failed to fetch issues: {e}", exc_info=True, operation="api_call", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='summarize_tickets')
            error(f"Failed to fetch issues: {e}. Please check your Jira connection, credentials, and network.", extra=context, feature='summarize_tickets')
            return
        # DIAGNOSTIC: Log id and length of issues right before the check
        info(f"[summarize_tickets][DIAG][REPR] repr(issues): {repr(issues)}")
        info(f"[summarize_tickets][DIAG][ALL BOOLS] bool(issues): {bool(issues)}, len(issues): {len(issues)}")
        if not issues:
            if len(issues) > 0:
                raise RuntimeError(f"[summarize_tickets][DIAG][IMPOSSIBLE] len(issues) > 0 but not issues is True! issues: {repr(issues)}")
            contextual_log('debug', f"[summarize_tickets] Entered 'no issues found' branch. issues: {issues}", extra=context, feature='summarize_tickets')
            info(f"[summarize_tickets][DIAG] Entered 'no issues found' branch. issues: {str(issues)}")
            error(f"[summarize_tickets] No issues found. JQL: {jql} | user: {username} | start_date: {start_date} | end_date: {end_date}", extra=context, feature='summarize_tickets')
            info("🦖 See, Nobody Cares. No issues found for the given parameters.", extra=context, feature='summarize_tickets')
            contextual_log('info', "🦖 See, Nobody Cares. No issues found for the given parameters.", extra=context, feature='summarize_tickets')
            # Write an empty report with a message
            params_list = [("user", display_name if display_name else account_id), ("start", start_date), ("end", end_date)]
            filename = make_output_filename("summarize_tickets", params_list, output_dir)
            contextual_log('info', f"[summarize_tickets] Attempting to write empty report to {filename}", extra=context, feature='summarize_tickets')
            try:
                empty_report = render_markdown_report(
                    feature="summarize_tickets",
                    user=user_email,
                    batch=batch_index,
                    suffix=unique_suffix,
                    feature_title="Ticket Summarization",
                    summary_section=f"**No issues found for the given parameters.**\n\nJQL: {jql}\nUser: {username}\nDate Range: {start_date} to {end_date}"
                )
                write_report(filename, empty_report, context, filetype='md', feature='summarize_tickets', item_name='Ticket summary report (empty)')
                info(f"🗂️ Ticket summary written to {filename}", extra=context, feature='summarize_tickets')
            except Exception as e:
                contextual_log('error', f"[summarize_tickets] Exception while writing empty report: {e}", exc_info=True, extra=context, feature='summarize_tickets')
                error(f"[summarize_tickets] Exception while writing empty report: {e}", extra=context, feature='summarize_tickets')
            return
        else:
            info(f"[summarize_tickets][DIAG][ELSE] Entered 'issues found' branch. Proceeding to write full report. len(issues): {len(issues)}")
            try:
                total_issues = len(issues)
                # Prompt user for grouping field
                import questionary
                grouping_fields = [
                    ("Issue Type", ["fields", "issuetype", "name"]),
                    ("Status", ["fields", "status", "name"]),
                    ("Priority", ["fields", "priority", "name"]),
                    ("Project Category", ["fields", "project", "projectCategory", "name"]),
                ]
                grouping_choice = questionary.select(
                    "How would you like to group the tickets in the summary report?",
                    choices=[f[0] for f in grouping_fields],
                    default="Issue Type"
                ).ask()
                grouping_label, grouping_path = next(f for f in grouping_fields if f[0] == grouping_choice)
                info(f"[summarize_tickets] Grouping by: {grouping_label} (path: {grouping_path})")
                # Group by selected field (now using helper)
                grouped = group_issues_by_field(issues, grouping_path, f"Other {grouping_label}")
                # Build sections using helpers
                header = f"# 🗂️ Ticket Summary Report\n\n"
                header += f"**Feature:** Summarize Tickets  "
                header += f"**User:** {display_name} ({account_id})  "
                header += f"**Timeframe:** {start_date} to {end_date}  "
                header += f"**Total issues completed:** {total_issues}  "
                header += f"**Grouped by:** {grouping_label}  "
                header += "\n\n---\n\n"
                toc = "## Table of Contents\n" + "\n".join(f"- [{group_val}](#{str(group_val).lower().replace(' ', '-').replace('/', '-')}-issues)" for group_val in grouped) + "\n"
                summary_table = f"| {grouping_label} | Count |\n|---|---|\n" + "\n".join(f"| {group_val} | {len(group)} |" for group_val, group in grouped.items()) + "\n---\n\n"
                # Action items
                not_resolved = [i for group in grouped.values() for i in group if safe_get(i, ['fields', 'status', 'name'], '').lower() not in ['done', 'closed', 'resolved']]
                action_items = "## Action Items\n"
                if not_resolved:
                    action_items += "### Not Resolved\n"
                    for issue in not_resolved:
                        key = issue.get('key', '')
                        summary = safe_get(issue, ['fields', 'summary'], '')[:40]
                        status = safe_get(issue, ['fields', 'status', 'name'], '')
                        action_items += f"- ⏳ [{key}] {summary} (Status: {status})\n"
                else:
                    action_items += "All summarized tickets are resolved.\n"
                # Top N lists
                assignees = [safe_get(i, ['fields', 'assignee', 'displayName'], '') for group in grouped.values() for i in group]
                from collections import Counter
                top_assignees = Counter(assignees).most_common(5)
                top_n_lists = make_top_n_list(top_assignees, "Top 5 Assignees")
                # Related links
                related_links = "## Related Links\n- [Jira Dashboard](https://your-domain.atlassian.net)\n"
                # Grouped issue sections
                grouped_sections = ""
                for itype, group in grouped.items():
                    anchor = str(itype).lower().replace(' ', '-')
                    grouped_sections += f"\n## {itype} Issues\n<a name=\"{anchor}-issues\"></a>\n\n"
                    grouped_sections += "| Key | Summary | Status | Resolved |\n|---|---|---|---|\n"
                    for issue in group:
                        key = issue.get('key', 'N/A')
                        summary = safe_get(issue, ['fields', 'summary'], '')[:40]
                        status = safe_get(issue, ['fields', 'status', 'name'], '')
                        emoji = status_emoji(status)
                        resolved = safe_get(issue, ['fields', 'resolutiondate'], '')
                        grouped_sections += f"| {key} | {summary} | {emoji} {status} | {resolved} |\n"
                    grouped_sections += "\n"
                export_metadata = f"---\n**Report generated by:** {user_email}  \n**Run at:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n"
                glossary = "## Glossary\n- ✅ Done/Closed/Resolved\n- 🟡 In Progress/In Review/Doing\n- 🔴 Blocked/On Hold/Overdue\n- ⬜️ Other statuses\n"
                next_steps = "## Next Steps\n- Review ticket summaries for trends or bottlenecks.\n"
                # Compose final report using build_report_sections
                sections = {
                    'header': header,
                    'toc': toc,
                    'summary': summary_table,
                    'action_items': action_items,
                    'top_n': top_n_lists,
                    'related_links': related_links,
                    'grouped_sections': grouped_sections,
                    'metadata': export_metadata,
                    'glossary': glossary,
                    'next_steps': next_steps,
                }
                content = build_report_sections(sections)
                params_list = [("user", display_name if display_name else account_id), ("start", start_date), ("end", end_date)]
                filename = make_output_filename("summarize_tickets", params_list, output_dir)
                write_report(filename, content, context, filetype='md', feature='summarize_tickets', item_name='Ticket summary report')
                info(f"🗂️ Ticket summary written to {filename}", extra=context, feature='summarize_tickets')
            except Exception as e:
                import traceback
                contextual_log('error', f"[summarize_tickets][FULL REPORT] Exception occurred: {e}", exc_info=True, operation="write_report", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='summarize_tickets')
                error(f"[summarize_tickets][FULL REPORT] Exception: {e}\n{traceback.format_exc()}", extra=context, feature='summarize_tickets')
                raise
        duration = int((time.time() - context.get('start_time', 0)) * 1000) if context.get('start_time') else None
        contextual_log('info', f"📝 [Summarize Tickets] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}).", operation="feature_end", status="success", params=redact_sensitive(params), extra=context, feature='summarize_tickets')
    except KeyboardInterrupt:
        contextual_log('warning', "📝 [Summarize Tickets] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context, feature='summarize_tickets')
        info("Graceful exit from Summarize Tickets feature.", extra=context)
    except Exception as e:
        if 'list index out of range' in str(e):
            info("🦖 See, Nobody Cares. No issues found for the given parameters.", extra=context)
            contextual_log('info', "🦖 See, Nobody Cares. No issues found for the given parameters.", extra=context, feature='summarize_tickets')
            return
        contextual_log('error', f"📝 [Summarize Tickets] Exception occurred: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='summarize_tickets')
        error(f"📝 [Summarize Tickets] Exception: {e}. Returning to previous menu.", extra=context)
        import questionary
        questionary.print("\n🦖 An error occurred while generating the ticket summary report. Returning to the previous menu.", style="bold fg:red")
        questionary.select("Select an option:", choices=["Return to previous menu"]).ask()
        return 

summarize_tickets = log_entry_exit(summarize_tickets) 