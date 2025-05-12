import os
import sys
import questionary
import re
from colorama import Fore, Style
from jirassicpack.utils import info, contextual_log

JUNGLE_GREEN = '\033[38;5;34m'
WARNING_YELLOW = '\033[38;5;226m'
DANGER_RED = '\033[38;5;196m'
EARTH_BROWN = '\033[38;5;94m'
RESET = Style.RESET_ALL

# --- Jurassic Park ASCII Art Banners by Feature ---
FEATURE_ASCII_ART = {
    'create_issue': r'\n   __\n  / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🦖\n',
    'update_issue': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🦕\n',
    'bulk_operations': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🦴\n',
    'user_team_analytics': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🧬\n',
    'integration_tools': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🔗\n',
    'time_tracking_worklogs': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n⏳\n',
    'automated_documentation': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n📄\n',
    'sprint_board_management': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🌋\n',
    'advanced_metrics': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n📊\n',
    'gather_metrics': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n📈\n',
    'summarize_tickets': r'\n      __\n     / _)_\n.-^^^-/ /\n__/       /\n<__.|_|-|_|\n🗂️\n',
}

FEATURE_COLORS = {
    'create_issue': JUNGLE_GREEN,
    'update_issue': WARNING_YELLOW,
    'bulk_operations': DANGER_RED,
    'user_team_analytics': EARTH_BROWN,
    'integration_tools': Fore.CYAN,
    'time_tracking_worklogs': Fore.MAGENTA,
    'automated_documentation': Fore.BLUE,
    'sprint_board_management': Fore.YELLOW,
    'advanced_metrics': Fore.GREEN,
    'gather_metrics': Fore.CYAN,
    'summarize_tickets': Fore.LIGHTYELLOW_EX,
}

def ensure_output_dir(directory: str) -> None:
    """
    Ensure the output directory exists, creating it if necessary.
    Used by all features to guarantee output files can be written.
    """
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

def print_section_header(title: str, feature_key: str = None):
    """
    Print a section header with per-feature ASCII art and color theme.
    """
    color = FEATURE_COLORS.get(feature_key, EARTH_BROWN)
    art = FEATURE_ASCII_ART.get(feature_key, '')
    try:
        import pyfiglet
        header = pyfiglet.figlet_format(title, font="mini")
    except Exception:
        header = title
    print(color + art + RESET)
    print(color + header + RESET)
    print(f"[Section: {title}]")  # For screen readers

def celebrate_success():
    print(JUNGLE_GREEN + "🎉 Success! 🎉" + RESET)

def retry_or_skip(action_desc, func, *args, **kwargs):
    while True:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(DANGER_RED + f"🦖 Error during {action_desc}: {e}" + RESET)
            choice = questionary.select(
                f"🦖 {action_desc} failed. What would you like to do?",
                choices=["Retry", "Skip", "Exit"],
                style=questionary.Style([
                    ("selected", "fg:#ffcc00 bold"),  # Yellow
                    ("pointer", "fg:#22bb22 bold"),   # Jungle green
                ])
            ).ask()
            if choice == "Retry":
                continue
            elif choice == "Skip":
                return None
            else:
                sys.exit(1)

def redact_sensitive(options):
    """
    Redact sensitive fields in options dict for logging/output.
    """
    if not isinstance(options, dict):
        return options
    redacted = options.copy()
    for k in redacted:
        if any(s in k.lower() for s in ["token", "password", "secret", "api_key"]):
            redacted[k] = "***REDACTED***"
    return redacted 