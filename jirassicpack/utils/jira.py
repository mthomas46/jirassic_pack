"""
jirassicpack.utils.jira

All Jira API helpers, user/field/transition selectors, and interactive search utilities for the Jirassic Pack CLI. Provides robust, user-friendly selection and validation for all Jira-related CLI operations.
"""
import questionary
from jirassicpack.utils.message_utils import info
from jirassicpack.utils.prompt_utils import prompt_text, prompt_select, select_with_pagination_and_fuzzy, select_from_list, select_with_fuzzy_multiselect
from jirassicpack.utils.output_utils import pretty_print_result
from rich.table import Table
from rich.console import Console
from jirassicpack.utils.rich_prompt import panel_objects_in_mirror, panel_clever_girl, panel_hold_onto_your_butts
from questionary import Choice
import json
import os
import time

CACHE_PATH = os.path.join('output', '.jira_user_cache.json')
CACHE_TTL = 24 * 3600  # 24 hours

# Module-level cache for Jira users
_CACHED_JIRA_USERS = None

def load_user_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r') as f:
                data = json.load(f)
            if time.time() - data.get('timestamp', 0) < CACHE_TTL:
                return data.get('users', [])
        except Exception as e:
            info(f"[user cache] Failed to load cache: {e}")
    return None

def save_user_cache(users):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, 'w') as f:
        json.dump({'timestamp': time.time(), 'users': users}, f)

def refresh_user_cache(jira):
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
    save_user_cache(all_jira_users)
    global _CACHED_JIRA_USERS
    _CACHED_JIRA_USERS = all_jira_users
    info("[user cache] Refreshed user cache from Jira.")
    return all_jira_users

def clear_all_caches():
    if os.path.exists(CACHE_PATH):
        os.remove(CACHE_PATH)
        info("[user cache] Cleared user cache.")
    global _CACHED_JIRA_USERS
    _CACHED_JIRA_USERS = None

def select_jira_user(jira, allow_multiple=False, default_user=None, force_refresh=False):
    """
    Reusable helper for selecting a Jira user via submenu:
    - In single-user mode (allow_multiple=False): select one user and return immediately.
    - In multi-user mode: allow selecting multiple users, return list.
    Returns a single (label, user_obj) tuple or list of such tuples if allow_multiple=True.
    """
    global _CACHED_JIRA_USERS
    if force_refresh:
        all_jira_users = refresh_user_cache(jira)
    else:
        all_jira_users = _CACHED_JIRA_USERS or load_user_cache()
        if all_jira_users is None:
            all_jira_users = refresh_user_cache(jira)
        else:
            info("[user cache] Using cached Jira users.")
        _CACHED_JIRA_USERS = all_jira_users
    filtered_users = [u for u in all_jira_users if u.get('emailAddress')]
    user_map = {u['accountId']: u for u in filtered_users if 'accountId' in u}
    user_choices = [
        {"name": f"{u.get('displayName','?')} <{u.get('emailAddress','?')}>", "value": u['accountId']} for u in filtered_users if 'accountId' in u
    ]
    if not user_choices:
        info("No users found.")
        return None if not allow_multiple else []
    if allow_multiple:
        picked = select_with_fuzzy_multiselect(
            user_choices,
            message="Select Jira users (multi-select mode):"
        )
        if not picked:
            return []  # User aborted or cleared
        # Extract .value if Choice objects are returned
        if picked and isinstance(picked[0], Choice):
            picked = [p.value for p in picked]
        return [(user_map[val]['displayName'], user_map[val]) for val in picked] if picked else []
    else:
        picked = select_from_list(
            user_choices,
            message="Select a Jira user:",
            multi=False
        )
        # Extract .value if a Choice object is returned
        if isinstance(picked, Choice):
            picked = picked.value
        if picked:
            return (user_map[picked]['displayName'], user_map[picked])
        else:
            return ('', None)

def get_valid_project_key(jira):
    try:
        projects = jira.get('project')
        project_keys = [p['key'] for p in projects]
        result = select_with_pagination_and_fuzzy(project_keys, message="Select a Jira Project:")
        if isinstance(result, str) and len(project_keys) > 30:
            panel_hold_onto_your_butts()
        return result
    except Exception:
        # Manual fallback: prompt for project key
        return prompt_text('Enter Jira Project Key:')  # TODO: Add regex validation if needed

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
        return prompt_text('Enter Issue Type:')  # TODO: Add validation if needed

def get_valid_user(jira):
    try:
        users = jira.search_users("")
        user_choices = [f"{u.get('displayName','?')} <{u.get('emailAddress','?')}>" for u in users]
        result = select_with_pagination_and_fuzzy(user_choices, message="Select User:")
        if isinstance(result, str) and len(user_choices) > 30:
            panel_clever_girl()
        return result
    except Exception:
        return prompt_text('Enter user email or username:')  # TODO: Add email validation if needed

def get_valid_field(jira, project_key, issue_type):
    try:
        fields = jira.get('field')
        field_names = [f['name'] for f in fields if f.get('name')]
        result = select_with_pagination_and_fuzzy(field_names, message="Select Field:")
        if isinstance(result, str) and len(field_names) > 30:
            panel_hold_onto_your_butts()
        return result
    except Exception:
        return prompt_text('Enter field name:')  # TODO: Add validation if needed

def get_valid_transition(jira, issue_key):
    try:
        transitions = jira.get(f'issue/{issue_key}/transitions')
        choices = [t['name'] for t in transitions.get('transitions',[])]
        result = select_with_pagination_and_fuzzy(choices, message="Select Transition:")
        if isinstance(result, str) and len(choices) > 30:
            panel_clever_girl()
        return result
    except Exception:
        return prompt_text('Enter transition name:')  # TODO: Add validation if needed

def select_account_id(jira):
    label, user_obj = select_jira_user(jira)
    return user_obj.get('accountId') if user_obj else None

def select_property_key(jira, account_id):
    try:
        resp = jira.get('user/properties', params={'accountId': account_id})
        keys = resp.get('keys', [])
        if not keys:
            return prompt_text("Enter property key:")
        choices = [{"name": k.get('key'), "value": k.get('key')} for k in keys]
        choices.append({"name": "(Enter manually)", "value": "__manual__"})
        result = select_with_pagination_and_fuzzy(choices, message="Select a property key:")
        if result == "__manual__":
            return prompt_text("Enter property key:")
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
                {"name": "Enter board name to search", "value": "search"},
                {"name": "Pick from list", "value": "pick"},
                {"name": "Enter manually", "value": "manual"},
                {"name": "Abort", "value": "abort"}
            ],
            default="pick"
        )
        if method == "search":
            search_term = prompt_text("Enter board name to search:")
            if not search_term:
                continue
            boards = jira.list_boards(name=search_term)
            if not boards:
                print("No boards found matching your search.")
                continue
            boards = sorted(boards, key=lambda b: (b.get('name') or '').lower())
            choices = [{"name": f"{b.get('name','?')} (ID: {b.get('id','?')}, Type: {b.get('type','?')})", "value": b.get('name','?')} for b in boards]
            picked = select_with_pagination_and_fuzzy(choices, message="Select a board:")
            if not picked:
                continue
            return picked
        elif method == "pick":
            boards = jira.list_boards()
            if not boards:
                print("No boards found in Jira.")
                continue
            boards = sorted(boards, key=lambda b: (b.get('name') or '').lower())
            choices = [{"name": f"{b.get('name','?')} (ID: {b.get('id','?')}, Type: {b.get('type','?')})", "value": b.get('name','?')} for b in boards]
            picked = select_with_pagination_and_fuzzy(choices, message="Select a board:")
            if not picked:
                continue
            return picked
        elif method == "manual":
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
                {"name": "Enter sprint name to search", "value": "search"},
                {"name": "Pick from list", "value": "pick"},
                {"name": "Enter manually", "value": "manual"},
                {"name": "Abort", "value": "abort"}
            ],
            default="pick"
        )
        if method == "search":
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
            choices = [{"name": f"{s.get('name','?')} (ID: {s.get('id','?')}, State: {s.get('state','?')})", "value": s.get('name','?')} for s in sprints]
            picked = select_with_pagination_and_fuzzy(choices, message="Select a sprint:")
            if not picked:
                continue
            return picked
        elif method == "pick":
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
            choices = [{"name": f"{s.get('name','?')} (ID: {s.get('id','?')}, State: {s.get('state','?')})", "value": s.get('name','?')} for s in sprints]
            picked = select_with_pagination_and_fuzzy(choices, message="Select a sprint:")
            if not picked:
                continue
            return picked
        elif method == "manual":
            return prompt_text("Enter sprint name:")
        else:  # Abort
            return None

SELECT_MENU_STYLE = questionary.Style([
    ("selected", "fg:#22bb22 bold"),  # Jungle green
    ("pointer", "fg:#ffcc00 bold"),   # Yellow
])

# Add get_valid_project_key, get_valid_issue_type, get_valid_user, get_valid_field, get_valid_transition, select_account_id, select_property_key, search_issues here as well, with docstrings and type hints. 