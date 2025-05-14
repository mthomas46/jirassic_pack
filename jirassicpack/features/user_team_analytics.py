# user_team_analytics.py
# This feature analyzes team workload in Jira by counting issues assigned to each team member in a given timeframe.
# It prompts for team members, start/end dates, and outputs a Markdown report with workload and bottleneck analysis.

from jirassicpack.utils.io import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, info, prompt_with_validation, validate_required, validate_date, error, spinner, info_spared_no_expense, get_option, status_emoji
from jirassicpack.utils.logging import contextual_log, redact_sensitive, build_context
from jirassicpack.utils.jira import select_jira_user
from jirassicpack.utils.io import render_markdown_report, render_markdown_report_template
from datetime import datetime
from typing import Any, Dict, List
from colorama import Fore, Style
from statistics import mean, median
import logging
import time
import questionary
import os
from mdutils.mdutils import MdUtils

logger = logging.getLogger(__name__)

# Module-level cache for Jira users
_CACHED_JIRA_USERS = None

def prompt_user_team_analytics_options(opts: Dict[str, Any], jira: Any = None) -> Dict[str, Any]:
    """
    Prompt for user/team analytics options, always requiring explicit team member selection. Config/env value is only used if the user selects it.
    Args:
        opts (Dict[str, Any]): Options/config dictionary.
        jira (Any, optional): Jira client for interactive selection.
    Returns:
        Dict[str, Any]: Validated options for the feature.
    """
    info(f"[DEBUG] prompt_user_team_analytics_options called. jira is {'present' if jira else 'None'}. opts: {opts}")
    config_team = opts.get('team') or os.environ.get('JIRA_TEAM')
    team = None
    users = []
    if not team and jira:
        info("Please select Jira team members for analytics.")
        label_user_tuples = select_jira_user(jira, allow_multiple=True)
        if not label_user_tuples:
            info("Aborted team member selection.")
            return None
        # Use accountId for each user
        users = [user_obj.get('accountId') for label, user_obj in label_user_tuples if user_obj and user_obj.get('accountId')]
        if not users:
            info("No valid users selected for team analytics.")
            return None
        team = ','.join(users)
    elif not team:
        team = get_option(opts, 'team', prompt="Team members (comma-separated usernames):", required=True)
    start = get_option(opts, 'start_date', prompt="Start date (YYYY-MM-DD):", default='2024-01-01', required=True, validate=validate_date)
    end = get_option(opts, 'end_date', prompt="End date (YYYY-MM-DD):", default='2024-01-31', required=True, validate=validate_date)
    out_dir = get_option(opts, 'output_dir', default='output')
    suffix = opts.get('unique_suffix', '')
    return {
        'team': team,
        'start_date': start,
        'end_date': end,
        'output_dir': out_dir,
        'unique_suffix': suffix
    }

def write_team_analytics_file(
    filename: str,
    start_date: str,
    end_date: str,
    workload: Dict[str, int],
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None,
    context: dict = None
) -> None:
    """
    Write a Markdown file for team analytics, including workload distribution and bottleneck analysis.
    Args:
        filename (str): Output file path.
        start_date (str): Start date for the analytics period.
        end_date (str): End date for the analytics period.
        workload (Dict[str, int]): Workload data per user.
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
        context (dict, optional): Additional context for logging.
    Returns:
        None. Writes a Markdown report to disk.
    """
    try:
        output_path = f"{filename}"
        md_file = MdUtils(file_name=output_path, title="Team Analytics Report")
        md_file.new_line(f"_Generated: {datetime.now()}_")
        md_file.new_header(level=2, title="Summary")
        # Replace all manual markdown with mdutils methods for sections, tables, lists, etc.
        # ... build report ...
        md_file.create_md_file()
        info(f"🦖 Team analytics report written to {output_path}")
    except Exception as e:
        contextual_log('error', f"Failed to write team analytics file: {e}", exc_info=True, operation="output_write", error_type=type(e).__name__, status="error", extra=context, feature='user_team_analytics')
        error(f"Failed to write team analytics file: {e}", extra=context, feature='user_team_analytics')

def generate_analytics(issues: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Generate analytics: count issues per assignee.
    Args:
        issues (List[Dict[str, Any]]): List of Jira issues.
    Returns:
        Dict[str, int]: Mapping of assignee to issue count.
    """
    workload = {}
    for issue in issues:
        assignee = issue['fields'].get('assignee', {}).get('displayName', 'Unassigned')
        workload[assignee] = workload.get(assignee, 0) + 1
    return workload

def write_analytics_file(filename: str, analytics: Dict[str, int], user_email: str = None, batch_index: int = None, unique_suffix: str = None, context: dict = None) -> None:
    """
    Write analytics to a Markdown file.
    Args:
        filename (str): Output file path.
        analytics (Dict[str, int]): Analytics data to write.
        user_email (str, optional): Email of the user running the report.
        batch_index (int, optional): Batch index for batch runs.
        unique_suffix (str, optional): Unique suffix for output file naming.
        context (dict, optional): Additional context for logging.
    Returns:
        None. Writes a Markdown file to disk.
    """
    try:
        with open(filename, 'w') as f:
            f.write(f"# User/Team Analytics\n\n")
            f.write("| User | Issue Count |\n|------|-------------|\n")
            for user, count in analytics.items():
                f.write(f"| {user} | {count} |\n")
            if analytics:
                max_user = max(analytics, key=analytics.get)
                min_user = min(analytics, key=analytics.get)
                f.write(f"\n**Most loaded:** {max_user} ({analytics[max_user]} issues)\n")
                f.write(f"**Least loaded:** {min_user} ({analytics[min_user]} issues)\n")
        contextual_log('info', f"Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=context, feature='user_team_analytics')
    except Exception as e:
        contextual_log('error', f"Failed to write analytics file: {e}", exc_info=True, operation="output_write", error_type=type(e).__name__, status="error", extra=context, feature='user_team_analytics')
        error(f"Failed to write analytics file: {e}", extra=context, feature='user_team_analytics')

def user_team_analytics(
    jira: Any,
    params: Dict[str, Any],
    user_email: str = None,
    batch_index: int = None,
    unique_suffix: str = None
) -> None:
    """
    Generate a user/team analytics report for Jira issues, including workload, bottlenecks, and status/type breakdowns.
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
    correlation_id = params.get('correlation_id')
    context = build_context("user_team_analytics", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    try:
        contextual_log('info', f"🧬 [User/Team Analytics] Starting feature for user '{user_email}' with params: {redact_sensitive(params)} (suffix: {unique_suffix})", operation="feature_start", params=redact_sensitive(params), extra=context, feature='user_team_analytics')
        orig_search_issues = getattr(jira, 'search_issues', None)
        if orig_search_issues:
            def log_search_issues(*args, **kwargs):
                contextual_log('debug', f"Jira search_issues: args={args}, kwargs={redact_sensitive(kwargs)}", extra=context, feature='user_team_analytics')
                resp = orig_search_issues(*args, **kwargs)
                contextual_log('debug', f"Jira search_issues response: {resp}", extra=context, feature='user_team_analytics')
                return resp
            jira.search_issues = log_search_issues
        team = params.get('team')
        if not team:
            error("team is required.", extra=context, feature='user_team_analytics')
            return
        start_date = params.get('start_date')
        if not start_date:
            error("start_date is required.", extra=context, feature='user_team_analytics')
            return
        end_date = params.get('end_date')
        if not end_date:
            error("end_date is required.", extra=context, feature='user_team_analytics')
            return
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        ensure_output_dir(output_dir)
        users = [u.strip() for u in team.split(",") if u.strip()]
        all_user_data = {}
        team_stats = {
            "total_issues": 0,
            "created": 0,
            "resolved": 0,
            "blockers": [],
            "critical": [],
            "blocked": [],
            "oldest_unresolved": None,
            "age_buckets": {"30d": 0, "60d": 0, "90d": 0},
            "unresolved_ages": [],
            "self_assigned": 0,
            "assigned_by_others": 0,
            "linked": 0,
            "blocking": [],
            "blocked_by": [],
            "reporters": {},
        }
        for user in users:
            user_jql = (
                f"assignee = '{user}' "
                f"AND updated >= '{start_date}' "
                f"AND updated <= '{end_date}'"
            )
            def do_user_analytics():
                with spinner(f"🧬 Fetching issues for {user}..."):
                    return jira.search_issues(
                        user_jql,
                        fields=[
                            "key", "summary", "status", "issuetype", "priority", "created", "updated", "resolutiondate",
                            "reporter", "labels", "issuelinks"
                        ],
                        max_results=100
                    )
            issues = retry_or_skip(f"Fetching issues for {user}", do_user_analytics)
            if not issues:
                all_user_data[user] = {"issues": [], "summary": {}}
                continue
            # Aggregate analytics
            status_counts = {}
            type_counts = {}
            priority_counts = {}
            cycle_times = []
            oldest = None
            newest = None
            unresolved_ages = []
            age_buckets = {"30d": 0, "60d": 0, "90d": 0}
            created_count = 0
            resolved_count = 0
            blockers = []
            critical = []
            blocked = []
            self_assigned = 0
            assigned_by_others = 0
            linked = 0
            blocking = []
            blocked_by = []
            reporters = {}
            today = datetime.utcnow()
            for issue in issues:
                fields = issue.get('fields', {})
                status = fields.get('status', {}).get('name', 'N/A')
                status_counts[status] = status_counts.get(status, 0) + 1
                itype = fields.get('issuetype', {}).get('name', 'N/A')
                type_counts[itype] = type_counts.get(itype, 0) + 1
                priority = fields.get('priority', {}).get('name', 'N/A')
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
                created = fields.get('created')
                updated = fields.get('updated')
                resolved = fields.get('resolutiondate')
                reporter = fields.get('reporter', {}).get('displayName', 'N/A')
                reporters[reporter] = reporters.get(reporter, 0) + 1
                # Throughput/activity
                if created and start_date <= created[:10] <= end_date:
                    created_count += 1
                if resolved and start_date <= resolved[:10] <= end_date:
                    resolved_count += 1
                # Self-assigned vs assigned by others
                if reporter == user:
                    self_assigned += 1
                else:
                    assigned_by_others += 1
                # Issue age buckets (unresolved only)
                if not resolved and created:
                    age_days = (today - datetime.strptime(created[:10], "%Y-%m-%d")).days
                    unresolved_ages.append(age_days)
                    if age_days > 90:
                        age_buckets["90d"] += 1
                    elif age_days > 60:
                        age_buckets["60d"] += 1
                    elif age_days > 30:
                        age_buckets["30d"] += 1
                    # Track oldest unresolved
                    if not team_stats["oldest_unresolved"] or age_days > team_stats["oldest_unresolved"]["age"]:
                        team_stats["oldest_unresolved"] = {"user": user, "key": issue.get('key'), "age": age_days}
                # Blockers/critical
                if priority in ["Blocker", "Highest", "Critical"]:
                    critical.append(issue.get('key'))
                    team_stats["critical"].append((user, issue.get('key')))
                if status.lower() == "blocked" or "blocked" in [l.lower() for l in fields.get('labels', [])]:
                    blocked.append(issue.get('key'))
                    team_stats["blocked"].append((user, issue.get('key')))
                # Linked issues
                links = fields.get('issuelinks', [])
                if links:
                    linked += 1
                    team_stats["linked"] += 1
                    for link in links:
                        if link.get('type', {}).get('name', '').lower() == 'blocks' and link.get('outwardIssue'):
                            blocking.append(link['outwardIssue'].get('key'))
                            team_stats["blocking"].append((user, issue.get('key'), link['outwardIssue'].get('key')))
                        if link.get('type', {}).get('name', '').lower() == 'is blocked by' and link.get('inwardIssue'):
                            blocked_by.append(link['inwardIssue'].get('key'))
                            team_stats["blocked_by"].append((user, issue.get('key'), link['inwardIssue'].get('key')))
                # Track oldest/newest
                if created:
                    if not oldest or created < oldest:
                        oldest = created
                    if not newest or created > newest:
                        newest = created
                # Cycle time
                if created and resolved:
                    try:
                        d1 = datetime.strptime(created[:10], "%Y-%m-%d")
                        d2 = datetime.strptime(resolved[:10], "%Y-%m-%d")
                        cycle_times.append((d2 - d1).days)
                    except Exception:
                        pass
            avg_cycle = round(mean(cycle_times), 2) if cycle_times else 'N/A'
            med_cycle = round(median(cycle_times), 2) if cycle_times else 'N/A'
            avg_unresolved_age = round(mean(unresolved_ages), 2) if unresolved_ages else 'N/A'
            med_unresolved_age = round(median(unresolved_ages), 2) if unresolved_ages else 'N/A'
            all_user_data[user] = {
                "issues": issues,
                "summary": {
                    "status_counts": status_counts,
                    "type_counts": type_counts,
                    "priority_counts": priority_counts,
                    "avg_cycle": avg_cycle,
                    "med_cycle": med_cycle,
                    "oldest": oldest[:10] if oldest else 'N/A',
                    "newest": newest[:10] if newest else 'N/A',
                    "total": len(issues),
                    "created": created_count,
                    "resolved": resolved_count,
                    "created_vs_resolved": f"{resolved_count}/{created_count}" if created_count else 'N/A',
                    "blockers": blockers,
                    "critical": critical,
                    "blocked": blocked,
                    "age_buckets": age_buckets,
                    "avg_unresolved_age": avg_unresolved_age,
                    "med_unresolved_age": med_unresolved_age,
                    "self_assigned": self_assigned,
                    "assigned_by_others": assigned_by_others,
                    "linked": linked,
                    "blocking": blocking,
                    "blocked_by": blocked_by,
                    "reporters": reporters,
                }
            }
            # Team summary aggregation
            team_stats["total_issues"] += len(issues)
            team_stats["created"] += created_count
            team_stats["resolved"] += resolved_count
            team_stats["age_buckets"]["30d"] += age_buckets["30d"]
            team_stats["age_buckets"]["60d"] += age_buckets["60d"]
            team_stats["age_buckets"]["90d"] += age_buckets["90d"]
            team_stats["unresolved_ages"].extend(unresolved_ages)
            team_stats["self_assigned"] += self_assigned
            team_stats["assigned_by_others"] += assigned_by_others
            for r, c in reporters.items():
                team_stats["reporters"][r] = team_stats["reporters"].get(r, 0) + c
        if not any(len(data["issues"]) for data in all_user_data.values()):
            info("🦖 See, Nobody Cares. No analytics data found.", extra=context, feature='user_team_analytics')
            contextual_log('info', "🦖 See, Nobody Cares. No analytics data found.", extra=context, feature='user_team_analytics')
            return
        # Write expanded analytics to Markdown
        filename = f"{output_dir}/user_team_analytics{unique_suffix}.md"
        try:
            summary_section = f"**Total issues:** {team_stats['total_issues']}\n\n**Created in period:** {team_stats['created']}\n\n**Resolved in period:** {team_stats['resolved']}\n\n**Resolved/Created ratio:** {team_stats['resolved']}/{team_stats['created']}\n\n**Self-assigned:** {team_stats['self_assigned']} | **Assigned by others:** {team_stats['assigned_by_others']}\n\n**Issues with links:** {team_stats['linked']}\n\n**Blockers/Critical:** {len(team_stats['critical'])}\n\n**Blocked:** {len(team_stats['blocked'])}"
            if team_stats['oldest_unresolved']:
                summary_section += f"\n\n**Oldest unresolved:** {team_stats['oldest_unresolved']['key']} (User: {team_stats['oldest_unresolved']['user']}, Age: {team_stats['oldest_unresolved']['age']} days)"
            if team_stats['unresolved_ages']:
                summary_section += f"\n\n**Avg unresolved age:** {round(mean(team_stats['unresolved_ages']),2)} | **Median unresolved age:** {round(median(team_stats['unresolved_ages']),2)}"
            summary_section += f"\n\n**Unresolved age buckets:** >30d: {team_stats['age_buckets']['30d']}, >60d: {team_stats['age_buckets']['60d']}, >90d: {team_stats['age_buckets']['90d']}\n\n**Top reporters:**\n"
            for r, c in sorted(team_stats['reporters'].items(), key=lambda x: -x[1]):
                summary_section += f"- {r}: {c}\n"
            details_section = ""
            for user, data in all_user_data.items():
                summary = data["summary"]
                issues = data["issues"]
                details_section += f"\n## {user}\n\n"
                details_section += f"**Total issues:** {summary['total']}\n\n**Created in period:** {summary['created']}\n\n**Resolved in period:** {summary['resolved']}\n\n**Resolved/Created ratio:** {summary['created_vs_resolved']}\n\n**Self-assigned:** {summary['self_assigned']} | **Assigned by others:** {summary['assigned_by_others']}\n\n**Issues with links:** {summary['linked']}\n\n**Blockers/Critical:** {len(summary['critical'])}\n\n**Blocked:** {len(summary['blocked'])}\n"
                if summary['blockers']:
                    details_section += f"**Blocker/Critical Issues:** {', '.join(summary['blockers'])}\n\n"
                if summary['blocked']:
                    details_section += f"**Blocked Issues:** {', '.join(summary['blocked'])}\n\n"
                if summary['blocking']:
                    details_section += f"**Blocking Issues:** {', '.join(summary['blocking'])}\n\n"
                if summary['blocked_by']:
                    details_section += f"**Blocked By Issues:** {', '.join(summary['blocked_by'])}\n\n"
                if summary['oldest'] != 'N/A':
                    details_section += f"**Oldest ticket:** {summary['oldest']}\n\n"
                if summary['newest'] != 'N/A':
                    details_section += f"**Newest ticket:** {summary['newest']}\n\n"
                if summary['avg_cycle'] != 'N/A':
                    details_section += f"**Average cycle time (days):** {summary['avg_cycle']}\n\n"
                if summary['med_cycle'] != 'N/A':
                    details_section += f"**Median cycle time (days):** {summary['med_cycle']}\n\n"
                if summary['avg_unresolved_age'] != 'N/A':
                    details_section += f"**Avg unresolved age:** {summary['avg_unresolved_age']}\n\n"
                if summary['med_unresolved_age'] != 'N/A':
                    details_section += f"**Median unresolved age:** {summary['med_unresolved_age']}\n\n"
                details_section += f"**Unresolved age buckets:** >30d: {summary['age_buckets']['30d']}, >60d: {summary['age_buckets']['60d']}, >90d: {summary['age_buckets']['90d']}\n\n"
                details_section += "### Status Breakdown\n"
                for k, v in summary['status_counts'].items():
                    details_section += f"- {k}: {v}\n"
                details_section += "\n### Type Breakdown\n"
                for k, v in summary['type_counts'].items():
                    details_section += f"- {k}: {v}\n"
                details_section += "\n### Priority Breakdown\n"
                for k, v in summary['priority_counts'].items():
                    details_section += f"- {k}: {v}\n"
                details_section += "\n### Reporter Breakdown\n"
                for k, v in summary['reporters'].items():
                    details_section += f"- {k}: {v}\n"
                details_section += "\n### Issue List\n"
                details_section += "| Key | Summary | Status | Type | Priority | Created | Updated | Resolved | Reporter | Links |\n"
                details_section += "|-----|---------|--------|------|----------|---------|---------|----------|----------|-------|\n"
                for issue in issues:
                    fields = issue.get('fields', {})
                    key = issue.get('key', 'N/A')
                    summary_txt = fields.get('summary', 'N/A').replace('|', '/')
                    status = fields.get('status', {}).get('name', 'N/A')
                    itype = fields.get('issuetype', {}).get('name', 'N/A')
                    priority = fields.get('priority', {}).get('name', 'N/A')
                    created = fields.get('created', 'N/A')[:10]
                    updated = fields.get('updated', 'N/A')[:10]
                    resolved = fields.get('resolutiondate', 'N/A')[:10] if fields.get('resolutiondate') else 'N/A'
                    reporter = fields.get('reporter', {}).get('displayName', 'N/A')
                    links = fields.get('issuelinks', [])
                    link_str = str(len(links)) if links else ''
                    details_section += f"| {key} | {summary_txt} | {status} | {itype} | {priority} | {created} | {updated} | {resolved} | {reporter} | {link_str} |\n"
                details_section += "\n---\n\n"
            content = render_markdown_report(
                feature="user_team_analytics",
                user=user_email,
                batch=batch_index,
                suffix=unique_suffix,
                feature_title="User & Team Analytics",
                summary_section=summary_section,
                main_content_section=details_section
            )
            with open(filename, 'w') as f:
                f.write(content)
            contextual_log('info', f"Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=context, feature='user_team_analytics')
            info(f"🧬 User/team analytics written to {filename}", extra=context, feature='user_team_analytics')
            duration = int((time.time() - start_time) * 1000)
            contextual_log('info', f"🧬 [User/Team Analytics] Feature completed successfully for user '{user_email}' (suffix: {unique_suffix}). Duration: {duration}ms.", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='user_team_analytics')
        except Exception as e:
            contextual_log('error', f"Failed to write analytics file: {e}", exc_info=True, operation="output_write", error_type=type(e).__name__, status="error", extra=context, feature='user_team_analytics')
            error(f"Failed to write analytics file: {e}", extra=context, feature='user_team_analytics')
            contextual_log('error', f"[User/Team Analytics] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", extra=context, feature='user_team_analytics')
        celebrate_success()
        info_spared_no_expense()
        info(f"🧬 User/team analytics written to {filename}", extra=context, feature='user_team_analytics')
    except KeyboardInterrupt:
        contextual_log('warning', "🧬 [User/Team Analytics] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context, feature='user_team_analytics')
        info("Graceful exit from User & Team Analytics feature.", extra=context, feature='user_team_analytics')
    except Exception as e:
        if 'list index out of range' in str(e):
            info("🦖 See, Nobody Cares. No analytics data found.", extra=context, feature='user_team_analytics')
            contextual_log('info', "🦖 See, Nobody Cares. No analytics data found.", extra=context, feature='user_team_analytics')
            return
        contextual_log('error', f"🧬 [User/Team Analytics] Exception occurred: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='user_team_analytics')
        error(f"🧬 [User/Team Analytics] Exception: {e}", extra=context, feature='user_team_analytics')
        raise 