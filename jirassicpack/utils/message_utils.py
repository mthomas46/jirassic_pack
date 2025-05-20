"""
Message and error/info utilities for Jirassic Pack CLI.
Handles error/info display, logging, and CLI halting.
"""
import sys
from jirassicpack.utils.rich_prompt import rich_info, rich_error
from jirassicpack.utils.logging import contextual_log

def error(message, extra=None, feature=None):
    rich_error(message)
    try:
        context = extra or {}
        if feature:
            context["feature"] = feature
        contextual_log('error', str(message), extra=context)
    except Exception:
        pass  # Logging is best-effort

def info(message, extra=None, feature=None):
    rich_info(message)
    try:
        context = extra or {}
        if feature:
            context["feature"] = feature
        contextual_log('info', str(message), extra=context)
    except Exception:
        pass

def halt_cli(reason=None):
    msg = f"🦖 CLI halted. {reason}" if reason else "🦖 CLI halted."
    rich_error(msg)
    contextual_log('warning', msg, extra={"feature": "cli"})
    sys.exit(0)

def retry_or_skip(action_desc: str, func, *args, **kwargs):
    while True:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"🦖 Error during {action_desc}: {e}")
            choice = prompt_select(
                f"🦖 {action_desc} failed. What would you like to do?",
                choices=["Retry", "Skip", "Exit"]
            )
            if choice == "Retry":
                continue
            elif choice == "Skip":
                return None
            else:
                sys.exit(1)
from jirassicpack.utils.prompt_utils import prompt_select 