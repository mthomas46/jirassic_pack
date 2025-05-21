"""
Prompt utilities for Jirassic Pack CLI.
Handles all user input prompts, selection, pagination, and fuzzy search.
"""
import questionary
from questionary import Choice, Style as QStyle
from InquirerPy import inquirer
from InquirerPy.utils import get_style
from jirassicpack.utils.rich_prompt import rich_panel
from typing import Any, List, Optional

# Jurassic Park color palette
JUNGLE_GREEN = '\033[38;5;34m'
WARNING_YELLOW = '\033[38;5;226m'
DANGER_RED = '\033[38;5;196m'
EARTH_BROWN = '\033[38;5;94m'
RESET = '\033[0m'

DEFAULT_PROMPT_STYLE = QStyle([
    ("selected", "fg:#22bb22 bold"),
    ("pointer", "fg:#ffcc00 bold"),
    ("question", "fg:#00aaee bold"),
    ("answer", "fg:#ffaa00 bold"),
    ("highlighted", "fg:#ffcc00 bold"),
])
INQUIRERPY_STYLE = get_style({
    "selected": "fg:#22bb22 bold",
    "pointer": "fg:#ffcc00 bold",
    "question": "fg:#00aaee bold",
    "answer": "fg:#ffaa00 bold",
    "highlighted": "fg:#ffcc00 bold",
})

def prompt_text(message, default=None, **kwargs):
    rich_panel(message, style="prompt")
    return questionary.text(message, default=default, style=DEFAULT_PROMPT_STYLE, **kwargs).ask()

def prompt_select(message, choices, **kwargs):
    style = kwargs.pop('style', DEFAULT_PROMPT_STYLE)
    if choices and isinstance(choices[0], dict) and 'name' in choices[0] and 'value' in choices[0]:
        q_choices = [Choice(title=c['name'], value=c['value']) for c in choices]
        rich_panel(message, style="prompt")
        picked = questionary.select(message, choices=q_choices, style=style, **kwargs).ask()
        if isinstance(picked, Choice):
            picked = picked.value
        return picked
    if (isinstance(choices, list) and (
        choices == ["Yes", "No"] or choices == ["No", "Yes"] or len(choices) <= 4
    )):
        rich_panel(message, style="prompt")
        picked = questionary.select(message, choices=choices, style=style, **kwargs).ask()
        if isinstance(picked, Choice):
            picked = picked.value
        return picked
    else:
        return _select_from_list(
            items=choices,
            message=message,
            display_fn=str,
            multi=False,
            allow_abort=False,
            style=style
        )

def prompt_password(message, **kwargs):
    rich_panel(message, style="prompt")
    return questionary.password(message, style=DEFAULT_PROMPT_STYLE, **kwargs).ask()

def prompt_checkbox(message, choices, **kwargs):
    style = kwargs.pop('style', DEFAULT_PROMPT_STYLE)
    if choices and isinstance(choices[0], dict) and 'name' in choices[0] and 'value' in choices[0]:
        q_choices = [Choice(title=c['name'], value=c['value']) for c in choices]
        rich_panel(message, style="prompt")
        picked = questionary.checkbox(message, choices=q_choices, style=style, **kwargs).ask()
        if picked and isinstance(picked[0], Choice):
            picked = [p.value for p in picked]
        return picked
    else:
        rich_panel(message, style="prompt")
        picked = questionary.checkbox(message, choices=choices, style=style, **kwargs).ask()
        if picked and isinstance(picked[0], Choice):
            picked = [p.value for p in picked]
        return picked

def select_with_pagination_and_fuzzy(choices, message="Select an item:", page_size=15, fuzzy_threshold=30):
    if len(choices) > fuzzy_threshold:
        return inquirer.fuzzy(
            message=message,
            choices=choices,
            max_height="70%"
        ).execute()
    elif len(choices) > page_size:
        page = 0
        total_pages = (len(choices) - 1) // page_size + 1
        while True:
            start = page * page_size
            end = start + page_size
            page_choices = choices[start:end]
            nav = []
            if page > 0:
                nav.append("⬅️ Previous page")
            if end < len(choices):
                nav.append("➡️ Next page")
            nav.append("🔤 Jump to letter")
            nav.append("🔢 Jump to page")
            nav.append("❌ Exit")
            selection = prompt_select(
                f"{message} (Page {page+1}/{total_pages})",
                choices=page_choices + nav
            )
            if selection == "⬅️ Previous page":
                page -= 1
            elif selection == "➡️ Next page":
                page += 1
            elif selection == "🔢 Jump to page":
                page = int(prompt_text("Enter page number:", default=str(page+1))) - 1
            elif selection == "🔤 Jump to letter":
                letter = prompt_text("Type a letter to jump:")
                idx = next((index for index, choice in enumerate(choices) if choice.lower().startswith(letter.lower())), None)
                if idx is not None:
                    page = idx // page_size
                else:
                    print("No items found for that letter.")
            elif selection == "❌ Exit":
                return None
            else:
                return selection
    else:
        return prompt_select(message, choices=choices)

def _select_from_list(
    items,
    message="Select an item:",
    display_fn=None,
    multi=False,
    page_size=15,
    fuzzy_threshold=30,
    allow_abort=True,
    style=DEFAULT_PROMPT_STYLE
):
    display_fn = display_fn or (lambda x: str(x))
    if items and isinstance(items[0], dict) and 'name' in items[0] and 'value' in items[0]:
        choices = [Choice(title=item['name'], value=item['value']) for item in items]
    else:
        choices = [display_fn(item) for item in items]
    if allow_abort:
        abort_label = "❌ Abort"
        choices = choices + [abort_label]
    if multi:
        picked = questionary.checkbox(message, choices=choices, style=style).ask()
        if picked and isinstance(picked[0], Choice):
            picked = [p.value for p in picked]
        if allow_abort and abort_label in picked:
            return None
        if items and isinstance(items[0], dict) and 'name' in items[0] and 'value' in items[0]:
            return picked
        return [items[choices.index(p)] for p in picked if p != abort_label]
    if len(choices) > fuzzy_threshold:
        display_map = {}
        display_choices = []
        for choice in choices:
            if isinstance(choice, Choice):
                display_map[choice.title] = choice.value
                display_choices.append(choice.title)
            else:
                display_map[choice] = choice
                display_choices.append(choice)
        if allow_abort and abort_label not in display_choices:
            display_choices.append(abort_label)
        picked = inquirer.fuzzy(message=message, choices=display_choices, max_height="70%", style=INQUIRERPY_STYLE).execute()
        if allow_abort and picked == abort_label:
            return None
        return display_map.get(picked, picked)
    elif len(choices) > page_size:
        page = 0
        total_pages = (len(choices) - 1) // page_size + 1
        while True:
            start = page * page_size
            end = start + page_size
            page_choices = choices[start:end]
            nav = []
            if page > 0:
                nav.append("⬅️ Previous page")
            if end < len(choices):
                nav.append("➡️ Next page")
            nav.append("🔤 Jump to letter")
            nav.append("🔢 Jump to page")
            if allow_abort:
                nav.append(abort_label)
            selection = questionary.select(f"{message} (Page {page+1}/{total_pages})", choices=page_choices + nav, style=style).ask()
            if isinstance(selection, Choice):
                selection = selection.value
            if selection == "⬅️ Previous page":
                page -= 1
            elif selection == "➡️ Next page":
                page += 1
            elif selection == "🔢 Jump to page":
                page = int(prompt_text("Enter page number:", default=str(page+1))) - 1
            elif selection == "🔤 Jump to letter":
                letter = prompt_text("Type a letter to jump:")
                idx = next((index for index, choice in enumerate(choices) if isinstance(choice, str) and choice.lower().startswith(letter.lower())), None)
                if idx is not None:
                    page = idx // page_size
                else:
                    print("No items found for that letter.")
            elif allow_abort and selection == abort_label:
                return None
            else:
                if items and isinstance(items[0], dict) and 'name' in items[0] and 'value' in items[0]:
                    return selection
                return items[choices.index(selection)]
    else:
        picked = questionary.select(message, choices=choices, style=style).ask()
        if isinstance(picked, Choice):
            picked = picked.value
        if allow_abort and picked == abort_label:
            return None
        if items and isinstance(items[0], dict) and 'name' in items[0] and 'value' in items[0]:
            return picked
        return items[choices.index(picked)]

# Public alias for select_from_list
select_from_list = _select_from_list

def select_with_fuzzy_multiselect(choices, message="Select items:", min_selection=1, max_selection=None):
    """
    Hybrid fuzzy multi-select: repeatedly show a fuzzy single-select to add users, with 'Done' and 'Abort' options, then confirm with a checkbox. True fuzzy search and reliable multi-select.
    Returns None if aborted, or a list of selected values.
    """
    abort_label = "❌ Abort"
    done_label = "✅ Done selecting"
    clear_label = "🔄 Clear Selections"
    base_choices = choices.copy()
    selected = []
    while True:
        # Build list of choices not yet selected
        remaining = [c for c in base_choices if (c['value'] if isinstance(c, dict) else c) not in selected]
        fuzzy_choices = remaining + [{"name": done_label, "value": done_label}, {"name": abort_label, "value": abort_label}]
        prompt_message = message + "\n(Use spacebar or Enter to select, type to fuzzy search, select 'Done' when finished.)\nSelected: " + ", ".join(str(s) for s in selected)
        picked = inquirer.fuzzy(
            message=prompt_message,
            choices=fuzzy_choices,
            multiselect=False,
            validate=None,
            max_height="70%"
        ).execute()
        if picked == abort_label or picked is None:
            return None
        if picked == done_label:
            break
        # Extract value if dict
        val = picked['value'] if isinstance(picked, dict) else picked
        if val not in selected:
            selected.append(val)
    # Final confirmation with checkbox
    if not selected:
        return None
    confirm_choices = [{"name": str(c), "value": c, "enabled": True} for c in selected] + [{"name": clear_label, "value": clear_label}, {"name": abort_label, "value": abort_label}]
    while True:
        confirm_message = "Review your selections (spacebar to select/deselect, Enter to confirm):"
        confirmed = inquirer.checkbox(
            message=confirm_message,
            choices=confirm_choices,
            instruction="Type to filter",
            transformer=lambda result: result,
            filter=lambda result: result,
            cycle=True,
            validate=None,
            max_height="70%"
        ).execute()
        if not confirmed or abort_label in confirmed:
            return None
        if clear_label in confirmed:
            selected = []
            break  # Go back to fuzzy selection
        if min_selection and len(confirmed) < min_selection:
            print(f"Please select at least {min_selection} item(s), or Abort.")
            continue
        return confirmed

__all__ = [
    "prompt_text",
    "prompt_select",
    "prompt_password",
    "prompt_checkbox",
    "select_with_pagination_and_fuzzy",
    "select_from_list",
    "select_with_fuzzy_multiselect"
] 