# time_tracking_worklogs.py
# This feature summarizes worklogs for a given Jira user and timeframe.
# It prompts for user, start/end dates, fetches issues with worklogs, and outputs a Markdown report with worklog details per issue.

from jirassicpack.utils_shared import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, redact_sensitive
from jirassicpack.utils import prompt_with_validation, validate_required, validate_date, error, info, spinner, info_spared_no_expense, safe_get, build_context, write_markdown_file, require_param, render_markdown_report, contextual_log, get_option
from datetime import datetime
from typing import Any, Dict, List
import time
import questionary
import os

# Module-level cache for Jira users
_CACHED_JIRA_USERS = None

def select_jira_user(jira, allow_multiple=False, default_user=None):
    """
    Reusable helper for selecting a Jira user via submenu:
    - In single-user mode (allow_multiple=False): select one user and return immediately.
    - In multi-user mode: allow selecting multiple users, return list.
    Returns a single (label, user_obj) tuple or list of such tuples if allow_multiple=True.
    """
    global _CACHED_JIRA_USERS
    users = []
    # Fetch all users with pagination, but only once
    if _CACHED_JIRA_USERS is None:
        all_jira_users = []
        start_at = 0
        max_results = 1000
        while True:
            batch = jira.search_users("", start_at=start_at, max_results=max_results)
            if not batch:
                break
            all_jira_users.extend(batch)
            if len(batch) < max_results:
                break
            start_at += max_results
        _CACHED_JIRA_USERS = all_jira_users
    else:
        all_jira_users = _CACHED_JIRA_USERS
    filtered_users = [u for u in all_jira_users if u.get('emailAddress')]
    user_choices = sorted([
        (f"{u.get('displayName','?')} <{u.get('emailAddress','?')}>", u)
        for u in filtered_users
    ], key=lambda x: x[0])
    # Single-user mode
    if not allow_multiple:
        while True:
            method = questionary.select(
                "How would you like to select the user?",
                choices=[
                    "Search for a user",
                    "Pick from list",
                    "Use current user",
                    "Abort"
                ],
                default="Pick from list"
            ).ask()
            if method == "Search for a user":
                search_term = questionary.text("Enter name or email to search:").ask()
                matches = [
                    (f"{u.get('displayName','?')} <{u.get('emailAddress','?')}>", u)
                    for u in filtered_users
                    if search_term.lower() in (u.get('displayName','').lower() + u.get('emailAddress','').lower())
                ]
                if not matches:
                    info("No users found matching your search.")
                    continue
                picked_label = questionary.select("Select a user:", choices=[m[0] for m in matches] + ["(Cancel)"]).ask()
                if picked_label == "(Cancel)":
                    continue
                picked = next((m for m in matches if m[0] == picked_label), None)
                if picked:
                    return picked
            elif method == "Pick from list":
                picked_label = questionary.select("Select a user:", choices=[c[0] for c in user_choices] + ["(Cancel)"]).ask()
                if picked_label == "(Cancel)":
                    continue
                picked = next((c for c in user_choices if c[0] == picked_label), None)
                if picked:
                    return picked
            elif method == "Use current user":
                try:
                    me = jira.get_current_user()
                    current_user = (f"{me.get('displayName','?')} <{me.get('emailAddress','?')}>", me)
                    info(f"Added current user: {current_user[0]}")
                    return current_user
                except Exception:
                    info("Could not retrieve current user from Jira.")
            elif method == "Abort":
                info("Aborted user selection.")
                return ('', None)
        # Defensive fallback
        return ('', None)
    # Multi-user mode
    while True:
        if users:
            info(f"Currently selected user(s):\n- " + "\n- ".join([u[0] for u in users]))
        method = questionary.select(
            "How would you like to select users? (multi-select mode)",
            choices=[
                "Search for a user",
                "Pick from list",
                "Use current user",
                "Clear selected",
                "Done",
                "Abort"
            ],
            default="Pick from list"
        ).ask()
        if method == "Search for a user":
            search_term = questionary.text("Enter name or email to search:").ask()
            matches = [
                (f"{u.get('displayName','?')} <{u.get('emailAddress','?')}>", u)
                for u in filtered_users
                if search_term.lower() in (u.get('displayName','').lower() + u.get('emailAddress','').lower())
            ]
            if not matches:
                info("No users found matching your search.")
                continue
            picked_label = questionary.select("Select a user:", choices=[m[0] for m in matches] + ["(Cancel)"]).ask()
            if picked_label == "(Cancel)":
                continue
            picked = next((m for m in matches if m[0] == picked_label), None)
            if picked and picked not in users:
                users.append(picked)
        elif method == "Pick from list":
            picked_label = questionary.select("Select a user:", choices=[c[0] for c in user_choices] + ["(Done)"]).ask()
            if picked_label == "(Done)":
                break
            picked = next((c for c in user_choices if c[0] == picked_label), None)
            if picked and picked not in users:
                users.append(picked)
        elif method == "Use current user":
            try:
                me = jira.get_current_user()
                current_user = (f"{me.get('displayName','?')} <{me.get('emailAddress','?')}>", me)
                if current_user not in users:
                    users.append(current_user)
                info(f"Added current user: {current_user[0]}")
            except Exception:
                info("Could not retrieve current user from Jira.")
        elif method == "Clear selected":
            users.clear()
            info("Cleared selected user(s).")
        elif method == "Abort":
            info("Aborted user selection.")
            return []
        else:  # Done
            break
    return users

def prompt_time_tracking_options(opts: Dict[str, Any], jira=None) -> Dict[str, Any]:
    """
    Prompt for time tracking options using Jira-aware helpers for user selection.
    Always prompt for user, using config/environment value as default.
    """
    config_user = opts.get('user') or os.environ.get('JIRA_USER')
    user_obj = None
    if jira:
        info("Please select a Jira user for time tracking and worklogs.")
        label, user_obj = select_jira_user(jira, default_user=config_user)
        usr = user_obj.get('accountId') if user_obj else ''
        if not usr:
            info("Aborted user selection for time tracking and worklogs.")
            return None
    else:
        usr = get_option(opts, 'user', prompt="Jira Username for worklogs:", default=config_user, required=True)
    start = get_option(opts, 'start_date', prompt="Start date (YYYY-MM-DD):", default='2024-01-01', required=True, validate=validate_date)
    end = get_option(opts, 'end_date', prompt="End date (YYYY-MM-DD):", default='2024-01-31', required=True, validate=validate_date)
    out_dir = get_option(opts, 'output_dir', default='output')
    suffix = opts.get('unique_suffix', '')
    return {
        'user': usr,
        'start_date': start,
        'end_date': end,
        'output_dir': out_dir,
        'unique_suffix': suffix
    }

def write_worklog_summary_file(filename: str, user: str, start_date: str, end_date: str, issues: list, user_email=None, batch_index=None, unique_suffix=None, context=None) -> None:
    try:
        summary_section = f"**User:** {user}\n\n**Timeframe:** {start_date} to {end_date}\n\n**Total Issues with Worklogs:** {len(issues)}"
        details_section = ""
        for issue in issues:
            key = issue.get('key', 'N/A')
            summary = safe_get(issue, ['fields', 'summary'], 'N/A')
            worklogs = safe_get(issue, ['fields', 'worklog', 'worklogs'], [])
            details_section += f"\n### {key}: {summary}\n"
            if not worklogs:
                details_section += "No worklogs found.\n"
            for wl in worklogs:
                author = safe_get(wl, ['author', 'displayName'], 'Unknown')
                started = safe_get(wl, ['started'], 'N/A')
                time_spent = safe_get(wl, ['timeSpent'], 'N/A')
                details_section += f"- {author}: {time_spent} on {started}\n"
        content = render_markdown_report(
            feature="time_tracking_worklogs",
            user=user_email,
            batch=batch_index,
            suffix=unique_suffix,
            feature_title="Time Tracking & Worklogs",
            summary_section=summary_section,
            main_content_section=details_section
        )
        with open(filename, 'w') as f:
            f.write(content)
        info(f"⏳ Worklog summary written to {filename}", extra=context)
    except Exception as e:
        error(f"Failed to write worklog summary file: {e}", extra=context)

def generate_worklog_summary(issues: List[Dict[str, Any]], start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    Filter worklogs in issues by date range. Returns filtered issues with worklogs in range.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    filtered_issues = []
    for issue in issues:
        fields = issue.get('fields', {})
        filtered_worklogs = []
        for wl in fields.get('worklog', {}).get('worklogs', []):
            wl_date = wl.get('started', '')[:10]
            try:
                wl_dt = datetime.strptime(wl_date, "%Y-%m-%d")
                if start <= wl_dt <= end:
                    filtered_worklogs.append(wl)
            except Exception:
                continue
        if filtered_worklogs:
            filtered_issue = dict(issue)
            filtered_issue['fields'] = dict(fields)
            filtered_issue['fields']['worklog'] = {'worklogs': filtered_worklogs}
            filtered_issues.append(filtered_issue)
    return filtered_issues

def time_tracking_worklogs(jira: Any, params: Dict[str, Any], user_email=None, batch_index=None, unique_suffix=None) -> None:
    correlation_id = params.get('correlation_id')
    context = build_context("time_tracking_worklogs", user_email, batch_index, unique_suffix, correlation_id=correlation_id)
    start_time = time.time()
    try:
        contextual_log('info', f"⏳ [time_tracking_worklogs] Feature entry | User: {user_email} | Params: {redact_sensitive(params)} | Suffix: {unique_suffix}", operation="feature_start", params=redact_sensitive(params), status="started", extra=context, feature='time_tracking_worklogs')
        if not require_param(params, 'user', context):
            return
        if not require_param(params, 'start_date', context):
            return
        if not require_param(params, 'end_date', context):
            return
        user = params.get('user')
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        output_dir = params.get('output_dir', 'output')
        unique_suffix = params.get('unique_suffix', '')
        ensure_output_dir(output_dir)
        orig_get = getattr(jira, 'get', None)
        if orig_get:
            def log_get(*args, **kwargs):
                contextual_log('debug', f"Jira GET: args={args}, kwargs={redact_sensitive(kwargs)}", extra=context, feature='time_tracking_worklogs')
                resp = orig_get(*args, **kwargs)
                contextual_log('debug', f"Jira GET response: {resp}", extra=context, feature='time_tracking_worklogs')
                return resp
            jira.get = log_get
        jql = (
            f"worklogAuthor = '{user}' "
            f"AND worklogDate >= '{start_date}' "
            f"AND worklogDate <= '{end_date}'"
        )
        def do_worklogs():
            with spinner("⏳ Running Time Tracking Worklogs..."):
                issues = jira.search_issues(jql, fields=["worklog", "key", "summary"], max_results=100)
                return generate_worklog_summary(issues, start_date, end_date)
        filtered_issues = retry_or_skip("Generating worklog summary from Jira issues", do_worklogs)
        if not filtered_issues:
            info("🦖 See, Nobody Cares. No worklogs found.", extra={**context, "feature": "time_tracking_worklogs"})
            return
        filename = f"{output_dir}/worklog_summary{unique_suffix}.md"
        write_worklog_summary_file(filename, user, start_date, end_date, filtered_issues, user_email, batch_index, unique_suffix, context)
        celebrate_success()
        info_spared_no_expense()
        duration = int((time.time() - start_time) * 1000)
        contextual_log('info', f"⏳ [time_tracking_worklogs] Feature complete | Suffix: {unique_suffix}", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(params), extra=context, feature='time_tracking_worklogs')
    except KeyboardInterrupt:
        contextual_log('warning', "[time_tracking_worklogs] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=redact_sensitive(params), extra=context, feature='time_tracking_worklogs')
        info("Graceful exit from Time Tracking Worklogs feature.", extra={**context, "feature": "time_tracking_worklogs"})
    except Exception as e:
        contextual_log('error', f"[time_tracking_worklogs] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context, feature='time_tracking_worklogs')
        error(f"[time_tracking_worklogs] Exception: {e}", extra={**context, "feature": "time_tracking_worklogs"})
        raise 