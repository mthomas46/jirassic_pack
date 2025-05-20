"""
Menu and onboarding wizard logic for Jirassic Pack CLI.
"""
# Imports
import os
import sys
import importlib
from jirassicpack.features import FEATURE_MANIFEST
from jirassicpack.utils.prompt_utils import prompt_select, select_from_list, prompt_text, prompt_checkbox
from jirassicpack.utils.output_utils import rich_panel
from jirassicpack.utils.message_utils import info, error
from jirassicpack.cli_state import RECENT_FEATURES, LAST_FEATURE, LAST_REPORT_PATH, FAVORITE_FEATURES, CLI_THEME, CLI_LOG_LEVEL, save_cli_state
from jirassicpack.utils.jira import clear_all_caches, refresh_user_cache

# Reconstruct FEATURE_GROUPS for menu logic
FEATURE_GROUPS = {}
for f in FEATURE_MANIFEST:
    group = f['group']
    if group not in FEATURE_GROUPS:
        FEATURE_GROUPS[group] = []
    FEATURE_GROUPS[group].append((f["emoji"] + " " + f["label"], f["key"]))

# Onboarding wizard

def onboarding_wizard():
    rich_panel("""
🦖 Welcome to Jirassic Pack CLI!

This wizard will help you get started in under a minute.
""", title="Welcome!", style="banner")
    # Step 1: Theme
    theme = prompt_select("Choose your preferred CLI theme:", choices=["default", "light", "dark", "jurassic", "matrix"])
    global CLI_THEME
    CLI_THEME = theme
    save_cli_state()
    rich_info(f"Theme set to {theme}.")
    # Step 2: Log level
    log_level = prompt_select("Set the log verbosity:", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    global CLI_LOG_LEVEL
    CLI_LOG_LEVEL = log_level
    save_cli_state()
    rich_info(f"Log level set to {log_level}.")
    # Step 3: Tour
    rich_panel("""
Main CLI Features:
- 🦖 Modular menu: Select features by group, favorites, or search.
- ⭐ Pin favorites for quick access.
- 🗂️ Batch mode: Run multiple features in sequence.
- ⚙️ Settings: Change theme, log level, and clear history.
- 🆘 Contextual help in every menu.
- 📄 All reports saved to the output directory.
""", title="Quick Tour", style="info")
    # Step 4: Docs
    open_docs = prompt_select("Would you like to open the documentation in your browser?", choices=["Yes", "No"])
    if open_docs == "Yes":
        import webbrowser
        webbrowser.open("https://github.com/your-org/jirassicpack")
        rich_info("Opened documentation in your browser.")
    rich_success("Onboarding complete! You can rerun this wizard from Settings at any time.")

# Menu logic

def feature_menu():
    from jirassicpack.features import FEATURE_MANIFEST
    global RECENT_FEATURES, LAST_FEATURE, LAST_REPORT_PATH, FAVORITE_FEATURES, CLI_THEME, CLI_LOG_LEVEL
    group_names = ["Batch mode: Run multiple features", "Favorites", "Recently Used"] + list(FEATURE_GROUPS.keys()) + ["Help", "Settings", "Onboarding Wizard", "Exit"]
    while True:
        group_choices = group_names + ["What is this?"]
        group = prompt_select(
            "Select a feature group:",
            choices=group_choices,
            default=group_names[0]
        )
        if group == "What is this?":
            rich_info("🦖 The main menu lets you choose feature groups, access favorites, run multiple features, or change settings. Use arrow keys, numbers, or type to search.")
            continue
        if group == "Onboarding Wizard":
            onboarding_wizard()
            continue
        if group == "Batch mode: Run multiple features":
            # Multi-select features from all groups
            all_features = [{"name": f["emoji"] + " " + f["label"], "value": f["key"]} for f in FEATURE_MANIFEST]
            selected = select_from_list(all_features, message="Select features to run in batch mode (space to select, enter to confirm):", multi=True)
            if not selected:
                continue
            # For each feature, prompt for options if prompt function exists
            import importlib
            batch_plan = []
            for feat_key in selected:
                feat = next((f for f in FEATURE_MANIFEST if f["key"] == feat_key), None)
                prompt_func_name = f"prompt_{feat_key}_options"
                prompt_func = None
                feature_module = feat["module"] if feat else None
                if feature_module and hasattr(feature_module, prompt_func_name):
                    prompt_func = getattr(feature_module, prompt_func_name)
                else:
                    try:
                        mod = importlib.import_module(f"jirassicpack.features.{feat_key}")
                        prompt_func = getattr(mod, prompt_func_name, None)
                    except Exception:
                        prompt_func = None
                if prompt_func:
                    import inspect
                    sig = inspect.signature(prompt_func)
                    if 'jira' in sig.parameters:
                        params = prompt_func({}, jira=None)  # Will be re-prompted with real jira later
                    else:
                        params = prompt_func({})
                else:
                    params = {}
                batch_plan.append({"key": feat_key, "label": feat["label"] if feat else feat_key, "options": params})
            # Show summary
            rich_panel("\n".join([f"{i+1}. {item['label']} (key: {item['key']})" for i, item in enumerate(batch_plan)]), title="Batch Plan", style="info")
            confirm = prompt_select("Proceed to run these features in sequence?", choices=["Yes", "No"])
            if confirm != "Yes":
                continue
            yield batch_plan, "batch_mode"
            continue
        if group == "Help":
            rich_info("🦖 Jirassic Pack CLI Help\n- Use arrow keys, numbers, or type to search.\n- Press Enter to select.\n- 'Back' returns to previous menu.\n- 'Abort' cancels the current operation.\n- 'Settings' lets you change config, log level, and theme.\n- 'Favorites' lets you pin features for quick access.\n- 'Batch mode' lets you run multiple features in sequence.\n- 'Run last feature again' and 'View last report' are available in 'Recently Used'.")
            continue
        if group == "Settings":
            settings_choices = [
                {"name": f"Theme: {CLI_THEME}", "value": "theme"},
                {"name": f"Log level: {CLI_LOG_LEVEL}", "value": "log_level"},
                {"name": "Clear history/reset favorites", "value": "clear_history"},
                {"name": "⬅️ Back to main menu", "value": "return_to_main_menu"},
                {"name": "What is this?", "value": "help"},
                {"name": "Update all caches (refresh user list, etc)", "value": "update_caches"},
            ]
            setting = prompt_select("Settings:", choices=settings_choices)
            if setting == "return_to_main_menu":
                continue
            if setting == "help":
                rich_info("🦖 Settings lets you change the CLI theme, log level, and clear your history/favorites. Theme affects color scheme. Log level controls verbosity.")
                continue
            if setting == "theme":
                theme = prompt_select("Select CLI theme:", choices=["default", "light", "dark", "jurassic", "matrix"])
                CLI_THEME = theme
                save_cli_state()
                rich_info(f"Theme set to {theme} (will apply on next run if not immediate).")
                continue
            if setting == "log_level":
                log_level = prompt_select("Select log level:", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
                CLI_LOG_LEVEL = log_level
                save_cli_state()
                rich_info(f"Log level set to {log_level} (will apply on next run if not immediate).")
                continue
            if setting == "clear_history":
                confirm = prompt_select("Are you sure you want to clear all history and reset favorites?", choices=["Yes, clear all", "No, cancel"])
                if confirm == "Yes, clear all":
                    RECENT_FEATURES.clear()
                    FAVORITE_FEATURES.clear()
                    global LAST_FEATURE, LAST_REPORT_PATH
                    LAST_FEATURE = None
                    LAST_REPORT_PATH = None
                    save_cli_state()
                    rich_info("🦖 All history and favorites have been cleared.")
                else:
                    rich_info("No changes made.")
                continue
            if setting == "update_caches":
                clear_all_caches()
                refresh_user_cache(None)
                rich_info("All major caches have been refreshed.")
                continue
            continue
        if group == "Exit":
            save_cli_state()
            yield "exit", None
            return
        # Contextual help for group menus
        if group not in FEATURE_GROUPS and group not in ["Favorites", "Recently Used"]:
            continue
        if group == "Favorites":
            fav_choices = []
            for i, feat in enumerate(FAVORITE_FEATURES):
                fav_choices.append({"name": f"[{i+1}] {feat['emoji']} {feat['label']} — {feat['description']}", "value": feat['key']})
            if fav_choices:
                fav_choices.append({"name": "Unpin a feature", "value": "unpin_feature"})
            fav_choices.append({"name": "⬅️ Back to main menu", "value": "return_to_main_menu"})
            fav_choices.append({"name": "What is this?", "value": "help"})
            feature = prompt_select(
                "Favorite features (pinned):",
                choices=fav_choices
            )
            if feature == "return_to_main_menu":
                continue
            if feature == "help":
                rich_info("🦖 Favorites are features you have pinned for quick access. Pin/unpin features from any group menu.")
                continue
            if feature == "unpin_feature":
                if not FAVORITE_FEATURES:
                    rich_info("No favorites to unpin.")
                    continue
                unpin_choices = [f"{feat['emoji']} {feat['label']}" for feat in FAVORITE_FEATURES]
                to_unpin = prompt_select("Select a feature to unpin:", choices=unpin_choices)
                idx = unpin_choices.index(to_unpin)
                FAVORITE_FEATURES.pop(idx)
                save_cli_state()
                rich_info(f"Unpinned {to_unpin} from favorites.")
                continue
            yield feature, group
            continue
        if group == "Recently Used":
            recent_choices = []
            if LAST_FEATURE:
                recent_choices.append({"name": f"🔁 Run last feature again: {LAST_FEATURE['emoji']} {LAST_FEATURE['label']}", "value": LAST_FEATURE['key']})
            if LAST_REPORT_PATH:
                recent_choices.append({"name": f"📄 View last report: {LAST_REPORT_PATH}", "value": "view_last_report"})
            for i, feat in enumerate(RECENT_FEATURES[-5:][::-1]):
                recent_choices.append({"name": f"[{i+1}] {feat['emoji']} {feat['label']} — {feat['description']}", "value": feat['key']})
            recent_choices.append({"name": "⬅️ Back to main menu", "value": "return_to_main_menu"})
            recent_choices.append({"name": "What is this?", "value": "help"})
            feature = prompt_select(
                "Recently used features:",
                choices=recent_choices
            )
            if feature == "return_to_main_menu":
                continue
            if feature == "help":
                rich_info("🦖 Recently Used shows your last 5 features and quick actions. Use it to quickly rerun or access recent reports.")
                continue
            if feature == "view_last_report":
                if LAST_REPORT_PATH and os.path.exists(LAST_REPORT_PATH):
                    os.system(f"open '{LAST_REPORT_PATH}'" if sys.platform == "darwin" else f"xdg-open '{LAST_REPORT_PATH}'")
                else:
                    rich_info("No last report found.")
                continue
            yield feature, group
            continue
        # Normal group
        features = FEATURE_GROUPS[group]
        feature_map = {f['key']: f for f in FEATURE_MANIFEST if f['group'] == group}
        submenu_choices = []
        for i, (name, key) in enumerate(features):
            feat = feature_map.get(key)
            desc = f" — {feat['description']}" if feat and 'description' in feat else ""
            shortcut = f"[{i+1}] "
            submenu_choices.append({"name": f"{shortcut}{name}{desc}", "value": key})
        submenu_choices.append({"name": "Pin a feature to Favorites", "value": "pin_feature"})
        submenu_choices.append({"name": "⬅️ Back to main menu", "value": "return_to_main_menu"})
        submenu_choices.append({"name": "What is this?", "value": "help"})
        feature = prompt_select(
            f"Select a feature from '{group}': (type to search or use number)",
            choices=submenu_choices
        )
        if feature == "return_to_main_menu":
            continue  # Go back to group selection
        if feature == "help":
            rich_info(f"🦖 This menu shows all features in the '{group}' group. Pin your favorites, or select a feature to run.")
            continue
        if feature == "pin_feature":
            pin_choices = [f"{feat['emoji']} {feat['label']}" for feat in feature_map.values() if feat not in FAVORITE_FEATURES]
            if not pin_choices:
                rich_info("All features in this group are already pinned.")
                continue
            to_pin = prompt_select("Select a feature to pin:", choices=pin_choices)
            idx = pin_choices.index(to_pin)
            feat_to_pin = [f for f in feature_map.values() if f not in FAVORITE_FEATURES][idx]
            FAVORITE_FEATURES.append(feat_to_pin)
            save_cli_state()
            rich_info(f"Pinned {to_pin} to favorites.")
            continue
        # Track recent
        feat_obj = feature_map.get(feature)
        if feat_obj and feat_obj not in RECENT_FEATURES:
            RECENT_FEATURES.append(feat_obj)
            save_cli_state()
        if feat_obj:
            LAST_FEATURE = feat_obj
            save_cli_state()
        yield feature, group

# ... (rest of the file remains unchanged) 