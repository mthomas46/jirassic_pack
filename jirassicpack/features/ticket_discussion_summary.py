import os
from jirassicpack.utils.io import ensure_output_dir, info, error, spinner
from jirassicpack.utils.logging import contextual_log
from jirassicpack.utils.io import safe_get
import openai
from datetime import datetime
import re
from github import Github
import requests

openai.api_key = os.environ.get("OPENAI_API_KEY")

def call_local_llm_text(prompt):
    url = "http://localhost:5000/generate/text"  # Ollama7BPoc Flask API
    response = requests.post(url, json={"prompt": prompt})
    response.raise_for_status()
    return response.json()["response"]

def call_local_llm_github_pr(repo_name, pr_number, github_token, prompt=None):
    """
    Calls the local LLM HTTP API to analyze a GitHub PR directly, letting the local LLM handle the GitHub API call.
    Optionally sends a custom prompt to the local LLM.
    """
    url = "http://localhost:5000/generate/github-pr"
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

def ticket_discussion_summary(jira, params, user_email=None, batch_index=None, unique_suffix=None):
    """
    Summarize a Jira ticket's discussion and resolution using LLM.
    Fetches description, acceptance criteria, and comments, sends to LLM, outputs Markdown summary.
    """
    context = {"feature": "ticket_discussion_summary", "user": user_email, "batch": batch_index, "suffix": unique_suffix}
    issue_key = params.get("issue_key")
    output_dir = params.get("output_dir", "output")
    ensure_output_dir(output_dir)
    if not issue_key:
        error("issue_key is required for Ticket Discussion Summary.", extra=context)
        return
    try:
        with spinner(f"Fetching issue {issue_key}..."):
            issue = jira.get_task(issue_key)
    except Exception as e:
        error(f"Failed to fetch issue: {e}", extra=context)
        return
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

    # --- GitHub PR Analysis via Jira Development Panel ---
    github_section = ''
    dev_panel = fields.get('development') or fields.get('customfield_development')
    github_prs = []
    if dev_panel and 'pullRequests' in dev_panel:
        github_prs = dev_panel['pullRequests']
    pr_analyses = []
    tech_summaries = []
    if github_prs:
        github_token = os.environ.get('GITHUB_TOKEN')
        if not github_token:
            try:
                import questionary
                github_token = questionary.password("Enter your GitHub API token (for PR analysis):").ask()
            except Exception:
                github_token = None
        gh = Github(github_token) if github_token else Github()
        for pr in github_prs:
            pr_url = pr.get('url') or pr.get('remoteUrl') or pr.get('self')
            if not pr_url:
                continue
            m = re.match(r'https://github.com/([^/]+)/([^/]+)/pull/(\d+)', pr_url)
            if not m:
                continue
            owner, repo, number = m.groups()
            try:
                repo_obj = gh.get_repo(f"{owner}/{repo}")
                pr_obj = repo_obj.get_pull(int(number))
                pr_title = pr_obj.title or ''
                pr_body = pr_obj.body or ''
                # PR comments (issue comments)
                comments_data = list(pr_obj.get_issue_comments())
                # PR reviews
                reviews_data = list(pr_obj.get_reviews())
                # PR commits
                commits_data = list(pr_obj.get_commits())
            except Exception as e:
                continue
            pr_comments = '\n'.join([c.body for c in comments_data])
            pr_reviews = '\n'.join([r.body for r in reviews_data if r.body])
            commit_msgs = '\n'.join([c.commit.message for c in commits_data if hasattr(c, 'commit') and hasattr(c.commit, 'message')])
            # --- Technical Summary Section ---
            code_and_docs = []
            code_and_docs += re.findall(r'```[\s\S]*?```', pr_body)
            doc_commits = [msg for msg in commit_msgs.split('\n') if 'readme' in msg.lower() or 'doc' in msg.lower()]
            for c in comments_data:
                code_and_docs += re.findall(r'```[\s\S]*?```', getattr(c, 'body', ''))
            tech_prompt = f"""
Analyze the following code snippets, comments, and documentation-related commit messages for technical changes, improvements, or documentation updates. Summarize the technical impact and any documentation changes:

Code/Docs:
{chr(10).join(code_and_docs)}

Documentation-related commits:
{chr(10).join(doc_commits)}
"""
            tech_summary = ''
            if code_and_docs or doc_commits:
                try:
                    with spinner(f"Summarizing technical/code changes for PR #{number} with LLM..."):
                        tech_summary = call_local_llm_text(tech_prompt)
                except Exception:
                    tech_summary = "(Failed to summarize technical/code changes via local LLM)"
            else:
                tech_summary = "No code snippets or documentation updates detected."
            tech_summaries.append(f"### [{pr_title}]({pr_url})\n{tech_summary}")
            # --- PR Analysis Section ---
            gh_prompt = f"""
Summarize the following GitHub PR for a technical audience:
- PR Title: {pr_title}
- PR Description: {pr_body}
- PR Comments: {pr_comments}
- PR Reviews: {pr_reviews}
- Commit Messages: {commit_msgs}

Highlight major discussion points, code changes, errors, and the resolution/outcome.
"""
            try:
                with spinner(f"Summarizing GitHub PR #{number} with LLM..."):
                    gh_summary = call_local_llm_text(gh_prompt)
            except Exception:
                gh_summary = "(Failed to summarize PR via local LLM)"
            pr_analyses.append(f"### [{pr_title}]({pr_url})\n{gh_summary}")
    # Always show both sections, even if empty
    if not tech_summaries:
        tech_summaries = ["No code snippets or documentation updates detected."]
    if not pr_analyses:
        pr_analyses = ["No GitHub PRs found or analyzed."]
    github_section = '\n## Technical Summary\n' + '\n\n'.join(tech_summaries) + '\n\n## GitHub Pull Request Analysis\n' + '\n\n'.join(pr_analyses) + '\n'

    # --- Jira Discussion Section ---
    jira_discussion_prompt = f"""
Summarize the following Jira ticket's description, acceptance criteria, and comments. Highlight the initial context, major points of discussion, and any resolutions or open questions.

**Description:**
{description}

**Acceptance Criteria:**
{acceptance_criteria}

**Comments:**
{comments_text}
"""
    jira_discussion_summary = ''
    if description or acceptance_criteria or comments_text:
        try:
            with spinner("Summarizing Jira discussion with LLM..."):
                jira_response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": jira_discussion_prompt}],
                    max_tokens=512,
                    temperature=0.3,
                )
                jira_discussion_summary = jira_response.choices[0].message.content.strip()
        except Exception:
            jira_discussion_summary = "(Failed to summarize Jira discussion via LLM)"
    else:
        jira_discussion_summary = "No Jira discussion found."
    jira_section = f"\n## Jira Discussion\n{jira_discussion_summary}\n"

    # --- Final Analysis Section ---
    final_analysis_prompt = f"""
Given the following sections from a Jira ticket summary:

[Jira Discussion]
{jira_discussion_summary}

[Technical Summary]
{chr(10).join(tech_summaries)}

[GitHub Pull Request Analysis]
{chr(10).join(pr_analyses)}

[Linked Pull Requests]
{pr_section}

Analyze and extrapolate the current state of the ticket and describe its progression from start to finish. Highlight any blockers, resolutions, or next steps.
"""
    final_analysis = ''
    try:
        with spinner("Generating final analysis with LLM..."):
            final_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": final_analysis_prompt}],
                max_tokens=512,
                temperature=0.3,
            )
            final_analysis = final_response.choices[0].message.content.strip()
    except Exception:
        final_analysis = "(Failed to generate final analysis via LLM)"
    final_section = f"\n## Final Analysis\n{final_analysis}\n"

    prompt = f"""
You are an expert technical summarizer. Given the following Jira ticket data, produce a Markdown summary with:
- Initial context
- Major points of discussion
- Summaries of code examples
- Errors discussed
- Resolution (if any)

---

**Description:**
{description}

**Acceptance Criteria:**
{acceptance_criteria}

**Comments:**
{comments_text}
"""
    try:
        with spinner("Summarizing with LLM..."):
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.3,
            )
            summary = response.choices[0].message.content.strip()
    except Exception as e:
        error(f"LLM summarization failed: {e}", extra=context)
        return
    filename = f"{output_dir}/{issue_key}_discussion_summary{unique_suffix or ''}.md"
    with open(filename, "w") as f:
        f.write(f"# Ticket Discussion Summary and Resolution\n\n**Issue:** {issue_key}\n"
                f"{jira_section}"
                f"{github_section}"
                f"{pr_section}"
                f"{final_section}")
    info(f"📝 Ticket discussion summary written to {filename}", extra=context) 