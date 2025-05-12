import os
from jirassicpack.utils.io import ensure_output_dir, info, error, spinner, get_option, prompt_text, prompt_select, prompt_password, prompt_checkbox, prompt_path, render_markdown_report_template
from jirassicpack.utils.logging import contextual_log
from jirassicpack.utils.io import safe_get
import openai
from datetime import datetime
import re
from github import Github
import requests
from jirassicpack.utils.jira import search_issues
from marshmallow import Schema, fields, ValidationError
from jirassicpack.utils.rich_prompt import rich_error
from jirassicpack.config import ConfigLoader
from jirassicpack.utils.fields import BaseOptionsSchema

openai.api_key = os.environ.get("OPENAI_API_KEY")

llm_config = ConfigLoader().get_llm_config()

def call_local_llm_text(prompt):
    url = llm_config['text_url']
    response = requests.post(url, json={"prompt": prompt})
    response.raise_for_status()
    return response.json()["response"]

def call_local_llm_github_pr(repo_name, pr_number, github_token, prompt=None):
    """
    Calls the local LLM HTTP API to analyze a GitHub PR directly, letting the local LLM handle the GitHub API call.
    Optionally sends a custom prompt to the local LLM.
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

def call_local_llm_file(file_path):
    """
    Sends a file to the local LLM HTTP API for analysis via the /generate/file endpoint.
    The file is uploaded as multipart/form-data.
    """
    url = "http://localhost:5000/generate/file"
    with open(file_path, "rb") as f:
        files = {"file": (file_path, f)}
        response = requests.post(url, files=files)
    response.raise_for_status()
    return response.json()["response"]

def select_jira_issues(jira):
    """
    Interactive multi-issue selection: search, pick, or enter manually. Returns a list of issue keys.
    """
    issues = []
    while True:
        method = prompt_select(
            "How would you like to select issues?",
            choices=[
                "Search for issues",
                "Enter issue key manually",
                "Done",
                "Abort"
            ],
            default="Search for issues"
        )
        if method == "Abort":
            return []
        elif method == "Done":
            break
        elif method == "Enter issue key manually":
            issue_key = prompt_text("Enter issue key:")
            if issue_key and issue_key not in issues:
                issues.append(issue_key)
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
            choices = [f"{issue.get('key','?')}: {issue.get('fields',{}).get('summary','?')}" for issue in found]
            picked = prompt_checkbox("Select issues:", choices=choices)
            for p in picked:
                key = p.split(':')[0]
                if key and key not in issues:
                    issues.append(key)
    return issues

def ticket_discussion_summary(jira, params, user_email=None, batch_index=None, unique_suffix=None):
    """
    Summarize one or more Jira tickets' discussion and resolution using LLM.
    Now uses standardized Markdown report template.
    """
    issue_keys = params.get("issue_keys") or ([params["issue_key"]] if "issue_key" in params else [])
    output_dir = params.get("output_dir", "output")
    ensure_output_dir(output_dir)
    for issue_key in issue_keys:
        context = {"feature": "ticket_discussion_summary", "user": user_email, "batch": batch_index, "suffix": unique_suffix, "issue_key": issue_key}
        try:
            with spinner(f"Fetching issue {issue_key}..."):
                issue = jira.get_task(issue_key)
        except Exception as e:
            error(f"Failed to fetch issue: {e}", extra=context)
            continue
        fields = issue.get("fields", {})
        description = fields.get("description", "")
        ac_field = os.environ.get("JIRA_ACCEPTANCE_CRITERIA_FIELD", "customfield_10001")
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
        report = render_markdown_report_template(
            report_header=header,
            table_of_contents=toc,
            report_summary=summary_table,
            action_items=action_items,
            top_n_lists=top_n_lists,
            related_links=related_links,
            grouped_issue_sections=grouped_section,
            export_metadata=export_metadata,
            glossary=glossary,
            next_steps=next_steps
        )
        filename = os.path.join(output_dir, f"ticket_discussion_summary_{issue_key}.md")
        with open(filename, 'w') as f:
            f.write(report)
        info(f"💬 Ticket discussion summary written to {filename}", extra=context)

class TicketDiscussionSummaryOptionsSchema(BaseOptionsSchema):
    issue_keys = fields.List(fields.Str(), required=True)

def prompt_ticket_discussion_summary_options(opts, jira=None):
    """
    Prompt for ticket discussion summary options, supporting multi-issue selection.
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