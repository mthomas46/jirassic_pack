# advanced_metrics.py
# This feature calculates advanced metrics for Jira issues, such as cycle time and lead time, for a given user and timeframe.
# It prompts for user, start/end dates, fetches completed issues, and outputs a Markdown report with a metrics table.

from datetime import datetime
from jirassicpack.utils.io import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, spinner, info, write_markdown_file, make_output_filename, render_markdown_report_template, status_emoji
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.utils.jira import select_jira_user
from jirassicpack.utils.io import get_option, validate_required, validate_date, error, safe_get, require_param, render_markdown_report
from typing import Any, Dict, List, Tuple
from statistics import mean, median
from collections import defaultdict, Counter
import logging
import time
import questionary
from marshmallow import Schema, fields, ValidationError, pre_load
from jirassicpack.utils.rich_prompt import rich_error
from jirassicpack.utils.fields import BaseOptionsSchema, validate_nonempty
from jirassicpack.config import ConfigLoader
from mdutils.mdutils import MdUtils

logger = logging.getLogger(__name__)

class AdvancedMetricsOptionsSchema(BaseOptionsSchema):
    user = fields.Str(required=True, error_messages={"required": "Jira user is required."}, validate=validate_nonempty)
    start_date = fields.Str(required=True, error_messages={"required": "Start date is required."}, validate=validate_date)
    end_date = fields.Str(required=True, error_messages={"required": "End date is required."}, validate=validate_date)
    output_dir = fields.Str(load_default='output')
    unique_suffix = fields.Str(load_default='')

    @pre_load
    def normalize(self, data, **kwargs):
        for k, v in data.items():
            if isinstance(v, str):
                data[k] = v.strip()
        return data

def prompt_advanced_metrics_options(options: Dict[str, Any], jira: Any = None) -> Dict[str, Any]:
    """
    Prompt for advanced metrics options using Marshmallow schema for validation and normalization.
    Prompts for user, start/end dates, and output directory.
    Returns a validated dictionary of all options needed for advanced metrics.
    Args:
        options (Dict[str, Any]): Options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.
    Returns:
        Dict[str, Any]: Validated options for the feature.
    """
    schema = AdvancedMetricsOptionsSchema()
    data = dict(options)
    while True:
        try:
            validated = schema.load(data)
            # Validate date fields using validate_date utility
            try:
                validate_date(validated['start_date'])
            except Exception:
                data['start_date'] = get_option(data, 'start_date', prompt="🦖 Start date (YYYY-MM-DD):", required=True, validate=validate_date)
                continue
            try:
                validate_date(validated['end_date'])
            except Exception:
                data['end_date'] = get_option(data, 'end_date', prompt="🦖 End date (YYYY-MM-DD):", required=True, validate=validate_date)
                continue
            return validated
        except ValidationError as err:
            for field, msgs in err.messages.items():
                suggestion = None
                if isinstance(msgs, list) and msgs and isinstance(msgs[0], tuple):
                    message, suggestion = msgs[0]
                elif isinstance(msgs, list) and msgs:
                    message = msgs[0]
                else:
                    message = str(msgs)
                if field == 'user' and jira:
                    info("Please select a Jira user for advanced metrics.")
                    user = select_jira_user(jira)
                    if not user:
                        info("Aborted user selection for advanced metrics.")
                        return None
                    data['user'] = user
                else:
                    data[field] = get_option(data, field, prompt=f"🦖 {field.replace('_', ' ').title()}: ", required=True)
                rich_error(f"Input validation error for '{field}': {message}", suggestion)
            continue

def advanced_metrics(
    jira: Any,
    params: Dict[str, Any],
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Generate an advanced metrics report for Jira issues, including bottleneck analysis, overdue issues, and top assignees.
    Outputs a Markdown report with detailed sections and visual enhancements.

    Args:
        jira (Any): Authenticated Jira client instance.
        params (Dict[str, Any]): Parameters for the report (dates, filters, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
    Returns:
        None. Writes a Markdown report to disk.
    """
    context = build_context("advanced_metrics", user_email, batch_index, unique_suffix)
    start_time = time.time()
    try:
        # Enhanced feature entry log
        contextual_log('info', f"📊 [Advanced Metrics] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='advanced_metrics')
        if not require_param(params, 'user', context):
            return
        if not require_param(params, 'start_date', context):
            return
        if not require_param(params, 'end_date', context):
            return
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        user = params['user']
        start_date = params['start_date']
        end_date = params['end_date']
        ensure_output_dir(output_dir)
        # Fetch more fields for richer analytics
        jql = (
            f"assignee = '{user}' "
            f"AND statusCategory = Done "
            f"AND resolved >= '{start_date}' "
            f"AND resolved <= '{end_date}'"
        )
        fields = ["summary", "created", "resolutiondate", "status", "key", "issuetype", "priority", "duedate", "assignee", "changelog"]
        try:
            with spinner("📊 Running Advanced Metrics..."):
                issues = jira.search_issues(jql, fields=fields, max_results=200, context=context)
        except Exception as e:
            contextual_log('error', f"📊 [Advanced Metrics] Failed to fetch issues: {e}", exc_info=True, operation="api_call", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='advanced_metrics')
            error(f"Failed to fetch issues: {e}. Please check your Jira connection, credentials, and network.", extra=context, feature='advanced_metrics')
            return
        if not issues:
            info("🦖 See, Nobody Cares. No issues found for the given parameters.", extra=context, feature='advanced_metrics')
            contextual_log('info', "🦖 See, Nobody Cares. No issues found for the given parameters.", extra=context, feature='advanced_metrics')
            return
        # Try to get display name/accountId for header
        display_name = user
        account_id = user
        try:
            user_obj = jira.get_user(account_id=user)
            display_name = user_obj.get('displayName', user)
            account_id = user_obj.get('accountId', user)
        except Exception:
            pass
        from jirassicpack.config import ConfigLoader
        jira_conf = ConfigLoader().get_jira_config()
        base_url = jira_conf['url'].rstrip('/')
        run_at = datetime.now().strftime('%Y-%m-%d %H:%M')
        # Order by issue key
        issues = sorted(issues, key=lambda i: i.get('key', ''))
        # Group by issue type
        grouped = defaultdict(list)
        for issue in issues:
            itype = safe_get(issue, ['fields', 'issuetype', 'name'], 'Other')
            grouped[itype].append(issue)
        # Try to get project category from first issue
        project_category = safe_get(issues[0], ['fields', 'project', 'projectCategory', 'name'], 'N/A') if issues else 'N/A'
        # Report header
        header = f"# 📊 Advanced Metrics Report\n\n"
        header += f"**Feature:** Advanced Metrics  "
        header += f"**User:** {display_name} ({account_id})  "
        header += f"**Time range:** {start_date} to {end_date}  "
        header += f"**Project Category:** {project_category}  "
        header += f"**Run at:** {run_at}  "
        header += "\n\n---\n\n"
        # Report summary table
        summary_table = "| Metric | Value |\n|---|---|\n"
        summary_table += f"| Total Issues | {len(issues)} |\n"
        for itype, group in grouped.items():
            summary_table += f"| {itype} | {len(group)} |\n"
        summary_table += "\n---\n\n"
        # Build table of contents
        toc = "## Table of Contents\n"
        for itype in grouped:
            anchor = itype.lower().replace(' ', '-')
            toc += f"- [{itype} Issues](#{anchor}-issues)\n"
        toc += "\n"
        # Action items: unresolved, overdue, blocked
        action_items = "## Action Items\n"
        overdue = [i for group in grouped.values() for i in group if safe_get(i, ['fields', 'status', 'name'], '').lower() not in ['done', 'closed'] and safe_get(i, ['fields', 'duedate']) and safe_get(i, ['fields', 'duedate']) < datetime.now().strftime('%Y-%m-%d')]
        if overdue:
            action_items += "### Overdue Issues\n"
            for issue in overdue:
                key = issue.get('key', '')
                summary = safe_get(issue, ['fields', 'summary'], '')[:40]
                due = safe_get(issue, ['fields', 'duedate'], '')
                action_items += f"- 🔴 [{key}] {summary} (Due: {due})\n"
        else:
            action_items += "No overdue issues!\n"
        # Visual enhancements: status emoji
        # Top N lists
        assignees = [safe_get(i, ['fields', 'assignee', 'displayName'], '') for group in grouped.values() for i in group]
        top_assignees = Counter(assignees).most_common(5)
        top_n_lists = "## Top 5 Assignees\n"
        for name, count in top_assignees:
            if name:
                top_n_lists += f"- {name}: {count} issues\n"
        # Related links
        related_links = "## Related Links\n"
        related_links += f"- [Project Dashboard]({base_url}/projects)\n"
        # Export metadata
        export_metadata = f"---\n**Report generated by:** {user_email}  \n**Run at:** {run_at}  \n**Filters:** User: {display_name}, Time: {start_date} to {end_date}\n"
        # Glossary
        glossary = "## Glossary\n- ✅ Done/Closed/Resolved\n- 🟡 In Progress/In Review/Doing\n- 🔴 Blocked/On Hold/Overdue\n- ⬜️ Other statuses\n"
        # Next steps
        next_steps = "## Next Steps\n"
        if overdue:
            next_steps += "- Review and resolve overdue issues.\n"
        if not top_assignees or (top_assignees and top_assignees[0][1] < 3):
            next_steps += "- Consider rebalancing workload among assignees.\n"
        # Grouped issue sections
        grouped_sections = ""
        for itype, group in grouped.items():
            anchor = itype.lower().replace(' ', '-')
            grouped_sections += f"\n## {itype} Issues\n<a name=\"{anchor}-issues\"></a>\n\n"
            grouped_sections += "| Key | Summary | Status | Assignee | Components | Project Category | Created | Updated | Age (days) | Link |\n"
            grouped_sections += "|---|---|---|---|---|---|---|---|---|---|\n"
            for issue in group:
                key = issue.get('key', '')
                summary = safe_get(issue, ['fields', 'summary'], '')[:40]
                status = safe_get(issue, ['fields', 'status', 'name'], '')
                emoji = status_emoji(status)
                assignee = safe_get(issue, ['fields', 'assignee', 'displayName'], '')
                components = ', '.join([c['name'] for c in issue.get('fields', {}).get('components', [])])
                proj_cat = safe_get(issue, ['fields', 'project', 'projectCategory', 'name'], project_category)
                created = safe_get(issue, ['fields', 'created'], '')
                updated = safe_get(issue, ['fields', 'updated'], '')
                age = ''
                try:
                    if created:
                        age = (datetime.now() - datetime.strptime(created[:10], '%Y-%m-%d')).days
                except Exception:
                    age = ''
                link = f"[{key}]({base_url}/browse/{key})"
                grouped_sections += f"| {key} | {summary} | {emoji} {status} | {assignee} | {components} | {proj_cat} | {created} | {updated} | {age} | {link} |\n"
            grouped_sections += "\n"
        # Compose final report
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
        # Write to file
        filename = make_output_filename(output_dir, f"advanced_metrics_{user_email}_{start_date}_{end_date}_{unique_suffix}")
        md_file = MdUtils(file_name=filename, title="Advanced Metrics Report")
        md_file.new_line(f"_Generated: {datetime.now()}_")
        md_file.new_header(level=2, title="Summary")
        md_file.new_line(report)
        md_file.create_md_file()
        info(f"🦖 Advanced metrics report written to {filename}")
        # Enhanced feature end log
        duration = int((time.time() - start_time) * 1000)
        contextual_log('info', f"📊 [advanced_metrics] Feature complete | Suffix: {unique_suffix}", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='advanced_metrics')
    except KeyboardInterrupt:
        contextual_log('warning', "[advanced_metrics] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context, feature='advanced_metrics')
        info("Graceful exit from Advanced Metrics feature.", extra=context, feature='advanced_metrics')
    except Exception as e:
        if 'list index out of range' in str(e):
            info("🦖 See, Nobody Cares. No issues found for the given parameters.", extra=context, feature='advanced_metrics')
            contextual_log('info', "🦖 See, Nobody Cares. No issues found for the given parameters.", extra=context, feature='advanced_metrics')
            return
        contextual_log('error', f"[advanced_metrics] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='advanced_metrics')
        error(f"[advanced_metrics] Exception: {e}", extra=context, feature='advanced_metrics')
        raise 