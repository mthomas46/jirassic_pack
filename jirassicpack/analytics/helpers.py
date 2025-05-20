"""
helpers.py
Shared analytics/statistics/reporting helpers for all analytics features in Jirassic Pack.
- Aggregation, stats, and reporting utilities for user/team analytics, advanced metrics, and gather metrics.
- Used by: user_team_analytics, advanced_metrics, gather_metrics, etc.

TODO: Further unify reporting templates and aggregation logic as needed.
"""

from datetime import datetime
from statistics import mean, median

# --- Aggregation Helpers ---
def aggregate_issue_stats(issues):
    """
    Aggregate status/type/priority counts, cycle times, unresolved ages, and other stats from a list of Jira issues.
    Returns a dict of summary stats.
    """
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
        resolved = fields.get('resolutiondate')
        reporter = fields.get('reporter', {}).get('displayName', 'N/A')
        reporters[reporter] = reporters.get(reporter, 0) + 1
        # Throughput/activity
        if created:
            created_count += 1
        if resolved:
            resolved_count += 1
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
        # Blockers/critical
        if priority in ["Blocker", "Highest", "Critical"]:
            critical.append(issue.get('key'))
        if status.lower() == "blocked" or "blocked" in [label.lower() for label in fields.get('labels', [])]:
            blocked.append(issue.get('key'))
        # Linked issues
        links = fields.get('issuelinks', [])
        if links:
            linked += 1
            for link in links:
                if link.get('type', {}).get('name', '').lower() == 'blocks' and link.get('outwardIssue'):
                    blocking.append(link['outwardIssue'].get('key'))
                if link.get('type', {}).get('name', '').lower() == 'is blocked by' and link.get('inwardIssue'):
                    blocked_by.append(link['inwardIssue'].get('key'))
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
    return {
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
        "linked": linked,
        "blocking": blocking,
        "blocked_by": blocked_by,
        "reporters": reporters,
    }

# --- Additional helpers can be added here as needed ---

def make_markdown_table(headers, rows):
    """
    Generate a Markdown table from headers and rows.
    Args:
        headers (list): List of column headers.
        rows (list of lists): Table rows.
    Returns:
        str: Markdown table as a string.
    """
    header_line = '| ' + ' | '.join(headers) + ' |'
    separator = '| ' + ' | '.join(['---'] * len(headers)) + ' |'
    row_lines = ['| ' + ' | '.join(str(cell) for cell in row) + ' |' for row in rows]
    return '\n'.join([header_line, separator] + row_lines)

def make_summary_section(stats):
    """
    Generate a Markdown summary section from stats dict (as returned by aggregate_issue_stats).
    Args:
        stats (dict): Aggregated stats.
    Returns:
        str: Markdown summary section.
    """
    lines = [f"**Total issues:** {stats.get('total', 0)}"]
    if 'created' in stats and 'resolved' in stats:
        lines.append(f"**Created in period:** {stats['created']}")
        lines.append(f"**Resolved in period:** {stats['resolved']}")
        lines.append(f"**Resolved/Created ratio:** {stats['created_vs_resolved']}")
    if 'oldest' in stats and stats['oldest'] != 'N/A':
        lines.append(f"**Oldest unresolved:** {stats['oldest']}")
    if 'avg_unresolved_age' in stats and stats['avg_unresolved_age'] != 'N/A':
        lines.append(f"**Avg unresolved age:** {stats['avg_unresolved_age']}")
    if 'med_unresolved_age' in stats and stats['med_unresolved_age'] != 'N/A':
        lines.append(f"**Median unresolved age:** {stats['med_unresolved_age']}")
    if 'age_buckets' in stats:
        ab = stats['age_buckets']
        lines.append(f"**Unresolved age buckets:** >30d: {ab['30d']}, >60d: {ab['60d']}, >90d: {ab['90d']}")
    return '\n'.join(lines)

def make_top_n_list(items, title, n=5):
    """
    Generate a Markdown section for the top N items (e.g., assignees, reporters).
    Args:
        items (list of tuples): List of (name, count) tuples.
        title (str): Section title.
        n (int): Number of top items to include.
    Returns:
        str: Markdown section as a string.
    """
    section = f"## {title}\n"
    for name, count in items[:n]:
        section += f"- {name}: {count}\n"
    return section

def make_breakdown_section(breakdown_dict, title):
    """
    Generate a Markdown section for a breakdown (e.g., status/type/priority).
    Args:
        breakdown_dict (dict): Mapping from key to count.
        title (str): Section title.
    Returns:
        str: Markdown section as a string.
    """
    section = f"### {title}\n"
    for key, value in breakdown_dict.items():
        section += f"- {key}: {value}\n"
    return section

def make_reporter_section(reporters_dict, title="Top Reporters"):
    """
    Generate a Markdown section for reporters.
    Args:
        reporters_dict (dict): Mapping from reporter name to count.
        title (str): Section title.
    Returns:
        str: Markdown section as a string.
    """
    section = f"## {title}\n"
    for reporter, count in sorted(reporters_dict.items(), key=lambda item: -item[1]):
        section += f"- {reporter}: {count}\n"
    return section

def group_issues_by_field(issues, field_path, default_label="Other"):
    """
    Group issues by a field path (list of keys). Returns a dict of group_label -> list of issues.
    Args:
        issues (list): List of Jira issues.
        field_path (list): List of keys to traverse in each issue dict.
        default_label (str): Label for issues missing the field.
    Returns:
        dict: {group_label: [issues]}
    """
    from collections import defaultdict
    def get_field(issue, field_path, default):
        current_value = issue
        for key in field_path:
            if isinstance(current_value, dict):
                current_value = current_value.get(key, default)
            else:
                return default
        return current_value if current_value is not None else default
    grouped = defaultdict(list)
    for issue in issues:
        label = get_field(issue, field_path, default_label)
        grouped[label].append(issue)
    return dict(grouped)

def build_report_sections(sections: dict) -> str:
    """
    Build a Markdown report from a dict of named sections. Only includes sections that are present.
    Args:
        sections (dict): Keys are section names (header, toc, summary, action_items, top_n, breakdowns, grouped_sections, metadata, glossary, next_steps, etc.), values are Markdown strings.
    Returns:
        str: Full Markdown report.
    """
    order = [
        'header',
        'toc',
        'summary',
        'action_items',
        'top_n',
        'breakdowns',
        'related_links',
        'grouped_sections',
        'next_steps',
        'metadata',
        'glossary',
    ]
    out = []
    for key in order:
        val = sections.get(key)
        if val:
            out.append(val.strip())
    # Add any extra sections not in the default order
    for key, val in sections.items():
        if key not in order and val:
            out.append(val.strip())
    return '\n\n---\n\n'.join(out) 