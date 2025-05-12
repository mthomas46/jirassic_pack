import logging
import uuid
from typing import Any, Dict, Optional

# Add your own log formatter or use the existing one from cli.py if needed

def redact_sensitive(options: Any) -> Any:
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

def contextual_log(level: str, message: str, extra: Optional[Dict[str, Any]] = None, **kwargs) -> None:
    """
    Log a message with structured context fields for feature, user, operation, etc.
    """
    logger = logging.getLogger("jirassicpack")
    if extra is None:
        extra = {}
    # Merge in any additional context from kwargs
    context = {**extra, **kwargs}
    # Add a unique operation_id if not present
    if 'operation_id' not in context:
        context['operation_id'] = str(uuid.uuid4())
    log_func = getattr(logger, level, logger.info)
    log_func(message, extra=context) 