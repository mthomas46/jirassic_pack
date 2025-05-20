import os
from jirassicpack.utils.io import ensure_output_dir, info, spinner, get_option, prompt_text, prompt_select, feature_error_handler, write_report, safe_get, select_from_list
from jirassicpack.utils.logging import contextual_log
import openai
from datetime import datetime
import re
import requests
from marshmallow import fields, ValidationError
from jirassicpack.utils.rich_prompt import rich_error
from jirassicpack.config import ConfigLoader
from jirassicpack.utils.fields import BaseOptionsSchema
from typing import Any
from jirassicpack.analytics.helpers import build_report_sections

openai_api_key = ConfigLoader().get('openai_api_key')
openai.api_key = openai_api_key

llm_config = ConfigLoader().get_llm_config()

def call_local_llm_text(prompt: str) -> str:
    """
    Call the local LLM HTTP API to generate a text response for a given prompt.
    Args:
        prompt (str): The prompt to send to the LLM.
    Returns:
        str: The LLM's response text.
    """
    url = llm_config['text_url']
    response = requests.post(url, json={"prompt": prompt})
    response.raise_for_status()
    return response.json()["response"]

def call_local_llm_github_pr(repo_name: str, pr_number: int, github_token: str, prompt: str = None) -> str:
    """
    Calls the local LLM HTTP API to analyze a GitHub PR directly, letting the local LLM handle the GitHub API call.
    Optionally sends a custom prompt to the local LLM.
    Args:
        repo_name (str): GitHub repository name.
        pr_number (int): Pull request number.
        github_token (str): GitHub API token.
        prompt (str, optional): Custom prompt for the LLM.
    Returns:
        str: The LLM's response text.
    """
    url = llm_config['github_url']
    payload = {
        "repo": repo_name,
        "pr_number": pr_number,
        "token": github_token
    }
    if prompt is not None:
        payload["prompt"] = prompt
    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()["response"]

def call_local_llm_file(file_path: str) -> str:
    """
    Sends a file to the local LLM HTTP API for analysis via the /generate/file endpoint.
    The file is uploaded as multipart/form-data.
    Args:
        file_path (str): Path to the file to analyze.
    Returns:
        str: The LLM's response text.
    """
    url = "http://localhost:5000/generate/file"
    with open(file_path, "rb") as f:
        files = {"file": (file_path, f)}
        response = requests.post(url, files=files)
    response.raise_for_status()
    return response.json()["response"]

def select_jira_issues(jira: Any) -> list:
    """
    Interactive multi-issue selection: search, pick, or enter manually. Returns a list of issue keys.
    Args:
        jira (Any): Authenticated Jira client instance.
    Returns:
        list: List of selected issue keys.
    """
    # Fetch issues (search or pick from list)
    while True:
        method = prompt_select(
            "How would you like to select issues?",
            choices=[
                "Search for issues",
                "Pick from list",
                "Enter issue key manually",
                "Abort"
            ],
            default="Search for issues"
        )
        if method == "Abort":
            return []
        elif method == "Enter issue key manually":
            issue_key = prompt_text("Enter issue key:")
            return [issue_key] if issue_key else []
        elif method == "Search for issues":
            search_term = prompt_text("Enter search term (summary or key):")
            if not search_term:
                continue
            try:
                found = jira.search_issues(f"summary ~ '{search_term}' OR key = '{search_term}'", fields=["key", "summary"], max_results=20)
            except Exception as e:
                info(f"Error searching issues: {e}")
                continue
            if not found:
                info("No issues found. Try again or use another option.")
                continue
            choices = [(f"{issue.get('key','?')}: {issue.get('fields',{}).get('summary','?')}", issue.get('key','?')) for issue in found]
            picked = select_from_list(choices, message="Select issues:", display_fn=lambda t: t[0], value_fn=lambda t: t[1], multi=True)
            return picked or []
        elif method == "Pick from list":
            try:
                all_issues = jira.search_issues("ORDER BY updated DESC", fields=["key", "summary"], max_results=100)
            except Exception as e:
                info(f"Error fetching issues: {e}")
                continue
            if not all_issues:
                info("No issues found.")
                continue
            choices = [(f"{issue.get('key','?')}: {issue.get('fields',{}).get('summary','?')}", issue.get('key','?')) for issue in all_issues]
            picked = select_from_list(choices, message="Select issues:", display_fn=lambda t: t[0], value_fn=lambda t: t[1], multi=True)
            return picked or []

@feature_error_handler('ticket_discussion_summary')
def ticket_discussion_summary(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Generate a summary report of a Jira ticket's discussion, including comments and action items.
    Outputs a Markdown report with detailed sections and visual enhancements.

    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the summary (issue key, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
    Returns:
        None. Writes a Markdown report to disk.
    """
    issue_keys = params.get("issue_keys") or ([params["issue_key"]] if "issue_key" in params else [])
    output_dir = params.get("output_dir", "output")
    ensure_output_dir(output_dir)
    for issue_key in issue_keys:
        context = {"feature": "ticket_discussion_summary", "user": user_email, "batch": batch_index, "suffix": unique_suffix, "issue_key": issue_key}
        with spinner(f"Fetching issue {issue_key}..."):
            issue = jira.get_task(issue_key)
        if not issue or not issue.get('fields'):
            info(f"🦖 See, Nobody Cares. No data found for issue {issue_key}.", extra=context)
            contextual_log('info', f"🦖 See, Nobody Cares. No data found for issue {issue_key}.", extra=context)
            continue
        fields = issue.get("fields", {})
        description = fields.get("description", "")
        config = ConfigLoader()
        ac_field = params.get("acceptance_criteria_field") or config.get("acceptance_criteria_field", "customfield_10001")
        acceptance_criteria = fields.get(ac_field, "")
        comments = safe_get(fields, ["comment", "comments"], [])
        comments_text = "\n\n".join([
            f"{c.get('author', {}).get('displayName', 'Unknown')}: {c.get('body', '')}" for c in comments
        ])
        # Extract GitHub PR links from description and comments
        pr_links = re.findall(r'https://github.com/[^\s)]+/pull/\d+', description)
        for c in comments:
            pr_links += re.findall(r'https://github.com/[^\s)]+/pull/\d+', c.get('body', ''))
        pr_links = list(set(pr_links))  # Deduplicate
        # --- Linked Pull Requests Section ---
        if not pr_links:
            pr_section = '\n## Linked Pull Requests\n_No pull requests found in description or comments._\n'
        else:
            pr_section = '\n## Linked Pull Requests\n' + '\n'.join(f'- {url}' for url in pr_links) + '\n'
        # --- Technical Summary Section (LLM) ---
        tech_summary = ""
        if description:
            tech_prompt = f"Summarize the technical discussion and resolution for the following Jira issue description and comments:\n\nDescription:\n{description}\n\nComments:\n{comments_text}"
            try:
                with spinner(f"Summarizing technical/code changes for {issue_key} with LLM..."):
                    tech_summary = call_local_llm_text(tech_prompt)
            except Exception:
                tech_summary = "(Failed to summarize technical/code changes via local LLM)"
        # --- Compose report sections ---
        header = f"# 💬 Ticket Discussion Summary\n\n"
        header += f"**Feature:** Ticket Discussion Summary  "
        header += f"**Issue Key:** {issue_key}  "
        header += f"**Created by:** {user_email}  "
        header += f"**Run at:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  "
        header += "\n\n---\n\n"
        toc = "## Table of Contents\n- [Linked Pull Requests](#linked-pull-requests)\n- [Technical Summary](#technical-summary)\n\n"
        summary_table = "| Field | Value |\n|---|---|\n"
        summary_table += f"| Issue Key | {issue_key} |\n"
        summary_table += f"| Description | {description[:40]} |\n"
        summary_table += f"| Acceptance Criteria | {acceptance_criteria[:40]} |\n"
        summary_table += f"| Comments | {len(comments)} |\n"
        summary_table += "\n---\n\n"
        action_items = "## Action Items\n"
        if not comments:
            action_items += "- ⚠️ No comments on this issue.\n"
        else:
            action_items += "- Review discussion for unresolved questions.\n"
        top_n_lists = ""
        related_links = f"## Related Links\n- [View in Jira](https://your-domain.atlassian.net/browse/{issue_key})\n"
        grouped_section = pr_section + "\n## Technical Summary\n" + tech_summary + "\n"
        export_metadata = f"---\n**Report generated by:** {user_email}  \n**Run at:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n"
        glossary = "## Glossary\n- ⚠️ Needs attention\n"
        next_steps = "## Next Steps\n- Follow up on any open questions or action items in the discussion.\n"
        sections = {
            'header': header,
            'toc': toc,
            'summary': summary_table,
            'action_items': action_items,
            'top_n': top_n_lists,
            'related_links': related_links,
            'grouped_sections': grouped_section,
            'metadata': export_metadata,
            'glossary': glossary,
            'next_steps': next_steps,
        }
        report = build_report_sections(sections)
        filename = os.path.join(output_dir, f"ticket_discussion_summary_{issue_key}.md")
        write_report(filename, report, context, filetype='md', feature='ticket_discussion_summary', item_name='Ticket discussion summary report')
        info(f"💬 Ticket discussion summary written to {filename}", extra=context, feature='ticket_discussion_summary')

class TicketDiscussionSummaryOptionsSchema(BaseOptionsSchema):
    issue_keys = fields.List(fields.Str(), required=True)

def prompt_ticket_discussion_summary_options(opts: dict, jira: Any = None) -> dict:
    """
    Prompt for ticket discussion summary options, supporting multi-issue selection.
    Args:
        opts (dict): Options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.
    Returns:
        dict: Validated options for the feature.
    """
    schema = TicketDiscussionSummaryOptionsSchema()
    while True:
        if jira:
            issues = select_jira_issues(jira)
        else:
            issue_key = get_option(opts, 'issue_key', prompt="🦖 Jira Issue Key (e.g., DEMO-123):", required=True)
            issues = [issue_key]
        output_dir = get_option(opts, 'output_dir', default='output')
        unique_suffix = opts.get('unique_suffix', '')
        data = {
            'issue_keys': issues,
            'output_dir': output_dir,
            'unique_suffix': unique_suffix
        }
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
                rich_error(f"Input validation error for '{field}': {message}", suggestion)
            continue

def prompt_ticket_discussion_options(opts: dict, jira: Any = None) -> dict:
    """
    Prompt for ticket discussion summary options using Marshmallow schema for validation.

    Args:
        opts (dict): Initial options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.

    Returns:
        dict: Validated options for the feature, or None if aborted.
    """
    schema = TicketDiscussionOptionsSchema()
    result = prompt_with_schema(schema, dict(opts), jira=jira, abort_option=True)
    if result == "__ABORT__":
        info("❌ Aborted ticket discussion summary prompt.")
        return None
    return result 