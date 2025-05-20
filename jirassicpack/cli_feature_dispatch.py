"""
Feature dispatch logic for Jirassic Pack CLI.
"""
# Imports
import time
import importlib
import inspect
from jirassicpack.cli_llm_server import update_llm_menu
from jirassicpack.utils.logging import contextual_log, redact_sensitive
from jirassicpack.utils.message_utils import error
from jirassicpack.features import FEATURE_REGISTRY
from jirassicpack.utils.jira import select_account_id, select_property_key, search_issues
from jirassicpack.cli_menu import prompt_text, prompt_select, prompt_checkbox

def run_feature(feature: str, jira, options: dict, user_email: str = None, batch_index: int = None, unique_suffix: str = None) -> None:
    """
    Dispatch and execute the selected feature, handling parameter gathering, logging, and error handling.
    """
    update_llm_menu()
    context = {"feature": feature, "user": user_email, "batch": batch_index, "suffix": unique_suffix}
    contextual_log('debug', f"[DEBUG] run_feature called. feature={feature}, user_email={user_email}, batch_index={batch_index}, unique_suffix={unique_suffix}, options={options}", extra=context)
    menu_to_key = {
        "🧪 Test connection to Jira": "test_connection",
        "🦖 Test Local LLM": "test_local_llm",
        "🦖 Start Local LLM Server": "start_local_llm_server",
        "👥 Output all users": "output_all_users",
        "📝 Create a new issue": "create_issue",
        "✏️ Update an existing issue": "update_issue",
        "📋 Sprint and board management": "sprint_board_management",
        "📊 Advanced metrics and reporting": "advanced_metrics",
        "🔁 Bulk operations": "bulk_operations",
        "👤 User and team analytics": "user_team_analytics",
        "🔗 Integration with other tools": "integration_tools",
        "⏱️ Time tracking and worklogs": "time_tracking_worklogs",
        "📄 Automated documentation": "automated_documentation",
        "📈 Gather metrics for a user": "gather_metrics",
        "🗂️ Summarize tickets": "summarize_tickets",
        "🧑‍💻 Get user by accountId/email": "get_user",
        "🔍 Search users": "search_users",
        "🔎 Search users by displayname and email": "search_users_by_displayname_email",
        "🏷️ Get user property": "get_user_property",
        "📋 Get task (issue)": "get_task",
        "⚙️ Get mypreferences": "get_mypreferences",
        "🙋 Get current user (myself)": "get_current_user",
        "🔍 Search logs for points of interest": "log_parser",
        "🏷️ Output all user property keys": "output_all_user_property_keys",
        "🔎 Search issues": "search_issues",
        "📄 Ticket Discussion Summary": "ticket_discussion_summary",
        "👀 Live Tail Local LLM Logs": "live_tail_local_llm_logs",
    }
    key = menu_to_key.get(feature, feature)
    context = {"feature": key, "user": user_email, "batch": batch_index, "suffix": unique_suffix}
    feature_tag = f"[{key}]"
    contextual_log('info', f"🦖 [CLI] run_feature: key={repr(key)}", extra=context)
    # Inline handlers for user features (examples, add more as needed)
    if key == "get_user":
        try:
            account_id = select_account_id(jira)
            email = None
            search_email = prompt_checkbox("Would you like to search for a user to fill in the email?", default=True)
            if search_email:
                users = jira.search_users("")
                email_choices = [u.get('emailAddress') for u in users if u.get('emailAddress')]
                if email_choices:
                    picked = prompt_select("Select an email:", choices=email_choices + ["(Enter manually)"])
                    if picked == "(Enter manually)":
                        email = prompt_text("Enter email (leave blank if not used):")
                    else:
                        email = picked
                else:
                    email = prompt_text("Enter email (leave blank if not used):")
            else:
                email = prompt_text("Enter email (leave blank if not used):")
            username = prompt_text("Username (leave blank if not used):")
            key_ = prompt_text("User key (leave blank if not used):")
            result = jira.get_user(account_id=account_id or None, email=email or None, username=username or None, key=key_ or None)
            if not result:
                print("Aborted: No user found with provided details.")
                return
            print(result)
        except Exception as e:
            error(f"🦖 Error fetching user: {e}", extra=context)
            contextual_log('error', f"🦖 [CLI] Error fetching user: {e}", exc_info=True, extra=context)
        return
    # Add more inline handlers as needed...
    # Only now check for FEATURE_REGISTRY
    if key not in FEATURE_REGISTRY:
        error(f"{feature_tag} Unknown feature: {feature}", extra=context)
        contextual_log('error', f"🦖 [CLI] Unknown feature: {feature}", exc_info=True, extra=context)
        return
    contextual_log('info', f"🦖 [CLI] Dispatching feature: {key} | Options: {redact_sensitive(options)} {context}", extra=context)
    prompt_func_name = f"prompt_{key}_options"
    prompt_func = None
    feature_module = FEATURE_REGISTRY[key]
    contextual_log('debug', f"[DEBUG] Looking for prompt function: {prompt_func_name} in {feature_module}", extra=context)
    if hasattr(feature_module, prompt_func_name):
        prompt_func = getattr(feature_module, prompt_func_name)
        contextual_log('debug', f"[DEBUG] Found prompt function: {prompt_func_name} in module {feature_module}", extra=context)
    else:
        try:
            mod = importlib.import_module(f"jirassicpack.features.{key}")
            prompt_func = getattr(mod, prompt_func_name, None)
            contextual_log('debug', f"[DEBUG] Imported module jirassicpack.features.{key}, found prompt_func: {bool(prompt_func)}", extra=context)
        except Exception as e:
            contextual_log('debug', f"[DEBUG] Could not import prompt function for {key}: {e}", extra=context)
            prompt_func = None
    if prompt_func:
        sig = inspect.signature(prompt_func)
        contextual_log('debug', f"[DEBUG] prompt_func signature: {sig}", extra=context)
        if 'jira' in sig.parameters:
            contextual_log('debug', f"[DEBUG] Calling prompt_func with jira", extra=context)
            params = prompt_func(options, jira=jira)
        else:
            contextual_log('debug', f"[DEBUG] Calling prompt_func without jira", extra=context)
            params = prompt_func(options)
        contextual_log('debug', f"[DEBUG] prompt_func returned params: {params}", extra=context)
        if not params:
            contextual_log('info', f"🦖 [CLI] Feature '{key}' cancelled or missing parameters for user {user_email}", extra=context)
            return
    else:
        contextual_log('debug', f"[DEBUG] No prompt_func found for {key}, using options as params.", extra=context)
        params = options
    start_time = time.time()
    contextual_log('info', f"🦖 [CLI] Feature '{key}' execution started for user {user_email}", operation="feature_start", params=redact_sensitive(options), extra=context)
    FEATURE_REGISTRY[key](jira, params, user_email=user_email, batch_index=batch_index, unique_suffix=unique_suffix)
    duration = int((time.time() - start_time) * 1000)
    contextual_log('info', f"🦖 [CLI] Feature '{key}' execution finished for user {user_email} in {duration}ms", operation="feature_end", status="success", duration_ms=duration, params=redact_sensitive(options), extra=context)
    contextual_log('info', f"🦖 [CLI] Feature '{key}' complete for user {user_email}", extra=context) 