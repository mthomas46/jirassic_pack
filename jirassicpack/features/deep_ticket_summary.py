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
    ensure_output_dir(output_dir)
    context = build_context("deep_ticket_summary", user_email, batch_index, unique_suffix, issue_key=issue_key)
    with spinner(f"Fetching issue {issue_key}..."):
        issue = jira.get(f'issue/{issue_key}', params={'expand': 'changelog,renderedFields'})
    if not issue or not isinstance(issue, dict) or not issue.get('fields'):
        info(f"🦖 See, Nobody Cares. No data found for issue {issue_key}. Raw response: {issue}", extra=context)
        contextual_log('info', f"🦖 See, Nobody Cares. No data found for issue {issue_key}. Raw response: {issue}", extra=context)
        return
    fields = issue.get("fields", {})
    changelog = issue.get("changelog", {}).get("histories", [])
    description = fields.get("description", "")
    # Ensure rendered_description is always defined
    rendered_description = safe_string(description) or ""
    config = ConfigLoader()
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
            contextual_log('info', f'[deep_ticket_summary] Sending LLM prompt for {section}', extra={**context, 'prompt': prompt[:500]})
            llm_futures[section] = executor.submit(call_openai_llm, prompt, "gpt-3.5-turbo", 512, 0.2)
        for section, future in llm_futures.items():
            try:
                response = future.result(timeout=60)
                contextual_log('info', f'[deep_ticket_summary] LLM response for {section}', extra={**context, 'response': str(response)[:500]})
                ai_section_blocks[section] = response
            except Exception as e:
                contextual_log('error', f'[deep_ticket_summary] LLM call failed for {section}', extra={**context, 'exception': str(e)})
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
    contextual_log('info', '[deep_ticket_summary] Starting AI/LLM analysis for report', extra=context)
    ai_error_messages = []
    # After AI/LLM analysis, log each section
    for section in [
        "AI Summary", "Risk Flags", "Action Items", "Business Value", "Stakeholder Mapping", "Process/Workflow Insights", "Knowledge/Documentation Value"
    ]:
        content = ai_section_blocks.get(section, "_No data available._")
        if content == "_No data available._":
            msg = f"[deep_ticket_summary] AI section '{section}' missing or failed."
            ai_error_messages.append(msg)
            contextual_log('warning', msg, extra=context)
        else:
            contextual_log('info', f"[deep_ticket_summary] AI section '{section}' generated.", extra={**context, 'ai_section': section, 'ai_content': str(content)[:500]})
    if ai_error_messages:
        contextual_log('error', '[deep_ticket_summary] Some AI/LLM sections failed or are missing.', extra={**context, 'ai_errors': ai_error_messages})
    else:
        contextual_log('info', '[deep_ticket_summary] All AI/LLM sections generated successfully.', extra=context)

    # --- Fetch linked tickets and perform AI analysis on relationships ---
    linked_issues = fields.get('issuelinks', [])
    linked_insights = []
    linked_ticket_infos = []
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
                        contextual_log(
                            'error',
                            f"[deep_ticket_summary] 'jira.get' is not callable. Type: {type(jira.get)}",
                            extra={**context, 'linked_key': linked_key}
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
                    contextual_log(
                        'error',
                        f"[deep_ticket_summary] Error fetching or processing linked ticket {linked_key}: {e}",
                        extra={**context, 'linked_key': linked_key}
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
        contextual_log('info', '[deep_ticket_summary] Sending LLM prompt for linked ticket ecosystem analysis', extra={**context, 'prompt': ecosystem_prompt[:500]})
        ecosystem_analysis = call_openai_llm(ecosystem_prompt, "gpt-3.5-turbo", 1024, 0.3)
        contextual_log('info', '[deep_ticket_summary] LLM response for linked ticket ecosystem', extra={**context, 'response': str(ecosystem_analysis)[:500]})
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
        contextual_log('info', f'[deep_ticket_summary] Sending LLM prompt for linked ticket analysis: {info["key"]}', extra={**context, 'prompt': rel_prompt[:500]})
        rel_analysis = call_openai_llm(rel_prompt, "gpt-3.5-turbo", 512, 0.2)
        contextual_log('info', f'[deep_ticket_summary] LLM response for linked ticket {info["key"]}', extra={**context, 'response': str(rel_analysis)[:500]})
        linked_insights.append(f"**{info['relationship']} [{info['key']}](https://your-domain.atlassian.net/browse/{info['key']})**\n\n{rel_analysis}")
    # --- Compose Insights & Analysis section ---
    insights_block = "## Insights & Analysis\n\n"
    if linked_insights:
        insights_block += "### AI Analysis of Linked Tickets\n\n" + "\n\n".join(linked_insights) + "\n\n---\n\n"
    elif 'insights' in locals():
        insights_block += insights + "---\n\n"
    else:
        insights_block += "_No additional insights available._\n---\n\n"

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
        "- [Report Footer](#report-footer)\n\n"
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
        'grouped_sections': ai_section_header + description_acceptance + comments_changelog + insights_block + (related_links if 'related_links' in locals() else ''),
        'metadata': f"## Metadata\n---\n**Report generated by:** {user_email}  \n**Run at:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  \n",
        'glossary': glossary if 'glossary' in locals() else '',
        'next_steps': next_steps if 'next_steps' in locals() else '',
        'footer': "## Report Footer\n---\nThank you for using the Deep Ticket Summary feature. For questions or feedback, contact the Jira Analytics Team.\n"
    }
    report = build_report_sections(sections)
    filename = os.path.join(output_dir, f"deep_ticket_summary_{issue_key}.md")
    write_report(filename, report, context, filetype='md', feature='deep_ticket_summary', item_name='Deep ticket summary report')
    logging.info(f"🦖 Deep ticket summary written to {filename}", extra=context)


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