import os
import questionary
from jirassicpack.utils.io import ensure_output_dir, spinner, error, info, get_option, validate_required, validate_date, safe_get, write_markdown_file, require_param, render_markdown_report, make_output_filename, render_markdown_report_template
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.features.time_tracking_worklogs import select_jira_user
from datetime import datetime
import time
from marshmallow import Schema, fields, ValidationError
from jirassicpack.utils.rich_prompt import rich_error

class SummarizeTicketsOptionsSchema(Schema):
    user = fields.Str(required=True)
    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)

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
        'start_date': start_date,
        'end_date': end_date,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix,
        'acceptance_criteria_field': ac_field
    }

def summarize_tickets(jira, params, user_email=None, batch_index=None, unique_suffix=None):
    """
    Summarize tickets for a user or team and write to a Markdown file.
    Enhanced: Orders tickets by issue key, groups by issue type, adds subsections, and details who the report was run on.
    Now uses standardized Markdown report template.
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
        # Try to get display name/accountId for header
        display_name = username
        account_id = username
        try:
            user_obj = jira.get_user(account_id=username)
            display_name = user_obj.get('displayName', username)
            account_id = user_obj.get('accountId', username)
        except Exception:
            pass
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
        # Order by issue key
        issues = sorted(issues, key=lambda i: i.get('key', ''))
        # Group by issue type
        from collections import defaultdict, Counter
        grouped = defaultdict(list)
        for issue in issues:
            itype = safe_get(issue, ['fields', 'issuetype', 'name'], 'Other')
            grouped[itype].append(issue)
        # Header
        header = f"# 🗂️ Ticket Summary Report\n\n"
        header += f"**Feature:** Summarize Tickets  "
        header += f"**User:** {display_name} ({account_id})  "
        header += f"**Timeframe:** {start_date} to {end_date}  "
        header += f"**Total issues completed:** {total_issues}  "
        header += "\n\n---\n\n"
        # Table of contents
        toc = "## Table of Contents\n"
        for itype in grouped:
            anchor = itype.lower().replace(' ', '-')
            toc += f"- [{itype} Issues](#{anchor}-issues)\n"
        toc += "\n"
        # Summary table
        summary_table = "| Issue Type | Count |\n|---|---|\n"
        for itype, group in grouped.items():
            summary_table += f"| {itype} | {len(group)} |\n"
        summary_table += "\n---\n\n"
        # Action items: none for completed tickets, but highlight if any are not resolved
        action_items = "## Action Items\n"
        not_resolved = [i for group in grouped.values() for i in group if safe_get(i, ['fields', 'status', 'name'], '').lower() not in ['done', 'closed', 'resolved']]
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
        top_assignees = Counter(assignees).most_common(5)
        top_n_lists = "## Top 5 Assignees\n"
        for name, count in top_assignees:
            if name:
                top_n_lists += f"- {name}: {count} tickets\n"
        # Related links
        related_links = "## Related Links\n"
        related_links += "- [Jira Dashboard](https://your-domain.atlassian.net)\n"
        # Grouped issue sections
        grouped_sections = ""
        def status_emoji(status):
            s = status.lower()
            if s in ['done', 'closed', 'resolved']:
                return '✅'
            elif s in ['in progress', 'in review', 'doing']:
                return '🟡'
            elif s in ['blocked', 'on hold']:
                return '🔴'
            return '⬜️'
        for itype, group in grouped.items():
            anchor = itype.lower().replace(' ', '-')
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
        # Export metadata
        export_metadata = f"---\n**Report generated by:** {user_email}  \n**Run at:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n"
        # Glossary
        glossary = "## Glossary\n- ✅ Done/Closed/Resolved\n- 🟡 In Progress/In Review/Doing\n- 🔴 Blocked/On Hold/Overdue\n- ⬜️ Other statuses\n"
        # Next steps
        next_steps = "## Next Steps\n- Review ticket summaries for trends or bottlenecks.\n"
        # Compose final report
        params_list = [("user", display_name), ("start", start_date), ("end", end_date)]
        filename = make_output_filename("summarize_tickets", params_list, output_dir)
        report = render_markdown_report_template(
            report_header=header,
            table_of_contents=toc,
            report_summary=summary_table,
            action_items=action_items,
            top_n_lists=top_n_lists,
            related_links=related_links,
            grouped_issue_sections=grouped_sections,
            export_metadata=export_metadata,
            glossary=glossary,
            next_steps=next_steps
        )
        with open(filename, 'w') as f:
            f.write(report)
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