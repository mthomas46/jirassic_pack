# automated_documentation.py
# This feature generates automated documentation from Jira issues, such as release notes, changelogs, or sprint reviews.
# It prompts the user for the documentation type, project, and relevant filters (version or sprint), then fetches issues and writes a Markdown report.

from typing import Any, Dict, List
from jirassicpack.utils.io import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, spinner, error, info, info_spared_no_expense, prompt_with_validation, safe_get, write_markdown_file, require_param, render_markdown_report, get_option, make_output_filename, render_markdown_report_template
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.utils.jira import get_valid_project_key
from marshmallow import Schema, fields, ValidationError, pre_load, validate
from jirassicpack.utils.rich_prompt import rich_error
from jirassicpack.utils.fields import ProjectKeyField, BaseOptionsSchema, validate_nonempty
from jirassicpack.config import ConfigLoader
from datetime import datetime
from collections import defaultdict, Counter

class AutomatedDocOptionsSchema(BaseOptionsSchema):
    doc_type = fields.Str(required=True, error_messages={"required": "Documentation type is required."}, validate=validate.OneOf(['Release notes', 'Changelog', 'Sprint Review']))
    project = ProjectKeyField(required=True, error_messages={"required": "Project key is required."}, validate=validate_nonempty)
    version = fields.Str(load_default='')
    sprint = fields.Str(load_default='')
    # output_dir and unique_suffix are inherited

def prompt_automated_doc_options(opts: Dict[str, Any], jira=None) -> Dict[str, Any]:
    """
    Prompt for automated documentation options using Marshmallow schema for validation and normalization.
    Prompts for doc_type, project, version, sprint, and output directory.
    Returns a validated dictionary of all options needed for automated documentation.
    """
    schema = AutomatedDocOptionsSchema()
    data = dict(opts)
    while True:
        try:
            validated = schema.load(data)
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
                if field == 'doc_type':
                    data['doc_type'] = get_option(data, 'doc_type', prompt="Select documentation type:", choices=["Release notes", "Changelog", "Sprint Review"], required=True)
                elif field == 'project' and jira:
                    data['project'] = get_valid_project_key(jira)
                else:
                    data[field] = get_option(data, field, prompt=f"🦖 {field.replace('_', ' ').title()}: ", required=True)
                rich_error(f"Input validation error for '{field}': {message}", suggestion)
            continue

def write_automated_doc_file(filename: str, doc_type: str, issues: list, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
    try:
        jira_conf = ConfigLoader().get_jira_config()
        base_url = jira_conf['url'].rstrip('/')
        run_at = datetime.now().strftime('%Y-%m-%d %H:%M')
        # Order by key
        issues = sorted(issues, key=lambda i: i.get('key', ''))
        # Group by issue type if available
        grouped = defaultdict(list)
        for issue in issues:
            itype = safe_get(issue, ['fields', 'issuetype', 'name'], 'Other')
            grouped[itype].append(issue)
        # Try to get project category from first issue
        project_category = safe_get(issues[0], ['fields', 'project', 'projectCategory', 'name'], 'N/A') if issues else 'N/A'
        # Report header
        header = f"# 📄 Automated Documentation Report\n\n"
        header += f"**Feature:** Automated Documentation  "
        header += f"**Project:** {safe_get(issues[0], ['fields', 'project', 'key'], 'N/A') if issues else 'N/A'}  "
        header += f"**Doc type:** {doc_type}  "
        header += f"**Version:** {safe_get(issues[0], ['fields', 'fixVersions', 0, 'name'], 'N/A') if issues else 'N/A'}  "
        header += f"**Sprint:** {safe_get(issues[0], ['fields', 'sprint', 'name'], 'N/A') if issues else 'N/A'}  "
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
        def status_emoji(status):
            s = status.lower()
            if s in ['done', 'closed', 'resolved']:
                return '✅'
            elif s in ['in progress', 'in review', 'doing']:
                return '🟡'
            elif s in ['blocked', 'on hold']:
                return '🔴'
            return '⬜️'
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
        export_metadata = f"---\n**Report generated by:** {user_email}  \n**Run at:** {run_at}  \n**Filters:** Project: {safe_get(issues[0], ['fields', 'project', 'key'], 'N/A') if issues else 'N/A'}, Doc type: {doc_type}\n"
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
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        info(f"🦖 Automated documentation written to {filename}", extra=context)
    except Exception as e:
        error(f"Failed to write automated documentation file: {e}", extra=context)

def generate_documentation(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate documentation content from issues. Returns a list of issues (could be filtered or processed as needed).
    """
    # For now, just return the issues as-is. Extend for custom doc logic.
    return issues

def automated_documentation(jira: Any, params: dict, user_email=None, batch_index=None, unique_suffix=None) -> None:
    import time
    correlation_id = params.get('correlation_id')
    context = build_context("automated_documentation", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    try:
        contextual_log('info', f"📚 [Automated Documentation] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='automated_documentation')
        if not require_param(params, 'doc_type', context):
            return
        if not require_param(params, 'project', context):
            return
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        doc_type = params.get('doc_type')
        project = params.get('project')
        version = params.get('version', '')
        sprint = params.get('sprint', '')
        ensure_output_dir(output_dir)
        if doc_type == 'Release notes' and version:
            jql = f'project = "{project}" AND fixVersion = "{version}" AND statusCategory = Done'
        elif doc_type == 'Sprint Review' and sprint:
            jql = f'project = "{project}" AND Sprint = "{sprint}" AND statusCategory = Done'
        else:
            jql = f'project = "{project}" AND statusCategory = Done'
        def do_search():
            with spinner("📄 Running Automated Documentation..."):
                return jira.search_issues(jql, fields=["key", "summary"], max_results=100)
        try:
            issues = retry_or_skip("Fetching issues for documentation", do_search)
        except Exception as e:
            error(f"Failed to fetch issues: {e}. Please check your Jira connection, credentials, and network.", extra=context, feature='automated_documentation')
            contextual_log('error', f"[automated_documentation] Failed to fetch issues: {e}", exc_info=True, extra=context)
            return
        if not issues:
            info("🦖 See, Nobody Cares. No issues found for documentation.", extra=context)
            return
        params_list = [("project", project), ("doc_type", doc_type), ("version", version), ("sprint", sprint)]
        filename = make_output_filename("automated_doc", params_list, output_dir)
        write_automated_doc_file(filename, doc_type, issues, user_email, batch_index, unique_suffix, context)
        celebrate_success()
        info_spared_no_expense()
        contextual_log('info', f"📄 Automated documentation written to {filename}", operation="output_write", output_file=filename, status="success", extra=context)
        contextual_log('info', f"📚 [Automated Documentation] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}).", operation="feature_end", status="success", params=redact_sensitive(params), extra=context)
    except KeyboardInterrupt:
        contextual_log('warning', "[automated_documentation] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context)
        info("Graceful exit from Automated Documentation feature.", extra=context)
    except Exception as e:
        contextual_log('error', f"📚 [Automated Documentation] Exception occurred: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context)
        error(f"[automated_documentation] Exception: {e}", extra=context)
        raise 