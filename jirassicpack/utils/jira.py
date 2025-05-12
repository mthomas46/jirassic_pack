import questionary
from typing import Any, Dict, Optional, Tuple, List
import os
from jirassicpack.utils.io import info

# Module-level cache for Jira users
_CACHED_JIRA_USERS = None

def select_jira_user(jira, allow_multiple: bool = False, default_user: Optional[str] = None) -> Any:
    """
    Select one or more Jira users via interactive prompt.
    Returns (label, user_obj) tuple or list of such tuples if allow_multiple=True.
    """
    global _CACHED_JIRA_USERS
    users = []
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
        return ('', None)
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

def get_valid_project_key(jira) -> Optional[str]:
    """
    Prompt the user to select a Jira project key, or enter manually if not found.
    """
    try:
        projects = jira.get('project')
        project_keys = [p['key'] for p in projects]
        return questionary.select(
            "Select a Jira Project:",
            choices=project_keys
        ).ask()
    except Exception:
        return questionary.text('Enter Jira Project Key:').ask()

def get_valid_issue_type(jira, project_key: str) -> Optional[str]:
    """
    Prompt the user to select an issue type for a given project, or enter manually if not found.
    """
    try:
        meta = jira.get(f'issue/createmeta?projectKeys={project_key}')
        types = meta['projects'][0]['issuetypes']
        return questionary.select(
            "Select Issue Type:",
            choices=[t['name'] for t in types]
        ).ask()
    except Exception:
        return questionary.text('Enter Issue Type:').ask()

def get_valid_user(jira) -> Optional[str]:
    """
    Prompt the user to select a user, or enter manually if not found.
    """
    try:
        users = jira.search_users("")
        user_choices = [f"{u.get('displayName','?')} <{u.get('emailAddress','?')}>" for u in users]
        return questionary.select(
            "Select User:",
            choices=user_choices
        ).ask()
    except Exception:
        return questionary.text('Enter user email or username:').ask()

def get_valid_field(jira, project_key: str, issue_type: str) -> Optional[str]:
    """
    Prompt the user to select a field, or enter manually if not found.
    """
    try:
        fields = jira.get('field')
        field_names = [f['name'] for f in fields if f.get('name')]
        return questionary.select(
            "Select Field:",
            choices=field_names
        ).ask()
    except Exception:
        return questionary.text('Enter field name:').ask()

def get_valid_transition(jira, issue_key: str) -> Optional[str]:
    """
    Prompt the user to select a transition, or enter manually if not found.
    """
    try:
        transitions = jira.get(f'issue/{issue_key}/transitions')
        choices = [t['name'] for t in transitions.get('transitions',[])]
        return questionary.select(
            "Select Transition:",
            choices=choices
        ).ask()
    except Exception:
        return questionary.text('Enter transition name:').ask()

def select_account_id(jira) -> Optional[str]:
    """
    Use select_jira_user to select a user and return their accountId.
    """
    label, user_obj = select_jira_user(jira)
    return user_obj.get('accountId') if user_obj else None

def select_property_key(jira, account_id: str) -> Optional[str]:
    """
    Prompt the user to select a property key for the given accountId, or enter manually if none are found.
    """
    try:
        resp = jira.get('user/properties', params={'accountId': account_id})
        keys = resp.get('keys', [])
        if not keys:
            return questionary.text("Enter property key:").ask()
        choices = [k.get('key') for k in keys]
        choices.append("(Enter manually)")
        picked = questionary.select("Select a property key:", choices=choices).ask()
        if picked == "(Enter manually)":
            return questionary.text("Enter property key:").ask()
        return picked
    except Exception:
        return questionary.text("Enter property key:").ask()

def search_issues(jira) -> Optional[Tuple[str, Any]]:
    """
    Prompt the user to search for a Jira issue by key or summary and select from the list, or enter manually if not found. Caches issues per search term.
    """
    issue_cache = {}
    while True:
        search_term = questionary.text("Enter issue key or summary to search (leave blank if you don't know):").ask()
        if not search_term:
            action = questionary.select(
                "You didn't enter an issue key or summary. What would you like to do?",
                choices=["Search for an issue", "Enter issue key manually", "Abort"]
            ).ask()
            if action == "Enter issue key manually":
                return questionary.text("Enter issue key:").ask(), None
            elif action == "Abort":
                return None, None
            search_term = questionary.text("Enter search term for issues (summary or key):").ask()
            if not search_term:
                continue
        if search_term in issue_cache:
            issues = issue_cache[search_term]
        else:
            jql = f"summary ~ '{search_term}' OR key = '{search_term}'"
            try:
                issues = jira.search_issues(jql, fields=["key", "summary"], max_results=20)
                issue_cache[search_term] = issues
            except Exception as e:
                info(f"Error searching issues: {e}")
                continue
        if not issues:
            info("No issues found. Try again or leave blank to enter manually.")
            continue
        issues = sorted(issues, key=lambda i: i.get('key', ''))
        choices = [f"{i.get('key','?')}: {i.get('fields',{}).get('summary','?')}" for i in issues]
        choices.append("(Enter manually)")
        picked = questionary.select("Select an issue:", choices=choices).ask()
        if picked == "(Enter manually)":
            return questionary.text("Enter issue key:").ask(), None
        return picked.split(':')[0] if picked else None, next((i for i in issues if f"{i.get('key','?')}: {i.get('fields',{}).get('summary','?')}" == picked), None)

# Add get_valid_project_key, get_valid_issue_type, get_valid_user, get_valid_field, get_valid_transition, select_account_id, select_property_key, search_issues here as well, with docstrings and type hints. 