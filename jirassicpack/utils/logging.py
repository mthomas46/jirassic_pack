import logging
import uuid
from typing import Any, Dict, Optional

# Add your own log formatter or use the existing one from cli.py if needed

def redact_sensitive(options: Any) -> Any:
    """
    Redact sensitive fields in options dict for logging/output.
    Args:
        options (Any): Options dictionary or object to redact.
    Returns:
        Any: Redacted options with sensitive fields replaced by '***REDACTED***'.
    """
    if not isinstance(options, dict):
        return options
    redacted = options.copy()
    for k in redacted:
        if any(s in k.lower() for s in ["token", "password", "secret", "api_key"]):
            redacted[k] = "***REDACTED***"
    return redacted

def contextual_log(level: str, message: str, extra: Optional[Dict[str, Any]] = None, **kwargs) -> None:
    """
    Log a message with structured context fields for feature, user, operation, etc.
    Handles exc_info as a keyword argument, not in extra/context.
    Args:
        level (str): Logging level (e.g., 'info', 'error').
        message (str): Log message.
        extra (Optional[Dict[str, Any]]): Additional context fields.
        **kwargs: Additional context fields or exc_info.
    Returns:
        None
    """
    logger = logging.getLogger("jirassicpack")
    if extra is None:
        extra = {}
    # Extract exc_info from kwargs if present
    exc_info = kwargs.pop('exc_info', False)
    # Merge in any additional context from kwargs
    context = {**extra, **kwargs}
    # Add a unique operation_id if not present
    if 'operation_id' not in context:
        context['operation_id'] = str(uuid.uuid4())
    log_func = getattr(logger, level, logger.info)
    log_func(message, extra=context, exc_info=exc_info)

def build_context(feature: str = None, user: str = None, batch: Any = None, suffix: str = None, **kwargs) -> Dict[str, Any]:
    """
    Build a structured context dictionary for logging, including feature, user, batch, suffix, and any extra fields.
    Args:
        feature (str, optional): Feature name.
        user (str, optional): User identifier.
        batch (Any, optional): Batch index or identifier.
        suffix (str, optional): Unique suffix for context.
        **kwargs: Additional context fields.
    Returns:
        Dict[str, Any]: Context dictionary for logging.
    """
    context = {}
    if feature is not None:
        context['feature'] = feature
    if user is not None:
        context['user'] = user
    if batch is not None:
        context['batch'] = batch
    if suffix is not None:
        context['suffix'] = suffix
    context.update(kwargs)
    return context 