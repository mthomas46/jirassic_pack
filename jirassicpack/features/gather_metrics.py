from jirassicpack.utils.io import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, info, get_option, error, rich_error
from jirassicpack.utils.logging import contextual_log
from jirassicpack.utils.jira import select_jira_user
from jirassicpack.utils.io import validate_date
import os
import logging
import questionary
from jirassicpack.utils.fields import BaseOptionsSchema, validate_date, validate_nonempty
from marshmallow import fields, validate, ValidationError

class GatherMetricsOptionsSchema(BaseOptionsSchema):
    user = fields.Str(required=True, error_messages={"required": "User is required."}, validate=validate_nonempty)
    start_date = fields.Str(required=True, error_messages={"required": "Start date is required."}, validate=validate_date)
    end_date = fields.Str(required=True, error_messages={"required": "End date is required."}, validate=validate_date)
    # output_dir and unique_suffix are inherited

def prompt_gather_metrics_options(options, jira=None):
    """
    Prompt for gather metrics options, always requiring explicit user selection.
    Uses Jira-aware user selection for consistency.
    Includes robust logging and error handling.
    """
    schema = GatherMetricsOptionsSchema()
    logger = logging.getLogger(__name__)
    try:
        config_user = options.get('user') or os.environ.get('JIRA_USER')
        user_obj = None
        if jira:
            info("Please select a Jira user for metrics gathering.")
            contextual_log('info', "Please select a Jira user for metrics gathering.", feature='gather_metrics')
            label, user_obj = select_jira_user(jira, default_user=config_user)
            user = user_obj.get('accountId') if user_obj else ''
            if not user:
                info("Aborted user selection for gather metrics.")
                contextual_log('info', "Aborted user selection for gather metrics.", feature='gather_metrics')
                return None
        else:
            user = get_option(options, 'user', prompt="Jira Username for metrics:", default=config_user, required=True)
        start = get_option(options, 'start_date', prompt="Start date (YYYY-MM-DD):", default='2024-01-01', required=True, validate=validate_date)
        end = get_option(options, 'end_date', prompt="End date (YYYY-MM-DD):", default='2024-01-31', required=True, validate=validate_date)
        out_dir = get_option(options, 'output_dir', default='output')
        suffix = options.get('unique_suffix', '')
        data = {
            'user': user,
            'start_date': start,
            'end_date': end,
            'output_dir': out_dir,
            'unique_suffix': suffix
        }
        try:
            validated = schema.load(data)
            logger.info(f"[gather_metrics] Prompted options: user={user}, start={start}, end={end}, out_dir={out_dir}, suffix={suffix}")
            return validated
        except ValidationError as err:
            for field, msgs in err.messages.items():
                suggestion = None
                if isinstance(msgs, list) and msgs and isinstance(msgs[0], tuple):
                    message, suggestion = msgs[0]
                elif isinstance(msgs, list) and msgs:
                    message = msgs[0]
                else:
                    message = str(msgs)
                rich_error(f"Input validation error for '{field}': {message}", suggestion)
            return None
    except Exception as err:
        logger.error(f"Input validation error: {err}")
        return None

def gather_metrics(jira, params, user_email=None, batch_index=None, unique_suffix=None):
    """
    Main feature logic for gathering metrics. Logs feature start, params, and errors.
    """
    logger = logging.getLogger(__name__)
    try:
        contextual_log('info', f"📊 [Gather Metrics] Feature start | User: {user_email} | Params: {params} | Suffix: {unique_suffix}", operation="feature_start", params=params, feature='gather_metrics')
        # --- Main logic placeholder ---
        # Implement your metrics gathering logic here
        logger.info(f"[gather_metrics] Running with params: {params}")
        # ...
        contextual_log('info', f"📊 [Gather Metrics] Feature complete | Suffix: {unique_suffix}", operation="feature_end", status="success", params=params, feature='gather_metrics')
    except KeyboardInterrupt:
        contextual_log('warning', "[gather_metrics] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=params, feature='gather_metrics')
        info("Graceful exit from Gather Metrics feature.")
    except Exception as e:
        contextual_log('error', f"[gather_metrics] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=params, feature='gather_metrics')
        logger.error(f"[gather_metrics] Exception: {e}", exc_info=True)
        error(f"[gather_metrics] Exception: {e}")
        raise 