"""
Decorators and logging helpers for Jirassic Pack CLI.
Handles function entry/exit logging and feature error handling.
"""
import logging
import traceback
import functools
from jirassicpack.utils.logging import contextual_log, build_context
from jirassicpack.utils.message_utils import info, error

def log_entry_exit(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        depth = getattr(wrapper, '_depth', 0)
        wrapper._depth = depth + 1
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            logging.error(f"[EXCEPTION] {func.__name__}: {e}\n{traceback.format_exc()}")
            wrapper._depth = depth
            raise
        wrapper._depth = depth
        return result
    wrapper._depth = 0
    return wrapper

def feature_error_handler(feature_name):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            user_email = kwargs.get('user_email')
            batch_index = kwargs.get('batch_index')
            unique_suffix = kwargs.get('unique_suffix')
            context = build_context(feature_name, user_email, batch_index, unique_suffix)
            try:
                return func(*args, **kwargs)
            except KeyboardInterrupt:
                contextual_log('warning', f"[{feature_name}] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", extra=context, feature=feature_name)
                info(f"Graceful exit from {feature_name} feature.", extra=context, feature=feature_name)
            except Exception as e:
                contextual_log('error', f"[{feature_name}] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", extra=context, feature=feature_name)
                error(f"[{feature_name}] Exception: {e}", extra=context, feature=feature_name)
                raise
        return wrapper
    return decorator 