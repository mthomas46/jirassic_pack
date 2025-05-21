"""
features/__init__.py

Defines the feature manifest and registry for the Jirassic Pack CLI.
Each feature is imported and registered with metadata for dynamic menu generation and dispatch.

- FEATURE_MANIFEST: List of all available features, their keys, labels, groups, and modules.
- Used by the CLI to build menus, validate features, and dispatch handlers.
"""

from .create_issue import create_issue
from .update_issue import update_issue
from .sprint_board_management import sprint_board_management
from .advanced_metrics import advanced_metrics
from .bulk_operations import bulk_operations
from .user_team_analytics import user_team_analytics
from .integration_tools import integration_tools
from . import time_tracking_worklogs as time_tracking_worklogs_mod
from .time_tracking_worklogs import time_tracking_worklogs as time_tracking_worklogs_func, prompt_worklog_options
from .automated_documentation import automated_documentation
from .deep_ticket_summary import deep_ticket_summary
from .gather_metrics import gather_metrics
from .summarize_tickets import summarize_tickets
from .github_connection_test import github_connection_test

# FEATURE_MANIFEST: List of all features with metadata for menu and dispatch
FEATURE_MANIFEST = [
    # Each entry: key, label, emoji, group, module, feature_func, description
    {"key": "create_issue", "label": "Create a new issue", "emoji": "📝", "group": "Issues & Tasks", "module": create_issue, "feature_func": create_issue, "description": "Create a new Jira issue by entering project, summary, description, and type."},
    {"key": "update_issue", "label": "Update an existing issue", "emoji": "✏️", "group": "Issues & Tasks", "module": update_issue, "feature_func": update_issue, "description": "Update a field on an existing Jira issue (e.g., status, assignee, custom fields)."},
    {"key": "bulk_operations", "label": "Bulk operations", "emoji": "🔁", "group": "Issues & Tasks", "module": bulk_operations, "feature_func": bulk_operations, "description": "Perform bulk transitions, comments, or assignments on multiple issues via JQL."},
    {"key": "user_team_analytics", "label": "User and team analytics", "emoji": "👤", "group": "Analytics & Reporting", "module": user_team_analytics, "feature_func": user_team_analytics, "description": "Analyze user/team activity, ticket stats, and generate analytics reports."},
    {"key": "integration_tools", "label": "Integration with other tools", "emoji": "🔗", "group": "Integrations & Docs", "module": integration_tools, "feature_func": integration_tools, "description": "Scan issues for GitHub/GitLab PR links and generate integration reports."},
    {"key": "time_tracking_worklogs", "label": "Time tracking and worklogs", "emoji": "⏱️", "group": "Analytics & Reporting", "module": time_tracking_worklogs_mod, "feature_func": time_tracking_worklogs_func, "description": "Summarize worklogs for a user and timeframe, with detailed Markdown output."},
    {"key": "automated_documentation", "label": "Automated documentation", "emoji": "📄", "group": "Integrations & Docs", "module": automated_documentation, "feature_func": automated_documentation, "description": "Generate release notes, changelogs, or sprint reviews from Jira issues."},
    {"key": "advanced_metrics", "label": "Advanced metrics and reporting", "emoji": "📊", "group": "Analytics & Reporting", "module": advanced_metrics, "feature_func": advanced_metrics, "description": "Generate advanced metrics, breakdowns, and top-N analytics for issues."},
    {"key": "sprint_board_management", "label": "Sprint and board management", "emoji": "📋", "group": "Boards & Sprints", "module": sprint_board_management, "feature_func": sprint_board_management, "description": "Summarize the state of a Jira board, sprints, and issues in the active sprint."},
    {"key": "deep_ticket_summary", "label": "Deep Ticket Summary (full changelog, all fields)", "emoji": "🦖", "group": "Analytics & Reporting", "module": deep_ticket_summary, "feature_func": deep_ticket_summary, "description": "Generate a full summary of a ticket, including changelog, comments, and all fields."},
    {"key": "gather_metrics", "label": "Gather metrics for a user", "emoji": "📈", "group": "Analytics & Reporting", "module": gather_metrics, "feature_func": gather_metrics, "description": "Gather and report metrics for Jira issues, including grouping by type and summary statistics."},
    {"key": "summarize_tickets", "label": "Summarize tickets", "emoji": "🗂️", "group": "Analytics & Reporting", "module": summarize_tickets, "feature_func": summarize_tickets, "description": "Generate summary reports for Jira tickets, including grouping, top assignees, and action items."},
    {"key": "github_connection_test", "label": "Test GitHub Connection", "emoji": "🐙", "group": "Integrations & Docs", "module": github_connection_test, "feature_func": github_connection_test, "description": "Test GitHub API connectivity and list branches for a repo."},
    # Add other features as needed
]

FEATURE_REGISTRY = {f["key"]: f["feature_func"] for f in FEATURE_MANIFEST}
FEATURE_MODULES = {f["key"]: f["module"] for f in FEATURE_MANIFEST}
