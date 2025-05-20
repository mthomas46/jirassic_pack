"""
integration_tools.py

Feature module for scanning Jira issues for integration links (e.g., GitHub/GitLab PRs) via the CLI.
Prompts for JQL, extracts PR links from issue descriptions and comments, and outputs a Markdown report for traceability.
"""

from typing import Any, Dict, List, Tuple
from jirassicpack.utils.output_utils import ensure_output_dir, celebrate_success
from jirassicpack.utils.message_utils import retry_or_skip, info, error
from jirassicpack.utils.validation_utils import safe_get, require_param, prompt_with_schema
from jirassicpack.utils.decorators import feature_error_handler
from jirassicpack.utils.progress_utils import spinner
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
import re
import time
from jirassicpack.utils.fields import BaseOptionsSchema, validate_nonempty
from marshmallow import fields
from jirassicpack.constants import SEE_NOBODY_CARES, FAILED_TO
from jirassicpack.analytics.helpers import build_report_sections

class IntegrationOptionsSchema(BaseOptionsSchema):
    """
    Marshmallow schema for validating integration options.
    Fields: integration_jql.
    """
    integration_jql = fields.Str(required=True, error_messages={"required": "JQL is required for integration scan."}, validate=validate_nonempty)
    # output_dir and unique_suffix are inherited

def prompt_integration_options(opts: dict, jira: Any = None) -> dict:
    """
    Prompt for integration options using Marshmallow schema for validation.

    Args:
        opts (dict): Initial options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.

    Returns:
        dict: Validated options for the feature, or None if aborted.
    """
    schema = IntegrationOptionsSchema()
    result = prompt_with_schema(schema, dict(opts), jira=jira, abort_option=True)
    if result == "__ABORT__":
        info("❌ Aborted integration options prompt.")
        return None
    return result

def write_integration_links_file(filename: str, pr_links: list, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
    """
    Write a Markdown file for integration links using write_report for robust file writing and logging.
    Args:
        filename (str): Output file path.
        pr_links (list): List of (issue, PR link) tuples.
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
        context (dict, optional): Additional context for logging.
    Returns:
        None. Writes a Markdown report to disk.
    """
    try:
        summary_section = f"**Total PR Links Found:** {len(pr_links)}"
        if not pr_links:
            details_section = "No PR links found."
        else:
            details_section = "| Issue Key | PR Link |\n|-----------|--------|\n"
            for pr, link in pr_links:
                details_section += f"| {pr} | {link} |\n"
        content = build_report_sections({
            'header': f"# 🔗 Integration Links Report\n\n**Total PR Links Found:** {len(pr_links)}",
            'summary': summary_section,
            'grouped_sections': details_section,
        })
        write_report(filename, content, context, filetype='md', feature='integration_tools', item_name='Integration links report')
        info(f"🔗 Integration links written to {filename}", extra=context, feature='integration_tools')
        contextual_log('info', f"Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=context, feature='integration_tools')
    except Exception as e:
        error(FAILED_TO.format(action='write integration links file', error=e), extra=context, feature='integration_tools')

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
        for comment in comments:
            for match in re.findall(r'https://github.com/[^\s)]+', safe_get(comment, ['body'], '')):
                pr_links.append((key, match))
    return pr_links

@feature_error_handler('integration_tools')
def integration_tools(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Main feature entrypoint for integration tools. Handles validation, integration actions, and report writing.

    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the integration (tool, action, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.

    Returns:
        None. Writes a Markdown report to disk.
    """
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
            error(FAILED_TO.format(action='fetch issues', error=e), extra=context, feature='integration_tools')
            contextual_log('error', f"[integration_tools] Failed to fetch issues: {e}", exc_info=True, extra=context, feature='integration_tools')
            return
        if not issues:
            info(SEE_NOBODY_CARES, extra=context, feature='integration_tools')
            return
        links = generate_integration_links(issues)
        if not links:
            info(SEE_NOBODY_CARES, extra=context, feature='integration_tools')
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