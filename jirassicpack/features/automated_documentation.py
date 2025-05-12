# automated_documentation.py
# This feature generates automated documentation from Jira issues, such as release notes, changelogs, or sprint reviews.
# It prompts the user for the documentation type, project, and relevant filters (version or sprint), then fetches issues and writes a Markdown report.

from typing import Any, Dict, List
from jirassicpack.utils.io import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, spinner, error, info, info_spared_no_expense, prompt_with_validation, safe_get, write_markdown_file, require_param, render_markdown_report, get_option
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.utils.jira import get_valid_project_key

def prompt_automated_doc_options(opts: Dict[str, Any], jira=None) -> Dict[str, Any]:
    """
    Prompt for automated documentation options using Jira-aware helpers for project selection.
    """
    doc_type = get_option(
        opts,
        'doc_type',
        prompt="Select documentation type:",
        choices=["Release notes", "Changelog", "Sprint Review"],
        required=True
    )
    proj = opts.get('project')
    if not proj and jira:
        proj = get_valid_project_key(jira)
    elif not proj:
        proj = get_option(opts, 'project', prompt="Jira Project Key:", required=True)
    version = get_option(opts, 'version', prompt="Version (for Release notes):", default='')
    sprint = get_option(opts, 'sprint', prompt="Sprint name (for Sprint Review):", default='')
    out_dir = get_option(opts, 'output_dir', default='output')
    suffix = opts.get('unique_suffix', '')
    return {
        'doc_type': doc_type,
        'project': proj,
        'version': version,
        'sprint': sprint,
        'output_dir': out_dir,
        'unique_suffix': suffix
    }

def write_automated_doc_file(filename: str, doc_type: str, issues: list, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
    try:
        summary_section = f"**Documentation Type:** {doc_type}\n\n**Total Issues:** {len(issues)}"
        details_section = ""
        for issue in issues:
            if isinstance(issue, dict):
                key = issue.get('key', 'N/A')
                summary = safe_get(issue, ['fields', 'summary'], 'N/A')
                details_section += f"- {key}: {summary}\n"
            else:
                details_section += f"- {issue}\n"
        content = render_markdown_report(
            feature="automated_documentation",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="Automated Documentation",
            summary_section=summary_section,
            main_content_section=details_section
        )
        with open(filename, 'w') as f:
            f.write(content)
        contextual_log('info', f"📄 Automated documentation written to {filename}", operation="output_write", output_file=filename, status="success", extra=context, feature='automated_documentation')
    except Exception as e:
        error(f"Failed to write automated documentation file: {e}", extra=context, feature='automated_documentation')

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
        filename = f"{output_dir}/automated_doc{unique_suffix}.md"
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