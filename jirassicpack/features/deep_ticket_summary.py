"""
deep_ticket_summary.py

Feature module for generating a deep summary report for a single Jira ticket via the CLI.
Fetches all available information (description, comments, changelog, fields, etc.) and outputs a detailed Markdown report for audit and review.
"""

from jirassicpack.utils.output_utils import ensure_output_dir, write_report, status_emoji
from jirassicpack.utils.message_utils import info
from jirassicpack.utils.validation_utils import get_option, safe_get
from jirassicpack.utils.decorators import feature_error_handler
from jirassicpack.utils.progress_utils import spinner
from jirassicpack.config import ConfigLoader
from datetime import datetime
import os
from typing import Any
from jirassicpack.analytics.helpers import build_report_sections
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.utils.llm import call_openai_llm
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import subprocess
import requests
import base64
import re
from jirassicpack.jira_client import JiraClient
from dotenv import load_dotenv
from github import GithubException


def safe_string(val):
    """Convert any value to a safe string for Markdown rendering."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        # Try to parse Atlassian Document Format (ADF) to text
        if val.get('type') == 'doc' and 'content' in val:
            return adf_to_text(val)
        return str(val)
    if isinstance(val, list):
        return '\n'.join([safe_string(v) for v in val])
    return str(val)


def adf_to_text(adf):
    """Recursively extract plain text from Atlassian Document Format (ADF) dicts."""
    if isinstance(adf, dict):
        if adf.get('type') == 'text' and 'text' in adf:
            return adf['text']
        elif 'content' in adf:
            return ''.join([adf_to_text(child) for child in adf['content']])
        else:
            return ''
    elif isinstance(adf, list):
        return ''.join([adf_to_text(item) for item in adf])
    return ''


@feature_error_handler('deep_ticket_summary')
def deep_ticket_summary(
    jira: Any,
    params: dict,
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Generate a deep summary report for a single Jira ticket, including all available information:
    - Description
    - Comments/discussion
    - Edits/changelog
    - Acceptance criteria
    - Resolution
    - Contextual fields (priority, type, status, reporter, assignee, components, labels, etc.)
    - Professional summary of the ticket's lifecycle

    Args:
        jira (Any): Authenticated Jira client instance.
        params (dict): Parameters for the summary (issue key, output_dir, etc).
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
    Returns:
        None. Writes a Markdown report to disk.
    """
    issue_key = params.get("issue_key")
    output_dir = params.get("output_dir", "output")
    context = build_context("deep_ticket_summary", user_email, batch_index, unique_suffix, issue_key=issue_key)
    ensure_output_dir(output_dir)
    safe_contextual_log('info', '[deep_ticket_summary] Entered function', context)
    load_dotenv()
    with spinner(f"Fetching issue {issue_key}..."):
        issue = jira.get(f'issue/{issue_key}', params={'expand': 'changelog,renderedFields'})
    safe_contextual_log('info', '[deep_ticket_summary] Issue fetched', context, issue=str(issue)[:500])
    if not issue or not isinstance(issue, dict) or not issue.get('fields'):
        info(f"🦖 See, Nobody Cares. No data found for issue {issue_key}. Raw response: {issue}", context)
        safe_contextual_log('info', f"🦖 See, Nobody Cares. No data found for issue {issue_key}. Raw response: {issue}", context)
        return
    fields = issue.get("fields", {})
    changelog = issue.get("changelog", {}).get("histories", [])
    description = fields.get("description", "")
    # Ensure rendered_description is always defined
    rendered_description = safe_string(description) or ""
    config = ConfigLoader()
    safe_contextual_log('info', '[deep_ticket_summary] Jira config loaded', context, jira_url=config.get('url', ''), email=config.get('email', ''), api_token_present=bool(config.get('api_token', '')))
    ac_field = params.get("acceptance_criteria_field") or config.get("acceptance_criteria_field", "customfield_10001")
    acceptance_criteria = fields.get(ac_field, "")
    comments = safe_get(fields, ["comment", "comments"], [])
    resolution = (fields.get("resolution") or {}).get("name", "N/A")
    status = (fields.get("status") or {}).get("name", "N/A")
    reporter = (fields.get("reporter") or {}).get("displayName", "N/A")
    assignee = (fields.get("assignee") or {}).get("displayName", "N/A")
    priority = (fields.get("priority") or {}).get("name", "N/A")
    issue_type = (fields.get("issuetype") or {}).get("name", "N/A")
    created = fields.get("created", "")
    updated = fields.get("updated", "")
    resolved = fields.get("resolutiondate", "")
    components = ', '.join([c['name'] for c in fields.get('components', [])])
    labels = ', '.join(fields.get('labels', []))
    project = safe_get(fields, ["project", "key"], "N/A")
    # Ensure Jira client uses YAML config parameters
    jira_conf = config.get_jira_config()
    jira_base_url = (jira_conf.get('url', '') if jira_conf else '').rstrip('/')
    api_token = jira_conf.get('api_token') if jira_conf else None
    user_email = jira_conf.get('email') if jira_conf else None
    # If the jira client is not already constructed with these, reconstruct it
    if hasattr(jira, 'base_url') and hasattr(jira, 'email') and hasattr(jira, 'api_token'):
        # If the client is already correct, do nothing
        pass
    else:
        jira = JiraClient(jira_base_url, user_email, api_token)
    # Now all jira.get calls and other usage will use the correct config
    # --- Compose enhanced report sections ---
    # Ensure ai_section_blocks is defined for all usages
    if 'ai_section_blocks' not in locals():
        ai_section_blocks = {}
    llm_error = False
    # Ensure ai_section_blocks has placeholders for expected sections
    expected_ai_sections = [
        "AI Summary", "Risk Flags", "Action Items", "Business Value", "Stakeholder Mapping", "Process/Workflow Insights", "Knowledge/Documentation Value"
    ]
    for section in expected_ai_sections:
        if section not in ai_section_blocks:
            ai_section_blocks[section] = "_No data available._"
            llm_error = True
    ai_sections = list(ai_section_blocks.keys())
    # --- AI/LLM Analysis: Populate ai_section_blocks with real LLM content ---
    ai_prompts = {
        "AI Summary": f"Summarize the following Jira ticket for an executive audience. Focus on the main goal, current state, blockers, and next steps.\n\nDescription:\n{rendered_description}\n\nAcceptance Criteria:\n{acceptance_criteria}",
        "Risk Flags": f"Identify and explain any risks, blockers, or potential issues in this Jira ticket.\n\nDescription:\n{rendered_description}",
        "Action Items": f"List clear, actionable next steps for this Jira ticket.\n\nDescription:\n{rendered_description}",
        "Business Value": f"Explain the business value and impact of this Jira ticket.\n\nDescription:\n{rendered_description}",
        "Stakeholder Mapping": f"List key stakeholders and their roles for this Jira ticket.\n\nDescription:\n{rendered_description}",
        "Process/Workflow Insights": f"Describe any process or workflow insights, bottlenecks, or improvements suggested by this Jira ticket.\n\nDescription:\n{rendered_description}",
        "Knowledge/Documentation Value": f"What knowledge or documentation value does this Jira ticket provide for future reference?\n\nDescription:\n{rendered_description}"
    }
    # Run LLM calls in parallel for speed
    llm_futures = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        for section, prompt in ai_prompts.items():
            safe_contextual_log('info', f'[deep_ticket_summary] Sending LLM prompt for {section}', context, prompt=prompt[:500])
            llm_futures[section] = executor.submit(call_openai_llm, prompt, "gpt-3.5-turbo", 512, 0.2)
        for section, future in llm_futures.items():
            try:
                response = future.result(timeout=60)
                safe_contextual_log('info', f'[deep_ticket_summary] LLM response for {section}', context, response=str(response)[:500])
                ai_section_blocks[section] = response
            except Exception as e:
                safe_contextual_log('error', f'[deep_ticket_summary] LLM call failed for {section}', context, exception=str(e))
                ai_section_blocks[section] = "_No data available._"
                llm_error = True
    # --- Acceptance Criteria: Extrapolate or enhance using LLM after AI/LLM analysis ---
    if not acceptance_criteria:
        ai_prompt = f"Based on the following Jira ticket description, comments, and analysis, extrapolate a set of clear, testable acceptance criteria.\n\nDescription:\n{rendered_description}\n\nComments:\n{safe_string(comments)}\n\nAnalysis:\n{safe_string(ai_section_blocks.get('AI Summary', ''))}"
        try:
            acceptance_criteria = call_openai_llm(ai_prompt)
        except Exception as e:
            acceptance_criteria = "_No acceptance criteria found or generated._"
    else:
        # If present, enhance with AI
        ai_prompt = f"Given the following acceptance criteria and the full ticket analysis, suggest improvements or clarifications to make them more robust and testable.\n\nAcceptance Criteria:\n{safe_string(acceptance_criteria)}\n\nDescription:\n{rendered_description}\n\nAnalysis:\n{safe_string(ai_section_blocks.get('AI Summary', ''))}"
        try:
            enhanced_criteria = call_openai_llm(ai_prompt)
            if enhanced_criteria and enhanced_criteria.strip() and enhanced_criteria.strip() != safe_string(acceptance_criteria).strip():
                acceptance_criteria = f"{safe_string(acceptance_criteria)}\n\n---\n\n**AI-Enhanced Acceptance Criteria:**\n{enhanced_criteria}"
        except Exception as e:
            pass
    # --- AI/LLM Analysis Logging ---
    safe_contextual_log('info', '[deep_ticket_summary] Starting AI/LLM analysis for report', context)
    ai_error_messages = []
    # After AI/LLM analysis, log each section
    for section in [
        "AI Summary", "Risk Flags", "Action Items", "Business Value", "Stakeholder Mapping", "Process/Workflow Insights", "Knowledge/Documentation Value"
    ]:
        content = ai_section_blocks.get(section, "_No data available._")
        if content == "_No data available._":
            msg = f"[deep_ticket_summary] AI section '{section}' missing or failed."
            ai_error_messages.append(msg)
            safe_contextual_log('warning', msg, context)
        else:
            safe_contextual_log('info', f"[deep_ticket_summary] AI section '{section}' generated.", context, ai_section=section, ai_content=str(content)[:500])
    if ai_error_messages:
        safe_contextual_log('error', '[deep_ticket_summary] Some AI/LLM sections failed or are missing.', context, ai_errors=ai_error_messages)
    else:
        safe_contextual_log('info', '[deep_ticket_summary] All AI/LLM sections generated successfully.', context)

    # --- Fetch linked tickets and perform AI analysis on relationships ---
    linked_issues = fields.get('issuelinks', [])
    linked_insights = []
    linked_ticket_infos = []
    # --- Scrape Jira comments for GitHub PR URLs ---
    pr_urls_found = []
    safe_contextual_log('info', '[deep_ticket_summary] Scraping Jira comments for GitHub PR URLs', context, num_comments=len(comments))
    for c in comments:
        body = safe_string(c.get('body', ''))
        # Simple regex for GitHub PR URLs in plain text
        urls = re.findall(r'https://github\.com/[^/]+/[^/]+/pull/\d+', body)
        # Also extract URLs from HTML <a> tags (if present)
        html_links = re.findall(r'<a [^>]*href=["\\\']([^"\\\']+)["\\\']', body)
        # Filter for GitHub PR URLs in links
        html_pr_urls = [u for u in html_links if re.match(r'https://github\.com/[^/]+/[^/]+/pull/\d+', u)]
        all_urls = urls + html_pr_urls
        if all_urls:
            pr_urls_found.extend(all_urls)
            safe_contextual_log('info', '[deep_ticket_summary] Found GitHub PR URLs in comment', context, comment_id=c.get('id'), urls=all_urls)
    if pr_urls_found:
        safe_contextual_log('info', '[deep_ticket_summary] Total GitHub PR URLs found in comments', context, pr_urls=pr_urls_found)
    else:
        safe_contextual_log('info', '[deep_ticket_summary] No GitHub PR URLs found in Jira comments', context)
    if linked_issues:
        for link in linked_issues:
            inward = link.get('inwardIssue')
            outward = link.get('outwardIssue')
            linked_issue = inward or outward
            if linked_issue:
                linked_key = linked_issue.get('key')
                try:
                    # Debug: Check type of jira.get before calling
                    if not hasattr(jira, "get") or not callable(jira.get):
                        safe_contextual_log(
                            'error',
                            f"[deep_ticket_summary] 'jira.get' is not callable. Type: {type(jira.get)}",
                            context,
                            linked_key=linked_key
                        )
                        continue  # Skip this linked ticket
                    linked_data = jira.get(f'issue/{linked_key}')
                    linked_fields = linked_data.get('fields', {})
                    linked_summary = safe_string(linked_fields.get('summary', ''))
                    linked_description = safe_string(linked_fields.get('description', ''))
                    linked_ac_field = params.get("acceptance_criteria_field") or config.get("acceptance_criteria_field", "customfield_10001")
                    linked_acceptance_criteria = linked_fields.get(linked_ac_field, "")
                    relationship = link.get('type', {}).get('name', 'Related')
                    linked_ticket_infos.append({
                        'key': linked_key,
                        'summary': linked_summary,
                        'description': linked_description,
                        'acceptance_criteria': linked_acceptance_criteria,
                        'relationship': relationship,
                    })
                except Exception as e:
                    safe_contextual_log(
                        'error',
                        f"[deep_ticket_summary] Error fetching or processing linked ticket {linked_key}: {e}",
                        context,
                        linked_key=linked_key
                    )
    # Compose ecosystem prompt if more than one linked ticket
    if len(linked_ticket_infos) > 1:
        ecosystem_prompt = (
            f"Analyze the ecosystem of the following Jira tickets.\n"
            f"Main Ticket: {issue_key} - {rendered_description}\n\n"
            f"Linked Tickets:\n"
        )
        for info in linked_ticket_infos:
            ecosystem_prompt += (
                f"- {info['relationship']} [{info['key']}](https://your-domain.atlassian.net/browse/{info['key']}): {info['summary']}\n"
                f"  Description: {info['description']}\n"
                f"  Acceptance Criteria: {info['acceptance_criteria']}\n"
            )
        ecosystem_prompt += (
            "\nConsider all tickets as a system. Describe clusters, dependencies, business value, and any red flags or risks that may exist in the ecosystem. Call out valuable relationships, blockers, or opportunities."
        )
        safe_contextual_log('info', '[deep_ticket_summary] Sending LLM prompt for linked ticket ecosystem analysis', context, prompt=ecosystem_prompt[:500])
        ecosystem_analysis = call_openai_llm(ecosystem_prompt, "gpt-3.5-turbo", 1024, 0.3)
        safe_contextual_log('info', '[deep_ticket_summary] LLM response for linked ticket ecosystem', context, response=str(ecosystem_analysis)[:500])
        linked_insights.append(f"**Ecosystem Analysis of Linked Tickets**\n\n{ecosystem_analysis}")
    elif len(linked_ticket_infos) == 1:
        info = linked_ticket_infos[0]
        rel_prompt = (
            f"Analyze the relationship between the following two Jira tickets.\n"
            f"Ticket 1: {issue_key} - {rendered_description}\n"
            f"Ticket 2: {info['key']} - {info['summary']}\n"
            f"Ticket 2 Description: {info['description']}\n"
            f"Ticket 2 Acceptance Criteria: {info['acceptance_criteria']}\n"
            f"Relationship: {info['relationship']}\n"
            f"Describe the impact, business value, and any red flags or risks that may exist between these tickets.\n"
            f"If there are valuable dependencies, blockers, or opportunities, call them out explicitly."
        )
        safe_contextual_log('info', f'[deep_ticket_summary] Sending LLM prompt for linked ticket analysis: {info["key"]}', context, prompt=rel_prompt[:500])
        rel_analysis = call_openai_llm(rel_prompt, "gpt-3.5-turbo", 512, 0.2)
        safe_contextual_log('info', f'[deep_ticket_summary] LLM response for linked ticket {info["key"]}', context, response=str(rel_analysis)[:500])
        linked_insights.append(f"**{info['relationship']} [{info['key']}](https://your-domain.atlassian.net/browse/{info['key']})**\n\n{rel_analysis}")
    # --- Compose Insights & Analysis section ---
    insights_block = "## Insights & Analysis\n\n"
    if linked_insights:
        insights_block += "### AI Analysis of Linked Tickets\n\n" + "\n\n".join(linked_insights) + "\n\n---\n\n"
    elif 'insights' in locals():
        insights_block += insights + "---\n\n"
    else:
        insights_block += "_No additional insights available._\n---\n\n"

    # --- GitHub Analysis Section ---
    github_analysis_section = "## GitHub Analysis\n\n"
    pr_found = False
    pr_analysis = ""
    pr_note = ""
    # 1. Primary: Use Jira dev-status API (development metadata) for GitHub PR/branch info
    safe_contextual_log('info', '[deep_ticket_summary] Looking for GitHub PR/branch via Jira dev-status API', context)
    jira_headers = None
    jira_config_incomplete = False
    if not (jira_base_url and api_token and user_email):
        jira_config_incomplete = True
        error_msg = "> ⚠️ **Warning:** Jira base URL, email, or API token missing from config. Cannot perform Jira dev-status API lookup. Please check your configuration.\n\n"
        github_analysis_section += error_msg
        safe_contextual_log('error', '[deep_ticket_summary] Jira dev-status API config incomplete', context, jira_base_url=jira_base_url, api_token_present=bool(api_token), user_email=user_email)
    else:
        auth_str = f"{user_email}:{api_token}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        jira_headers = {
            "Authorization": f"Basic {b64_auth}",
            "Accept": "application/json"
        }
        try:
            issue_id = issue.get('id')
            dev_status_url = f"{jira_base_url}/rest/dev-status/1.0/issue/detail?issueId={issue_id}&applicationType=github&dataType=branch,pullrequest"
            safe_contextual_log('info', '[deep_ticket_summary] Requesting Jira dev-status API', context, dev_status_url=dev_status_url)
            response = requests.get(dev_status_url, headers=jira_headers)
            # Log the full JSON response for debugging
            try:
                dev_status_json = response.json()
            except Exception as e:
                dev_status_json = f"[Could not decode JSON: {e}]"
            safe_contextual_log('info', '[deep_ticket_summary] Full Jira dev-status API JSON response', context, status_code=response.status_code, dev_status_json=str(dev_status_json)[:2000])
            safe_contextual_log('info', '[deep_ticket_summary] Jira dev-status API response', context, status_code=response.status_code, response_text=response.text[:500])
            if response.status_code != 200:
                raise Exception(f"Jira dev-status API returned {response.status_code}: {response.text}")
            dev_status = dev_status_json
            details = dev_status.get('detail', [])
            pr_info = None
            branch_info = None
            for d in details:
                prs = d.get('pullRequests', [])
                branches = d.get('branches', [])
                if prs:
                    pr_info = prs[0]
                    break
                if branches:
                    branch_info = branches[0]
            safe_contextual_log('info', '[deep_ticket_summary] Parsed Jira dev-status API result', context, pr_info=str(pr_info)[:500], branch_info=str(branch_info)[:500])
            if pr_info:
                pr_found = True
                pr_title = pr_info.get('title', '')
                pr_url = pr_info.get('url', '')
                pr_desc = pr_info.get('description', '')
                pr_files = ', '.join([f.get('filename', '') for f in pr_info.get('files', [])])
                pr_diff_url = pr_info.get('diffUrl', '')
                diff = f"See PR diff at: {pr_diff_url}" if pr_diff_url else "Diff not available."
                code_analysis_prompt = f"Analyze the following pull request for Jira ticket {issue_key}.\n\nAcceptance Criteria:\n{acceptance_criteria}\n\nPR Title: {pr_title}\nPR Description: {pr_desc}\nFiles Changed: {pr_files}\nDiff: {diff}\n\nSummarize what the PR solves, and give a confidence report on whether it meets the acceptance criteria."
                try:
                    pr_analysis = call_openai_llm(code_analysis_prompt, "gpt-3.5-turbo", 512, 0.2)
                    github_analysis_section += f"<details><summary><b>Show GitHub PR Analysis (from Jira dev-status)</b></summary>\n\n{pr_analysis}\n\n</details>\n"
                except Exception as e:
                    github_analysis_section += f"> ⚠️ **Warning:** LLM analysis of the PR (from Jira dev-status) failed: {e}\n\n"
            elif branch_info:
                branch_name = branch_info.get('name', '')
                github_analysis_section += f"> 📢 **Info:** No PR found, but branch detected via Jira dev-status: `{branch_name}`.\n\n"
            else:
                github_analysis_section += "> 📢 **Info:** No pull request or branch found for this ticket via Jira dev-status.\n\n"
            # Additional: Call dev-status API for summary endpoint and log the result (restore if removed)
            summary_status_url = f"{jira_base_url}/rest/dev-status/latest/issue/summary?issueId={issue_id}"
            try:
                summary_response = requests.get(summary_status_url, headers=jira_headers)
                try:
                    summary_status_json = summary_response.json()
                except Exception as e:
                    summary_status_json = f"[Could not decode JSON: {e}]"
                safe_contextual_log('info', '[deep_ticket_summary] Full Jira dev-status API JSON response (summary endpoint)', context, status_code=summary_response.status_code, summary_status_json=str(summary_status_json)[:2000])
            except Exception as e:
                safe_contextual_log('error', '[deep_ticket_summary] Error during Jira dev-status API summary endpoint lookup', context, exception=str(e))

            # Additional: Try multiple GraphQL queries to get branch/PR info
            graphql_url = f"{jira_base_url}/gateway/api/graphql"
            graphql_headers = dict(jira_headers) if jira_headers else {}
            graphql_headers["Content-Type"] = "application/json"
            graphql_headers["X-ExperimentalApi"] = "ariGraph,boardCardMove,deleteCard,JiraJqlBuilder,SoftwareCardTypeTransitions,jira-releases-v0,JiraDevOps,JiraDevOpsProviders,createCustomFilter,updateCustomFilter,deleteCustomFilter,customFilters,PermissionScheme,JiraIssue,projectStyle,startSprintPrototype,AddIssuesToFixVersion,JiraVersionResult,JiraIssueConnectionJql,JiraFieldOptionSearching,JiraIssueFieldMutations,JiraIssueDevInfoDetails,JiraIssueDevSummaryCache,JiraVersionWarningConfig,JiraReleaseNotesConfiguration,JiraUpdateReleaseNotesConfiguration,ReleaseNotes,ReleaseNotesOptions,DeploymentsFeaturePrecondition,UpdateVersionWarningConfig,UpdateVersionName,UpdateVersionDescription,UpdateVersionStartDate,UpdateVersionReleaseDate,VersionsForProject,RelatedWork,SuggestedRelatedWorkCategories,setIssueMediaVisibility,toggleBoardFeature,DevOpsProvider,DevOpsSummarisedDeployments,virtual-agent-beta,JiraProject,DevOpsSummarisedEntities,RoadmapsMutation,RoadmapsQuery,JiraApplicationProperties,JiraIssueSearch,JiraFilter,featureGroups,setBoardEstimationType,devOps,softwareBoards,name,AddRelatedWorkToVersion,RemoveRelatedWorkFromVersion,admins,canAdministerBoard,jql,globalCardCreateAdditionalFields,GlobalTimeTrackingSettings,ReleaseNotesOptions,search-experience,MoveOrRemoveIssuesToFixVersion,compass-beta,JiraIssueSearchStatus,Townsquare,JiraNavigationItems"

            graphql_attempts = [
                {
                    'name': 'jiraIssue',
                    'query': '''\nquery GetIssue($issueId: String!) {\n  jiraIssue(issueId: $issueId) {\n    id\n    key\n    devInfoSummary {\n      branches {\n        name\n        url\n      }\n      pullRequests {\n        id\n        url\n        title\n        status\n      }\n    }\n  }\n}\n''',
                    'variables': {"issueId": issue_id}
                },
                {
                    'name': 'issueById',
                    'query': '''\nquery GetIssue($issueId: ID!) {\n  issueById(id: $issueId) {\n    id\n    key\n    devInfoSummary {\n      branches {\n        name\n        url\n      }\n      pullRequests {\n        id\n        url\n        title\n        status\n      }\n    }\n  }\n}\n''',
                    'variables': {"issueId": issue_id}
                },
                {
                    'name': 'search',
                    'query': '''\nquery SearchIssues($query: String!) {\n  search(query: $query) {\n    issues {\n      id\n      key\n      devInfoSummary {\n        branches {\n          name\n          url\n        }\n        pullRequests {\n          id\n          url\n          title\n          status\n        }\n      }\n    }\n  }\n}\n''',
                    'variables': {"query": f"key = {issue_key}"}
                }
            ]
            last_graphql_error = None
            for attempt in graphql_attempts:
                try:
                    graphql_payload = {"query": attempt['query'], "variables": attempt['variables']}
                    graphql_response = requests.post(graphql_url, headers=graphql_headers, json=graphql_payload)
                    try:
                        graphql_result = graphql_response.json()
                    except Exception as e:
                        graphql_result = f"[Could not decode JSON: {e}]"
                    safe_contextual_log('info', f"[deep_ticket_summary] Jira GraphQL dev info response ({attempt['name']})", context, status_code=graphql_response.status_code, graphql_result=str(graphql_result)[:2000])
                    # If we get data, stop trying further queries
                    if isinstance(graphql_result, dict) and (graphql_result.get('data') or (isinstance(graphql_result.get('data'), dict) and len(graphql_result.get('data')) > 0)):
                        break
                    last_graphql_error = graphql_result
                except Exception as e:
                    last_graphql_error = str(e)
                    safe_contextual_log('error', f"[deep_ticket_summary] Error during Jira GraphQL dev info lookup ({attempt['name']})", context, exception=str(e))
            if last_graphql_error and (not isinstance(last_graphql_error, dict) or not last_graphql_error.get('data')):
                safe_contextual_log('error', '[deep_ticket_summary] All Jira GraphQL dev info queries failed', context, last_graphql_error=str(last_graphql_error)[:2000])
        except Exception as e:
            safe_contextual_log('error', '[deep_ticket_summary] Error during Jira dev-status API lookup', context, exception=str(e))
            github_analysis_section += f"> ⚠️ **Warning:** Could not analyze GitHub via Jira dev-status: {e}\n\n"
        except GithubException as e:
            if hasattr(e, 'status') and e.status == 403:
                print("[WARN] 403 Forbidden: Token does not have access to the repo. Falling back to code_analysis_test_file.py from GitHub.")
                contextual_log('warning', '[deep_ticket_summary] 403 Forbidden on GitHub repo access. Fetching code_analysis_test_file.py from GitHub.', context)
                # Fallback: fetch the test file from GitHub
                github_conf = config.get_github_config() if hasattr(config, 'get_github_config') else config.get('github', {})
                github_token = github_conf.get('token')
                repo_owner = github_conf.get('owner', 'jirassicpack')
                repo_name = github_conf.get('repo', 'jirassicpack')
                test_file_path = 'jirassicpack/features/code_analysis_test_file.py'
                github_api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{test_file_path}"
                headers = {"Authorization": f"token {github_token}"} if github_token else {}
                try:
                    resp = requests.get(github_api_url, headers=headers)
                    if resp.status_code == 200:
                        file_json = resp.json()
                        encoded_content = file_json.get('content', '')
                        if file_json.get('encoding') == 'base64':
                            test_code = base64.b64decode(encoded_content).decode('utf-8')
                        else:
                            test_code = encoded_content
                        contextual_log('info', '[deep_ticket_summary] Successfully fetched code_analysis_test_file.py from GitHub.', context)
                        llm_result = run_llm_code_analysis(test_code)
                        report_sections.append({'title': 'Fallback Code Analysis (Test File from GitHub)', 'content': llm_result})
                        return
                    else:
                        contextual_log('error', f'[deep_ticket_summary] Failed to fetch code_analysis_test_file.py from GitHub. Status: {resp.status_code}', context)
                        report_sections.append({'title': 'Fallback Code Analysis (Test File from GitHub)', 'content': f'> ⚠️ Could not fetch code_analysis_test_file.py from GitHub. Status: {resp.status_code}'})
                        return
                except Exception as ex:
                    contextual_log('error', f'[deep_ticket_summary] Exception fetching code_analysis_test_file.py from GitHub: {ex}', context)
                    report_sections.append({'title': 'Fallback Code Analysis (Test File from GitHub)', 'content': f'> ⚠️ Exception fetching code_analysis_test_file.py from GitHub: {ex}'})
                    return
            else:
                pass  # Other GithubException errors can be handled here
    # 4. Fallback: GitHub API search for branch/PR if not found via Jira or local git
    if not pr_found:
        github_conf = config.get_github_config() if hasattr(config, 'get_github_config') else config.get('github', {})
        github_token = github_conf.get('token')
        github_org_url = github_conf.get('url', '')
        github_org = github_org_url.split('/')[-1] if github_org_url else ''
        github_headers = None
        github_config_incomplete = False
        if not (github_token and github_org):
            github_config_incomplete = True
            missing_params = []
            if not github_token:
                missing_params.append('github_token')
            if not github_org:
                missing_params.append('github_org')
            error_msg = f"> ⚠️ **Warning:** GitHub token or org missing from config ({', '.join(missing_params)}). Cannot perform GitHub API lookup. Please check your configuration.\n\n"
            github_analysis_section += error_msg
            safe_contextual_log('error', '[deep_ticket_summary] GitHub API config incomplete', context, github_token_present=bool(github_token), github_org=github_org, missing_params=missing_params)
        else:
            github_headers = {"Authorization": f"token {github_token}"}
            try:
                safe_contextual_log('info', '[deep_ticket_summary] Listing repos in org (GitHub API call)', context, github_org=github_org, url=f"https://api.github.com/orgs/{github_org}/repos")
                repos_resp = requests.get(f"https://api.github.com/orgs/{github_org}/repos", headers=github_headers)
                safe_contextual_log('info', '[deep_ticket_summary] GitHub API response for repo list', context, status_code=repos_resp.status_code)
                repos_resp.raise_for_status()
                repos = repos_resp.json()
                found_branches = []
                found_prs = []
                for repo in repos:
                    repo_name = repo['name']
                    # List branches in the repo
                    try:
                        branch_url = f"https://api.github.com/repos/{github_org}/{repo_name}/branches"
                        safe_contextual_log('info', '[deep_ticket_summary] Listing branches in repo (GitHub API call)', context, repo=repo_name, url=branch_url)
                        branches_resp = requests.get(branch_url, headers=github_headers)
                        safe_contextual_log('info', '[deep_ticket_summary] GitHub API response for branch list', context, repo=repo_name, status_code=branches_resp.status_code)
                        branches_resp.raise_for_status()
                        branches = branches_resp.json()
                        for branch in branches:
                            branch_name = branch.get('name', '')
                            if issue_key in branch_name:
                                found_branches.append({'repo': repo_name, 'branch': branch_name})
                                # Search for PRs with this branch as head
                                pr_url = f"https://api.github.com/repos/{github_org}/{repo_name}/pulls?head={github_org}:{branch_name}&state=all"
                                safe_contextual_log('info', '[deep_ticket_summary] Listing PRs for branch (GitHub API call)', context, repo=repo_name, branch=branch_name, url=pr_url)
                                prs_resp = requests.get(pr_url, headers=github_headers)
                                safe_contextual_log('info', '[deep_ticket_summary] GitHub API response for PR list', context, repo=repo_name, branch=branch_name, status_code=prs_resp.status_code)
                                prs_resp.raise_for_status()
                                prs = prs_resp.json()
                                for pr in prs:
                                    found_prs.append({'repo': repo_name, 'branch': branch_name, 'pr': pr})
                    except Exception as e:
                        safe_contextual_log('error', '[deep_ticket_summary] Error listing branches or PRs in repo', context, repo=repo_name, exception=str(e))
                if found_prs:
                    github_analysis_section += f"### GitHub PRs matching `{issue_key}`\n\n"
                    for item in found_prs:
                        pr = item['pr']
                        pr_title = pr.get('title', '')
                        pr_url = pr.get('html_url', '')
                        pr_state = pr.get('state', '')
                        pr_user = pr.get('user', {}).get('login', '')
                        pr_merged = pr.get('merged_at') is not None
                        pr_draft = pr.get('draft', False)
                        pr_status_emoji = '✔️' if pr_merged else ('🟢' if pr_state == 'open' else '🔴')
                        if pr_draft:
                            pr_status_emoji = '📝'
                        pr_status_str = f"{pr_status_emoji} "
                        if pr_merged:
                            pr_status_str += f"Merged at {pr.get('merged_at', '')}"
                        elif pr_draft:
                            pr_status_str += "Draft"
                        else:
                            pr_status_str += pr_state.capitalize()
                        github_analysis_section += f"- **Repo:** `{item['repo']}` | **Branch:** `{item['branch']}` | **PR:** [{pr_title}]({pr_url}) | **Status:** {pr_status_str} | **Author:** {pr_user}\n"
                    github_analysis_section += "\n"
                elif found_branches:
                    github_analysis_section += f"### GitHub branches matching `{issue_key}` (no PRs found)\n\n"
                    for item in found_branches:
                        github_analysis_section += f"- **Repo:** `{item['repo']}` | **Branch:** `{item['branch']}`\n"
                    github_analysis_section += "\n"
                else:
                    github_analysis_section += f"> 📢 **Info:** No branches or PRs found in GitHub repos matching `{issue_key}`.\n\n"
                safe_contextual_log('info', '[deep_ticket_summary] GitHub branch/PR lookup complete', context, found_prs=len(found_prs), found_branches=len(found_branches))
            except Exception as e:
                safe_contextual_log('error', '[deep_ticket_summary] Error during GitHub API repo/branch/PR lookup', context, exception=str(e))
                github_analysis_section += f"> ⚠️ **Warning:** Could not analyze GitHub for this ticket using GitHub API: {e}\n\n"

    # --- After scraping PR URLs, fetch PR details and analyze with LLM ---
    github_conf = config.get_github_config() if hasattr(config, 'get_github_config') else config.get('github', {})
    github_token = github_conf.get('token')
    github_org_url = github_conf.get('url', '')
    github_headers = {"Authorization": f"token {github_token}"} if github_token else {}
    # Test GitHub connection and branch visibility if at least one PR URL is found
    if pr_urls_found:
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_urls_found[0])
        if match:
            owner, repo, _ = match.groups()
            test_github_connection_and_branches(github_token, owner, repo, context)
    pr_analysis_blocks = []
    for pr_url in pr_urls_found:
        match = re.match(r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_url)
        if match:
            owner, repo, pr_number = match.groups()
            api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
            try:
                resp = requests.get(api_url, headers=github_headers)
                pr_data = resp.json()
                safe_contextual_log('info', '[deep_ticket_summary] GitHub PR API response from scraped URL', context, pr_url=pr_url, status_code=resp.status_code, pr_data=str(pr_data)[:1000])
                if resp.status_code == 200 and isinstance(pr_data, dict):
                    pr_title = pr_data.get('title', '')
                    pr_body = pr_data.get('body', '')
                    pr_state = pr_data.get('state', '')
                    pr_user = pr_data.get('user', {}).get('login', '')
                    pr_branch = pr_data.get('head', {}).get('ref', '')
                    pr_diff_url = pr_data.get('diff_url', '')
                    # Optionally fetch the diff (if you want to include it in LLM analysis)
                    diff_text = ''
                    if pr_diff_url:
                        try:
                            diff_resp = requests.get(pr_diff_url, headers=github_headers)
                            if diff_resp.status_code == 200:
                                diff_text = diff_resp.text[:2000]  # Truncate for LLM
                        except Exception as e:
                            safe_contextual_log('error', '[deep_ticket_summary] Error fetching PR diff from GitHub', context, pr_url=pr_url, exception=str(e))
                    # Call local LLM for code analysis
                    try:
                        llm_prompt = f"Analyze the following GitHub pull request.\n\nTitle: {pr_title}\nDescription: {pr_body}\nBranch: {pr_branch}\nState: {pr_state}\nAuthor: {pr_user}\nDiff (truncated):\n{diff_text}\n\nSummarize what this PR does, its risks, and whether it meets its likely acceptance criteria."
                        pr_llm_analysis = call_openai_llm(llm_prompt, "gpt-3.5-turbo", 512, 0.2)
                        pr_analysis_blocks.append(f"### Analysis of [PR #{pr_number}]({pr_url}) in `{owner}/{repo}`\n\n{pr_llm_analysis}\n")
                        safe_contextual_log('info', '[deep_ticket_summary] LLM analysis of PR from scraped URL', context, pr_url=pr_url, analysis=pr_llm_analysis[:500])
                    except Exception as e:
                        pr_analysis_blocks.append(f"### Analysis of [PR #{pr_number}]({pr_url}) in `{owner}/{repo}`\n\n> ⚠️ LLM analysis failed: {e}\n")
                        safe_contextual_log('error', '[deep_ticket_summary] LLM analysis of PR from scraped URL failed', context, pr_url=pr_url, exception=str(e))
            except Exception as e:
                safe_contextual_log('error', '[deep_ticket_summary] Error fetching GitHub PR from scraped URL', context, pr_url=pr_url, exception=str(e))
    # Add PR analysis blocks to the GitHub Analysis section of the report
    if pr_analysis_blocks:
        github_analysis_section += '\n'.join(pr_analysis_blocks)

    # --- Compose enhanced report sections (move this after LLM calls) ---
    # Visual summary block at the top
    visual_summary = (
        "# 🦖 Deep Ticket Summary Report\n\n"
        "> 💡 **Tip:** How to Use This Report\n>\n> This report provides a comprehensive, AI-enhanced summary of a Jira ticket, including business value, process insights, risks, and actionable items. Use it for executive review, audit, or knowledge sharing.\n\n"
        f"| **Key** | [{issue_key}](https://your-domain.atlassian.net/browse/{issue_key}) | **Status** | {status_emoji(status)} {status} |\n"
        f"|---|---|---|---|\n"
        f"| **Project** | {project} | **Priority** | {priority} |\n"
        f"| **Type** | {issue_type} | **Assignee** | {assignee} |\n"
        f"| **Reporter** | {reporter} | **Created** | {created} |\n"
        f"| **Updated** | {updated} | **Resolved** | {resolved} |\n"
        f"| **Components** | {components} | **Labels** | {labels} |\n"
        f"| **Resolution** | {resolution} | | |\n"
        "\n\n---\n\n"
    )
    # Table of Contents (anchors match section headers)
    toc = (
        "## Table of Contents\n"
        "- [Quick Insights](#quick-insights)\n"
        "- [AI-Generated Business Value](#ai-generated-business-value)\n"
        + ''.join([f"- [{section}](#{section.lower().replace(' ', '-')})\n" for section in ai_sections]) +
        "- [Description & Acceptance Criteria](#description--acceptance-criteria)\n"
        "- [Comments & Changelog](#comments--changelog)\n"
        "- [Insights & Analysis](#insights--analysis)\n"
        "- [Related Links](#related-links)\n"
        "- [Glossary](#glossary)\n"
        "- [Next Steps](#next-steps)\n"
        "- [Metadata](#metadata)\n"
        "- [Report Footer](#report-footer)\n"
        "- [GitHub Analysis](#github-analysis)\n\n"
    )
    # Quick Insights block (AI Summary, Risks, Action Items)
    quick_insights = (
        "## Quick Insights\n\n"
        "> 📢 **Executive Summary**\n>\n> **AI Summary:**\n> " + ai_section_blocks.get("AI Summary", "_No data available._").replace('\n', '\n> ') + "\n>\n> **Risks:**\n> " + ai_section_blocks.get("Risk Flags", "_No data available._").replace('\n', '\n> ') + "\n>\n> **Action Items:**\n> " + ai_section_blocks.get("Action Items", "_No data available._").replace('\n', '\n> ') + "\n\n---\n\n"
    )
    # Description & Acceptance Criteria
    description_acceptance = (
        "## Description & Acceptance Criteria\n\n"
        f"### Description\n{rendered_description or '_No description provided._'}\n\n"
        f"### Acceptance Criteria\n{acceptance_criteria or '_No acceptance criteria provided._'}\n\n---\n\n"
    )
    # Comments Section (collapsible with table)
    comment_rows = []
    for c in comments:
        author = safe_get(c, ["author", "displayName"], "N/A")
        created = c.get("created", "N/A")
        body = safe_string(c.get("body", ""))
        comment_rows.append(f"| {author} | {created} | {body.replace('|', '¦').replace('\\n', '<br>')} |")
    comments_table = "| Author | Created | Comment |\n|---|---|---|\n" + "\n".join(comment_rows) if comment_rows else "_No comments available._"
    comments_section = (
        f"<details><summary><b>Show Comments ({len(comments)})</b></summary>\n\n"
        f"{comments_table}\n\n"
        f"</details>\n"
    )
    # Changelog Section (collapsible with table)
    changelog_rows = []
    for entry in changelog:
        author = safe_get(entry, ["author", "displayName"], "N/A")
        created = entry.get("created", "N/A")
        items = entry.get("items", [])
        for item in items:
            field = safe_string(item.get("field", ""))
            from_string = safe_string(item.get("fromString", ""))
            to_string = safe_string(item.get("toString", ""))
            changelog_rows.append(f"| {author} | {created} | {field} | {from_string} | {to_string} |")
    changelog_table = "| Author | Date | Field | From | To |\n|---|---|---|---|---|\n" + "\n".join(changelog_rows) if changelog_rows else "_No changelog entries available._"
    changelog_section = (
        f"<details><summary><b>Show Changelog ({len(changelog_rows)})</b></summary>\n\n"
        f"{changelog_table}\n\n"
        f"</details>\n"
    )
    # Comments & Changelog
    comments_changelog = (
        "## Comments & Changelog\n\n"
        f"### Comments & Discussion\n**Total Comments:** {len(comments)}\n\n" + comments_section +
        f"### Changelog & Edits\n\n" + changelog_section +
        "---\n\n"
    )
    # AI-Generated Business Value (collapsible and explicit sections)
    ai_warning = ""
    if llm_error:
        ai_warning = "> ⚠️ **Warning:** AI analysis could not be completed for some or all sections. See logs for details.\n\n"
    ai_explicit_sections = ""
    for section, content in ai_section_blocks.items():
        content_str = safe_string(content)
        if not content_str.strip():
            continue
        ai_explicit_sections += f"<details><summary><b>{safe_string(section)}</b></summary>\n\n{content_str}\n\n</details>\n\n"
    ai_section_header = "## AI-Generated Business Value\n\n" + ai_warning + (ai_summary_collapsible if 'ai_summary_collapsible' in locals() else "") + ai_explicit_sections + "---\n\n"
    # Compose final report using build_report_sections
    sections = {
        'header': visual_summary + toc,
        'toc': '',
        'summary': quick_insights,
        'grouped_sections': ai_section_header + description_acceptance + comments_changelog + insights_block + github_analysis_section + (related_links if 'related_links' in locals() else ''),
        'metadata': f"## Metadata\n---\n**Report generated by:** {user_email}  \n**Run at:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n",
        'glossary': glossary if 'glossary' in locals() else '',
        'next_steps': next_steps if 'next_steps' in locals() else '',
        'footer': "## Report Footer\n---\nThank you for using the Deep Ticket Summary feature. For questions or feedback, contact the Jira Analytics Team.\n"
    }
    report = build_report_sections(sections)
    filename = os.path.join(output_dir, f"deep_ticket_summary_{issue_key}.md")
    write_report(filename, report, context, filetype='md', feature='deep_ticket_summary', item_name='Deep ticket summary report')
    logging.info(f"🦖 Deep ticket summary written to {filename}", context)


def prompt_deep_ticket_summary_options(opts: dict, jira: Any = None) -> dict:
    """
    Prompt for deep ticket summary options for the CLI.

    Args:
        opts (dict): Initial options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.

    Returns:
        dict: Validated options for the feature, or None if aborted.
    """
    issue_key = get_option(opts, 'issue_key', prompt="🦖 Jira Issue Key (e.g., DEMO-123):", required=True)
    if issue_key == "__ABORT__":
        info("❌ Aborted deep ticket summary prompt.")
        return None
    output_dir = get_option(opts, 'output_dir', default='output')
    if output_dir == "__ABORT__":
        info("❌ Aborted deep ticket summary prompt.")
        return None
    unique_suffix = opts.get('unique_suffix', '')
    return {
        'issue_key': issue_key,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix,
    }


def safe_contextual_log(level, msg, context, **kwargs):
    try:
        contextual_log(level, msg, extra=context, **kwargs)
    except Exception:
        contextual_log(level, msg, extra={})


def test_github_connection_and_branches(github_token, owner, repo, context):
    """
    Test GitHub API connectivity and list branches for a repo.
    Logs the result and any errors.
    """
    github_headers = {"Authorization": f"token {github_token}"} if github_token else {}
    # Test repo access
    repo_url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        repo_resp = requests.get(repo_url, headers=github_headers)
        safe_contextual_log('info', '[deep_ticket_summary] GitHub repo access test', context, repo_url=repo_url, status_code=repo_resp.status_code, repo_json=str(repo_resp.json())[:500])
        if repo_resp.status_code == 200:
            # Fetch branches
            branches_url = f"https://api.github.com/repos/{owner}/{repo}/branches"
            branches_resp = requests.get(branches_url, headers=github_headers)
            branches_json = branches_resp.json() if branches_resp.status_code == 200 else None
            branch_names = [b.get('name') for b in branches_json] if branches_json else []
            safe_contextual_log('info', '[deep_ticket_summary] GitHub branch list', context, branches_url=branches_url, status_code=branches_resp.status_code, branch_names=branch_names)
        else:
            safe_contextual_log('error', '[deep_ticket_summary] GitHub repo access failed', context, repo_url=repo_url, status_code=repo_resp.status_code)
    except Exception as e:
        safe_contextual_log('error', '[deep_ticket_summary] Exception during GitHub repo/branch test', context, repo_url=repo_url, exception=str(e)) 