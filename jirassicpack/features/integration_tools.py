from typing import Any, Dict, List, Tuple
from jirassicpack.cli import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, logger, redact_sensitive
from jirassicpack.utils import get_option, validate_required, error, info, spinner, info_spared_no_expense, prompt_with_validation, safe_get, build_context, write_markdown_file, require_param, render_markdown_report, contextual_log
import re
import time

def prompt_integration_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """Prompt for integration options using get_option utility."""
    jql = get_option(options, 'integration_jql', prompt="🔗 JQL to find issues for integration scan:", required=True)
    output_dir = get_option(options, 'output_dir', default='output')
    unique_suffix = options.get('unique_suffix', '')
    return {
        'integration_jql': jql,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix
    }

def write_integration_links_file(filename: str, pr_links: list, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
    try:
        summary_section = f"**Total PR Links Found:** {len(pr_links)}"
        details_section = ""
        if not pr_links:
            details_section = "No PR links found."
        else:
            details_section = "| Issue Key | PR Link |\n|-----------|--------|\n"
            for pr, link in pr_links:
                details_section += f"| {pr} | {link} |\n"
        content = render_markdown_report(
            feature="integration_tools",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="Integration Tools",
            summary_section=summary_section,
            main_content_section=details_section
        )
        with open(filename, 'w') as f:
            f.write(content)
        info(f"🔗 Integration links written to {filename}", extra=context)
        contextual_log('info', f"Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=context, feature='integration_tools')
    except Exception as e:
        error(f"Failed to write integration links file: {e}", extra=context, feature='integration_tools')

def generate_integration_links(issues: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """
    Extract GitHub/GitLab PR links from issue descriptions and comments.
    Returns a list of (issue_key, link) tuples.
    """
    pr_links = []
    for issue in issues:
        key = issue.get('key', 'N/A')
        desc = safe_get(issue, ['fields', 'description'], '')
        comments = safe_get(issue, ['fields', 'comment', 'comments'], [])
        for match in re.findall(r'https://github.com/[^\s)]+', desc):
            pr_links.append((key, match))
        for c in comments:
            for match in re.findall(r'https://github.com/[^\s)]+', safe_get(c, ['body'], '')):
                pr_links.append((key, match))
    return pr_links

def integration_tools(jira: Any, params: Dict[str, Any], user_email=None, batch_index=None, unique_suffix=None) -> None:
    correlation_id = params.get('correlation_id')
    context = build_context("integration_tools", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    try:
        contextual_log('info', f"🔗 [Integration Tools] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='integration_tools')
        if not require_param(params, 'integration_jql', context):
            return
        jql = params.get('integration_jql')
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        ensure_output_dir(output_dir)
        def do_search():
            with spinner("🔗 Running Integration Tools..."):
                return jira.search_issues(jql, fields=["key", "description", "comment"], max_results=100)
        try:
            issues = retry_or_skip("Fetching issues for integration tools", do_search)
        except Exception as e:
            error(f"Failed to fetch issues: {e}. Please check your Jira connection, credentials, and network.", extra=context, feature='integration_tools')
            contextual_log('error', f"[integration_tools] Failed to fetch issues: {e}", exc_info=True, extra=context, feature='integration_tools')
            return
        if not issues:
            info("🦖 See, Nobody Cares. No issues found for integration links.", extra=context, feature='integration_tools')
            return
        links = generate_integration_links(issues)
        if not links:
            info("🦖 See, Nobody Cares. No integration links found.", extra=context, feature='integration_tools')
            return
        filename = f"{output_dir}/integration_links{unique_suffix}.md"
        write_integration_links_file(filename, links, user_email, batch_index, unique_suffix, context)
        celebrate_success()
        info_spared_no_expense()
        duration = int((time.time() - start_time) * 1000)
        contextual_log('info', f"🔗 [Integration Tools] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}).", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='integration_tools')
    except KeyboardInterrupt:
        contextual_log('warning', "[integration_tools] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context, feature='integration_tools')
        info("Graceful exit from Integration Tools feature.", extra=context, feature='integration_tools')
    except Exception as e:
        contextual_log('error', f"�� [Integration Tools] Exception occurred: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='integration_tools')
        error(f"[integration_tools] Exception: {e}", extra=context, feature='integration_tools')
        raise 