import questionary
from typing import Any, Dict, Optional, Tuple, List
import os
from jirassicpack.utils.io import info, prompt_text, prompt_select, prompt_password, prompt_checkbox, prompt_path, get_validated_input, select_with_pagination_and_fuzzy
from datetime import datetime
from jirassicpack.utils.logging import contextual_log
from jirassicpack.utils.io import pretty_print_result
from rich.table import Table
from rich.console import Console
from jirassicpack.utils.rich_prompt import panel_objects_in_mirror, panel_clever_girl, panel_hold_onto_your_butts

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
            method = prompt_select(
                "How would you like to select the user?",
                choices=[
                    "Search for a user",
                    "Pick from list",
                    "Use current user",
                    "Abort"
                ],
                default="Pick from list"
            )
            if method == "Search for a user":
                search_term = prompt_text("Enter name or email to search:")
                # Live query Jira for the search term
                matches_batch = jira.search_users(query=search_term, max_results=100)
                matches = [
                    (f"{u.get('displayName','?')} <{u.get('emailAddress','?')}>", u)
                    for u in matches_batch if u.get('emailAddress')
                ]
                if not matches:
                    info("No users found matching your search.")
                    continue
                picked_label = select_with_pagination_and_fuzzy([m[0] for m in matches], message="Select a user:")
                if not picked_label:
                    continue
                picked = next((m for m in matches if m[0] == picked_label), None)
                if picked:
                    return picked
            elif method == "Pick from list":
                picked_label = select_with_pagination_and_fuzzy([c[0] for c in user_choices], message="Select a user:")
                if not picked_label:
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
        method = prompt_select(
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
        )
        if method == "Search for a user":
            search_term = prompt_text("Enter name or email to search:")
            # Live query Jira for the search term
            matches_batch = jira.search_users(query=search_term, max_results=100)
            matches = [
                (f"{u.get('displayName','?')} <{u.get('emailAddress','?')}>", u)
                for u in matches_batch if u.get('emailAddress')
            ]
            if not matches:
                info("No users found matching your search.")
                continue
            picked_label = select_with_pagination_and_fuzzy([m[0] for m in matches], message="Select a user:")
            if not picked_label:
                continue
            picked = next((m for m in matches if m[0] == picked_label), None)
            if picked and picked not in users:
                users.append(picked)
        elif method == "Pick from list":
            picked_label = select_with_pagination_and_fuzzy([c[0] for c in user_choices], message="Select a user:")
            if not picked_label:
                continue
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

def get_valid_project_key(jira):
    try:
        projects = jira.get('project')
        project_keys = [p['key'] for p in projects]
        result = select_with_pagination_and_fuzzy(project_keys, message="Select a Jira Project:")
        if isinstance(result, str) and len(project_keys) > 30:
            panel_hold_onto_your_butts()
        return result
    except Exception:
        return get_validated_input('Enter Jira Project Key:', regex=r'^[A-Z][A-Z0-9]+$', error_msg='Invalid project key format.')

def get_valid_issue_type(jira, project_key):
    try:
        meta = jira.get(f'issue/createmeta?projectKeys={project_key}')
        types = meta['projects'][0]['issuetypes']
        choices = [t['name'] for t in types]
        result = select_with_pagination_and_fuzzy(choices, message="Select Issue Type:")
        if isinstance(result, str) and len(choices) > 30:
            panel_clever_girl()
        return result
    except Exception:
        return get_validated_input('Enter Issue Type:', error_msg='Invalid issue type.')

def get_valid_user(jira):
    try:
        users = jira.search_users("")
        user_choices = [f"{u.get('displayName','?')} <{u.get('emailAddress','?')}>" for u in users]
        result = select_with_pagination_and_fuzzy(user_choices, message="Select User:")
        if isinstance(result, str) and len(user_choices) > 30:
            panel_clever_girl()
        return result
    except Exception:
        return get_validated_input('Enter user email or username:', regex=r'^[^@\s]+@[^@\s]+\.[^@\s]+$', error_msg='Invalid email format.')

def get_valid_field(jira, project_key, issue_type):
    try:
        fields = jira.get('field')
        field_names = [f['name'] for f in fields if f.get('name')]
        result = select_with_pagination_and_fuzzy(field_names, message="Select Field:")
        if isinstance(result, str) and len(field_names) > 30:
            panel_hold_onto_your_butts()
        return result
    except Exception:
        return get_validated_input('Enter field name:', error_msg='Invalid field name.')

def get_valid_transition(jira, issue_key):
    try:
        transitions = jira.get(f'issue/{issue_key}/transitions')
        choices = [t['name'] for t in transitions.get('transitions',[])]
        result = select_with_pagination_and_fuzzy(choices, message="Select Transition:")
        if isinstance(result, str) and len(choices) > 30:
            panel_clever_girl()
        return result
    except Exception:
        return get_validated_input('Enter transition name:', error_msg='Invalid transition.')

def select_account_id(jira):
    label, user_obj = select_jira_user(jira)
    return user_obj.get('accountId') if user_obj else None

def select_property_key(jira, account_id):
    try:
        resp = jira.get('user/properties', params={'accountId': account_id})
        keys = resp.get('keys', [])
        if not keys:
            return prompt_text("Enter property key:")
        choices = [k.get('key') for k in keys]
        choices.append("(Enter manually)")
        result = select_with_pagination_and_fuzzy(choices, message="Select a property key:")
        if result == "(Enter manually)":
            return prompt_text("Enter property key:")
        if isinstance(result, str) and len(choices) > 30:
            panel_hold_onto_your_butts()
        return result
    except Exception:
        return prompt_text("Enter property key:")

def search_issues(jira):
    """
    Interactive submenu for searching issues:
    1. Search by summary or key
    2. Enter issue key manually
    3. List all issues
    4. List my issues
    5. List recently updated
    6. Search by reporter
    7. Search by assignee
    8. Search by status
    9. Search by label
    10. Search by project
    11. Abort
    Displays a table/list of results. Optionally, lets the user select one for details.
    """
    def print_issues(issues):
        if not issues:
            info("No issues found. Try again or use another option.")
            return
        console = Console()
        table = Table(title="Search Results", show_lines=True)
        table.add_column("#", style="cyan", no_wrap=True)
        table.add_column("Key", style="magenta")
        table.add_column("Summary", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("Assignee", style="blue")
        for i, issue in enumerate(issues, 1):
            key = issue.get('key', '?')
            summary = issue.get('fields', {}).get('summary', '?')
            status = issue.get('fields', {}).get('status', {}).get('name', '?')
            assignee = issue.get('fields', {}).get('assignee', {}).get('displayName', 'Unassigned')
            table.add_row(str(i), key, summary, status, assignee)
        console.print(table)
        if len(issues) > 10:
            panel_objects_in_mirror()

    while True:
        action = prompt_select(
            "How would you like to search for an issue?",
            choices=[
                "Search by summary or key",
                "Enter issue key manually",
                "List all issues",
                "List my issues",
                "List recently updated",
                "Search by reporter",
                "Search by assignee",
                "Search by status",
                "Search by label",
                "Search by project",
                "Abort"
            ]
        )
        if action == "Abort":
            return None
        elif action == "Enter issue key manually":
            issue_key = prompt_text("Enter issue key:")
            if not issue_key:
                continue
            issue = jira.get_task(issue_key)
            pretty_print_result(issue)
            continue
        elif action == "Search by summary or key":
            search_term = prompt_text("Enter search term (summary or key):")
            if not search_term:
                continue
            try:
                issues = jira.search_issues(f"summary ~ '{search_term}' OR key = '{search_term}'", fields=["key", "summary", "status", "assignee", "comment"], max_results=20)
            except Exception as e:
                info(f"Error searching issues: {e}")
                continue
            print_issues(issues)
            continue
        elif action == "List all issues":
            try:
                issues = jira.search_issues('ORDER BY updated DESC', fields=["key", "summary", "status", "assignee", "comment"], max_results=20)
            except Exception as e:
                info(f"Error listing all issues: {e}")
                continue
            print_issues(issues)
            continue
        elif action == "List my issues":
            try:
                issues = jira.search_issues('assignee = currentUser() ORDER BY updated DESC', fields=["key", "summary", "status", "assignee", "comment"], max_results=20)
            except Exception as e:
                info(f"Error listing my issues: {e}")
                continue
            print_issues(issues)
            continue
        elif action == "List recently updated":
            try:
                issues = jira.search_issues('ORDER BY updated DESC', fields=["key", "summary", "status", "assignee", "comment"], max_results=20)
            except Exception as e:
                info(f"Error listing recently updated issues: {e}")
                continue
            print_issues(issues)
            continue
        elif action == "Search by reporter":
            reporter = prompt_text("Enter reporter username or email:")
            if not reporter:
                continue
            try:
                issues = jira.search_issues(f'reporter = "{reporter}" ORDER BY updated DESC', fields=["key", "summary", "status", "assignee", "comment"], max_results=20)
            except Exception as e:
                info(f"Error searching by reporter: {e}")
                continue
            print_issues(issues)
            continue
        elif action == "Search by assignee":
            assignee = prompt_text("Enter assignee username or email:")
            if not assignee:
                continue
            try:
                issues = jira.search_issues(f'assignee = "{assignee}" ORDER BY updated DESC', fields=["key", "summary", "status", "assignee", "comment"], max_results=20)
            except Exception as e:
                info(f"Error searching by assignee: {e}")
                continue
            print_issues(issues)
            continue
        elif action == "Search by status":
            status = prompt_text("Enter status (e.g., 'To Do', 'In Progress', 'Done'):")
            if not status:
                continue
            try:
                issues = jira.search_issues(f'status = "{status}" ORDER BY updated DESC', fields=["key", "summary", "status", "assignee", "comment"], max_results=20)
            except Exception as e:
                info(f"Error searching by status: {e}")
                continue
            print_issues(issues)
            continue
        elif action == "Search by label":
            label = prompt_text("Enter label:")
            if not label:
                continue
            try:
                issues = jira.search_issues(f'labels = "{label}" ORDER BY updated DESC', fields=["key", "summary", "status", "assignee", "comment"], max_results=20)
            except Exception as e:
                info(f"Error searching by label: {e}")
                continue
            print_issues(issues)
            continue
        elif action == "Search by project":
            project = prompt_text("Enter project key:")
            if not project:
                continue
            try:
                issues = jira.search_issues(f'project = "{project}" ORDER BY updated DESC', fields=["key", "summary", "status", "assignee", "comment"], max_results=20)
            except Exception as e:
                info(f"Error searching by project: {e}")
                continue
            print_issues(issues)
            continue

def select_board_name(jira):
    """
    Prompt the user to select a Jira board via submenu:
    - Enter board name to search
    - Enter manually
    - Pick from list
    Returns the selected board name.
    """
    while True:
        method = prompt_select(
            "How would you like to select a board?",
            choices=[
                "Enter board name to search",
                "Pick from list",
                "Enter manually",
                "Abort"
            ],
            default="Pick from list"
        )
        if method == "Enter board name to search":
            search_term = prompt_text("Enter board name to search:")
            if not search_term:
                continue
            boards = jira.list_boards(name=search_term)
            if not boards:
                print("No boards found matching your search.")
                continue
            boards = sorted(boards, key=lambda b: (b.get('name') or '').lower())
            choices = [f"{b.get('name','?')} (ID: {b.get('id','?')}, Type: {b.get('type','?')})" for b in boards]
            picked = select_with_pagination_and_fuzzy(choices, message="Select a board:")
            if not picked:
                continue
            for b in boards:
                label = f"{b.get('name','?')} (ID: {b.get('id','?')}, Type: {b.get('type','?')})"
                if picked == label:
                    return b.get('name')
        elif method == "Pick from list":
            boards = jira.list_boards()
            if not boards:
                print("No boards found in Jira.")
                continue
            boards = sorted(boards, key=lambda b: (b.get('name') or '').lower())
            choices = [f"{b.get('name','?')} (ID: {b.get('id','?')}, Type: {b.get('type','?')})" for b in boards]
            picked = select_with_pagination_and_fuzzy(choices, message="Select a board:")
            if not picked:
                continue
            for b in boards:
                label = f"{b.get('name','?')} (ID: {b.get('id','?')}, Type: {b.get('type','?')})"
                if picked == label:
                    return b.get('name')
        elif method == "Enter manually":
            return prompt_text("Enter board name:")
        else:  # Abort
            return None

def select_sprint_name(jira, board_name=None, board_id=None):
    """
    Prompt the user to select a sprint via submenu:
    - Enter sprint name to search
    - Enter manually
    - Pick from list
    Handles boards that do not support sprints (e.g., Kanban) gracefully.
    Returns the selected sprint name.
    Accepts board_id directly if available, otherwise looks up by board_name.
    """
    import requests
    if not board_id:
        if not board_name:
            board_name = prompt_text("Enter board name:")
        boards = jira.list_boards(name=board_name)
        board_id = None
        for b in boards:
            if b.get('name') == board_name:
                board_id = b.get('id')
                break
        if not board_id:
            print(f"No board found with name '{board_name}'.")
            return prompt_text("Enter sprint name:")
    while True:
        method = prompt_select(
            "How would you like to select a sprint?",
            choices=[
                "Enter sprint name to search",
                "Pick from list",
                "Enter manually",
                "Abort"
            ],
            default="Pick from list"
        )
        if method == "Enter sprint name to search":
            search_term = prompt_text("Enter sprint name to search:")
            if not search_term:
                continue
            try:
                sprints = jira.list_sprints(board_id)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 400:
                    print("This board does not support sprints (likely a Kanban board) or you do not have permission. Aborting.")
                    return None
                else:
                    print(f"Error fetching sprints: {e}")
                    return None
            except Exception as e:
                print(f"Error fetching sprints: {e}")
                return None
            sprints = [s for s in sprints if search_term.lower() in s.get('name','').lower()]
            if not sprints:
                print("No sprints match your search.")
                continue
            choices = [f"{s.get('name','?')} (ID: {s.get('id','?')}, State: {s.get('state','?')})" for s in sprints]
            picked = select_with_pagination_and_fuzzy(choices, message="Select a sprint:")
            if not picked:
                continue
            for s in sprints:
                label = f"{s.get('name','?')} (ID: {s.get('id','?')}, State: {s.get('state','?')})"
                if picked == label:
                    return s.get('name')
        elif method == "Pick from list":
            try:
                sprints = jira.list_sprints(board_id)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 400:
                    print("This board does not support sprints (likely a Kanban board) or you do not have permission. Aborting.")
                    return None
                else:
                    print(f"Error fetching sprints: {e}")
                    return None
            except Exception as e:
                print(f"Error fetching sprints: {e}")
                return None
            if not sprints:
                print("No sprints found for this board.")
                continue
            choices = [f"{s.get('name','?')} (ID: {s.get('id','?')}, State: {s.get('state','?')})" for s in sprints]
            picked = select_with_pagination_and_fuzzy(choices, message="Select a sprint:")
            if not picked:
                continue
            for s in sprints:
                label = f"{s.get('name','?')} (ID: {s.get('id','?')}, State: {s.get('state','?')})"
                if picked == label:
                    return s.get('name')
        elif method == "Enter manually":
            return prompt_text("Enter sprint name:")
        else:  # Abort
            return None

SELECT_MENU_STYLE = questionary.Style([
    ("selected", "fg:#22bb22 bold"),  # Jungle green
    ("pointer", "fg:#ffcc00 bold"),   # Yellow
])

# Add get_valid_project_key, get_valid_issue_type, get_valid_user, get_valid_field, get_valid_transition, select_account_id, select_property_key, search_issues here as well, with docstrings and type hints. 