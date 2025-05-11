# advanced_metrics.py
# This feature calculates advanced metrics for Jira issues, such as cycle time and lead time, for a given user and timeframe.
# It prompts for user, start/end dates, fetches completed issues, and outputs a Markdown report with a metrics table.

from datetime import datetime
from jirassicpack.cli import ensure_output_dir
from jirassicpack.utils import get_option, validate_required, validate_date, error, spinner, safe_get, build_context, write_markdown_file, require_param, info, render_markdown_report, redact_sensitive
from typing import Any, Dict, List, Tuple
from statistics import mean, median
from collections import defaultdict, Counter
import logging
import time

logger = logging.getLogger(__name__)

def prompt_advanced_metrics_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prompt for advanced metrics options using get_option utility.
    Prompts for user, start date, and end date.
    Returns a dictionary of all options needed for the metrics calculation.
    """
    user = get_option(options, 'user', prompt="Jira Username for metrics:", required=True)
    start_date = get_option(options, 'start_date', prompt="Start date (YYYY-MM-DD):", default='2024-01-01', required=True, validate=validate_date)
    end_date = get_option(options, 'end_date', prompt="End date (YYYY-MM-DD):", default='2024-01-31', required=True, validate=validate_date)
    output_dir = get_option(options, 'output_dir', default='output')
    unique_suffix = options.get('unique_suffix', '')
    return {
        'user': user,
        'start_date': start_date,
        'end_date': end_date,
        'output_dir': output_dir,
        'unique_suffix': unique_suffix
    }

def advanced_metrics(jira: Any, params: Dict[str, Any], user_email=None, batch_index=None, unique_suffix=None) -> None:
    """
    Output cycle time, lead time, and a simple burndown table to Markdown.
    Prompts for user and timeframe, fetches completed issues, and calculates metrics for each.
    Outputs a Markdown report with a metrics table for analysis.
    Handles errors for missing required options or failed API calls.
    """
    context = build_context("advanced_metrics", user_email, batch_index, unique_suffix)
    start_time = time.time()
    try:
        # Enhanced feature entry log
        contextual_log('info', f"📊 [advanced_metrics] Feature entry | User: {user_email} | Params: {redact_sensitive(params)} | Suffix: {unique_suffix}", operation="feature_start", params=redact_sensitive(params), status="started", extra=context)
        if not require_param(params, 'user', context):
            return
        if not require_param(params, 'start_date', context):
            return
        if not require_param(params, 'end_date', context):
            return
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        user = params['user']
        start_date = params['start_date']
        end_date = params['end_date']
        ensure_output_dir(output_dir)
        # Fetch more fields for richer analytics
        jql = (
            f"assignee = '{user}' "
            f"AND statusCategory = Done "
            f"AND resolved >= '{start_date}' "
            f"AND resolved <= '{end_date}'"
        )
        fields = ["summary", "created", "resolutiondate", "status", "key", "issuetype", "priority", "duedate", "assignee", "changelog"]
        try:
            with spinner("📊 Running Advanced Metrics..."):
                issues = jira.search_issues(jql, fields=fields, max_results=200, context=context)
        except Exception as e:
            error(f"Failed to fetch issues: {e}. Please check your Jira connection, credentials, and network.", extra=context)
            logger.error(f"[advanced_metrics] Failed to fetch issues: {e}", exc_info=True, extra=context)
            return
        # --- Analytics Aggregation ---
        cycle_times = []
        lead_times = []
        status_times = defaultdict(list)  # status -> list of time spent
        type_cycle = defaultdict(list)
        priority_cycle = defaultdict(list)
        due_met = 0
        due_missed = 0
        due_late_days = []
        throughput_week = Counter()
        throughput_month = Counter()
        per_assignee = defaultdict(list)
        open_issues = []
        slowest = None
        fastest = None
        min_cycle = None
        max_cycle = None
        today = datetime.utcnow()
        issue_rows = []
        for issue in issues:
            fields = issue.get('fields', {})
            key = issue.get('key', 'N/A')
            summary = safe_get(issue, ['fields', 'summary'], '')
            created = safe_get(issue, ['fields', 'created'], '')[:10]
            resolved = safe_get(issue, ['fields', 'resolutiondate'], '')[:10]
            status = safe_get(issue, ['fields', 'status', 'name'], '')
            itype = safe_get(issue, ['fields', 'issuetype', 'name'], '')
            priority = safe_get(issue, ['fields', 'priority', 'name'], '')
            duedate = safe_get(issue, ['fields', 'duedate'], '')[:10]
            assignee = safe_get(issue, ['fields', 'assignee', 'displayName'], user)
            # Cycle time
            cycle_time = None
            if created and resolved:
                try:
                    d1 = datetime.strptime(created, "%Y-%m-%d")
                    d2 = datetime.strptime(resolved, "%Y-%m-%d")
                    cycle_time = (d2 - d1).days
                    cycle_times.append(cycle_time)
                    type_cycle[itype].append(cycle_time)
                    priority_cycle[priority].append(cycle_time)
                    # Throughput
                    week = d2.strftime("%Y-W%U")
                    month = d2.strftime("%Y-%m")
                    throughput_week[week] += 1
                    throughput_month[month] += 1
                    per_assignee[assignee].append(cycle_time)
                    # Outliers
                    if min_cycle is None or cycle_time < min_cycle:
                        min_cycle = cycle_time
                        fastest = (key, summary, cycle_time)
                    if max_cycle is None or cycle_time > max_cycle:
                        max_cycle = cycle_time
                        slowest = (key, summary, cycle_time)
                except Exception:
                    cycle_time = 'N/A'
            # Lead time (if changelog available)
            lead_time = None
            changelog = issue.get('changelog', {}).get('histories', [])
            in_progress_date = None
            if changelog and created:
                for hist in changelog:
                    for item in hist.get('items', []):
                        if item.get('field') == 'status' and item.get('toString', '').lower() in ['in progress', 'in review', 'doing']:
                            in_progress_date = hist.get('created', '')[:10]
                            break
                    if in_progress_date:
                        break
                if in_progress_date:
                    try:
                        d1 = datetime.strptime(created, "%Y-%m-%d")
                        d2 = datetime.strptime(in_progress_date, "%Y-%m-%d")
                        lead_time = (d2 - d1).days
                        lead_times.append(lead_time)
                    except Exception:
                        lead_time = 'N/A'
            # Status time analysis (bottleneck)
            if changelog and created:
                status_entry = {}
                last_date = created
                for hist in changelog:
                    hist_date = hist.get('created', '')[:10]
                    for item in hist.get('items', []):
                        if item.get('field') == 'status':
                            prev_status = item.get('fromString', '')
                            new_status = item.get('toString', '')
                            if prev_status:
                                try:
                                    d1 = datetime.strptime(last_date, "%Y-%m-%d")
                                    d2 = datetime.strptime(hist_date, "%Y-%m-%d")
                                    status_times[prev_status].append((d2 - d1).days)
                                except Exception:
                                    pass
                        last_date = hist_date
                # Final status duration
                if status:
                    try:
                        d1 = datetime.strptime(last_date, "%Y-%m-%d")
                        d2 = datetime.strptime(resolved, "%Y-%m-%d") if resolved else today
                        status_times[status].append((d2 - d1).days)
                    except Exception:
                        pass
            # SLA/Deadline
            if duedate and resolved:
                try:
                    due_dt = datetime.strptime(duedate, "%Y-%m-%d")
                    res_dt = datetime.strptime(resolved, "%Y-%m-%d")
                    if res_dt <= due_dt:
                        due_met += 1
                    else:
                        due_missed += 1
                        due_late_days.append((key, (res_dt - due_dt).days))
                except Exception:
                    pass
            # Open/overdue
            if not resolved:
                open_issues.append((key, summary, created))
            # Issue row for table
            issue_rows.append((key, summary, itype, priority, status, created, resolved, cycle_time if cycle_time is not None else '', lead_time if lead_time is not None else '', duedate, assignee))
        # --- Aggregated Stats ---
        avg_cycle = round(mean(cycle_times), 2) if cycle_times else 'N/A'
        med_cycle = round(median(cycle_times), 2) if cycle_times else 'N/A'
        min_cycle_val = min_cycle if min_cycle is not None else 'N/A'
        max_cycle_val = max_cycle if max_cycle is not None else 'N/A'
        avg_lead = round(mean(lead_times), 2) if lead_times else 'N/A'
        med_lead = round(median(lead_times), 2) if lead_times else 'N/A'
        # Cycle time buckets
        buckets = {'<2d': 0, '2-5d': 0, '>5d': 0}
        for ct in cycle_times:
            if ct < 2:
                buckets['<2d'] += 1
            elif ct <= 5:
                buckets['2-5d'] += 1
            else:
                buckets['>5d'] += 1
        # Per-user stats
        assignee_stats = {a: (len(lst), round(mean(lst),2) if lst else 'N/A') for a, lst in per_assignee.items()}
        # --- Markdown Output ---
        summary_section = f"**Total issues resolved:** {len(cycle_times)}\n\n**Average cycle time:** {avg_cycle} days\n\n**Median cycle time:** {med_cycle} days"
        if fastest:
            summary_section += f"\n\n**Fastest issue:** {fastest[0]} ({fastest[2]} days)"
        if slowest:
            summary_section += f"\n\n**Slowest issue:** {slowest[0]} ({slowest[2]} days)"
        if avg_lead != 'N/A':
            summary_section += f"\n\n**Average lead time:** {avg_lead} days"
        if med_lead != 'N/A':
            summary_section += f"\n\n**Median lead time:** {med_lead} days"
        details_section = "## Cycle Time Distribution\n"
        details_section += f"- <2 days: {buckets['<2d']} issues\n"
        details_section += f"- 2–5 days: {buckets['2-5d']} issues\n"
        details_section += f"- >5 days: {buckets['>5d']} issues\n"
        details_section += "\n## Throughput by Month\n"
        for m in sorted(throughput_month):
            details_section += f"- {m}: {throughput_month[m]} issues\n"
        details_section += "\n## Cycle Time by Type\n"
        for t, vals in type_cycle.items():
            details_section += f"- {t}: {round(mean(vals),2) if vals else 'N/A'} days\n"
        details_section += "\n## Cycle Time by Priority\n"
        for p, vals in priority_cycle.items():
            details_section += f"- {p}: {round(mean(vals),2) if vals else 'N/A'} days\n"
        details_section += "\n## SLA/Deadline Analysis\n"
        details_section += f"- Issues met due date: {due_met}\n"
        details_section += f"- Issues missed due date: {due_missed}\n"
        if due_late_days:
            details_section += f"- Avg days late: {round(mean([d for _,d in due_late_days]),2)}\n"
            details_section += f"- Most late: {max(due_late_days, key=lambda x: x[1])}\n"
        details_section += "\n## Per-Assignee Stats\n"
        for a, (count, avg) in assignee_stats.items():
            details_section += f"- {a}: {count} issues, avg cycle time {avg} days\n"
        details_section += "\n## Status/Stage Analysis\n"
        for s, vals in status_times.items():
            details_section += f"- {s}: avg {round(mean(vals),2) if vals else 'N/A'} days\n"
        details_section += "\n## Outliers and Action Items\n"
        if open_issues:
            details_section += f"- Open/Unresolved issues: {len(open_issues)}\n"
            for k, s, c in open_issues:
                details_section += f"  - {k}: {s} (created {c})\n"
        details_section += "\n## Issue Table\n"
        details_section += "| Key | Summary | Type | Priority | Status | Created | Resolved | Cycle Time | Lead Time | Due Date | Assignee |\n"
        details_section += "|-----|---------|------|----------|--------|---------|----------|------------|-----------|----------|----------|\n"
        for row in issue_rows:
            details_section += f"| {' | '.join(str(x) for x in row)} |\n"
        filename = f"{output_dir}/{user}_{start_date}_to_{end_date}_advanced_metrics{unique_suffix}.md"
        content = render_markdown_report(
            feature="advanced_metrics",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="Advanced Metrics",
            summary_section=summary_section,
            main_content_section=details_section
        )
        with open(filename, 'w') as f:
            f.write(content)
        # Enhanced output file write log
        contextual_log('info', f"Markdown file written: {filename}", operation="output_write", output_file=filename, status="success", extra=context)
        # Enhanced feature end log
        duration = int((time.time() - start_time) * 1000)
        contextual_log('info', f"📊 [advanced_metrics] Feature complete | Suffix: {unique_suffix}", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context)
    except KeyboardInterrupt:
        contextual_log('warning', "[advanced_metrics] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context)
        info("Graceful exit from Advanced Metrics feature.", extra=context)
    except Exception as e:
        contextual_log('error', f"[advanced_metrics] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context)
        error(f"[advanced_metrics] Exception: {e}", extra=context)
        raise 