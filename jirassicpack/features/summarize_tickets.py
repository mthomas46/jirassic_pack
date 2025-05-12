from jirassicpack.utils.io import ensure_output_dir, print_section_header, celebrate_success, retry_or_skip, info, get_option, error
from jirassicpack.utils.logging import contextual_log
from jirassicpack.utils.jira import select_jira_user
from jirassicpack.utils.io import validate_date
import os
import logging
import questionary

def prompt_summarize_tickets_options(options, jira=None):
    """
    Prompt for summarize tickets options, always requiring explicit user selection.
    Uses Jira-aware user selection for consistency.
    Includes robust logging and error handling.
    """
    logger = logging.getLogger(__name__)
    try:
        config_user = options.get('user') or os.environ.get('JIRA_USER')
        user_obj = None
        if jira:
            info("Please select a Jira user for ticket summarization.")
            contextual_log('info', "Please select a Jira user for ticket summarization.", feature='summarize_tickets')
            label, user_obj = select_jira_user(jira, default_user=config_user)
            user = user_obj.get('accountId') if user_obj else ''
            if not user:
                info("Aborted user selection for summarize tickets.")
                contextual_log('info', "Aborted user selection for summarize tickets.", feature='summarize_tickets')
                return None
        else:
            user = get_option(options, 'user', prompt="Jira Username for summary:", default=config_user, required=True)
        start = get_option(options, 'start_date', prompt="Start date (YYYY-MM-DD):", default='2024-01-01', required=True, validate=validate_date)
        end = get_option(options, 'end_date', prompt="End date (YYYY-MM-DD):", default='2024-01-31', required=True, validate=validate_date)
        out_dir = get_option(options, 'output_dir', default='output')
        suffix = options.get('unique_suffix', '')
        logger.info(f"[summarize_tickets] Prompted options: user={user}, start={start}, end={end}, out_dir={out_dir}, suffix={suffix}")
        contextual_log('info', f"[summarize_tickets] Prompted options: user={user}, start={start}, end={end}, out_dir={out_dir}, suffix={suffix}", feature='summarize_tickets')
        return {
            'user': user,
            'start_date': start,
            'end_date': end,
            'output_dir': out_dir,
            'unique_suffix': suffix
        }
    except Exception as e:
        logger.error(f"[summarize_tickets] Error in prompt_summarize_tickets_options: {e}", exc_info=True)
        error(f"Error in summarize tickets prompt: {e}")
        contextual_log('error', f"Error in summarize tickets prompt: {e}", feature='summarize_tickets')
        return None

def summarize_tickets(jira, params, user_email=None, batch_index=None, unique_suffix=None):
    """
    Main feature logic for summarizing tickets. Logs feature start, params, and errors.
    """
    logger = logging.getLogger(__name__)
    try:
        contextual_log('info', f"📝 [Summarize Tickets] Feature start | User: {user_email} | Params: {params} | Suffix: {unique_suffix}", operation="feature_start", params=params, feature='summarize_tickets')
        # --- Main logic placeholder ---
        # Implement your ticket summarization logic here
        logger.info(f"[summarize_tickets] Running with params: {params}")
        # ...
        contextual_log('info', f"📝 [Summarize Tickets] Feature complete | Suffix: {unique_suffix}", operation="feature_end", status="success", params=params, feature='summarize_tickets')
    except KeyboardInterrupt:
        contextual_log('warning', "[summarize_tickets] Graceful exit via KeyboardInterrupt.", operation="feature_end", status="interrupted", params=params, feature='summarize_tickets')
        info("Graceful exit from Summarize Tickets feature.")
    except Exception as e:
        contextual_log('error', f"[summarize_tickets] Exception: {e}", exc_info=True, operation="feature_end", error_type=type(e).__name__, status="error", params=params, feature='summarize_tickets')
        logger.error(f"[summarize_tickets] Exception: {e}", exc_info=True)
        error(f"[summarize_tickets] Exception: {e}")
        raise 