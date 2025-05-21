"""
Validation and option utilities for Jirassic Pack CLI.
Handles input validation, required checks, and option retrieval.
"""
from jirassicpack.utils.prompt_utils import prompt_select, prompt_text, prompt_password
from jirassicpack.utils.rich_prompt import rich_error
from marshmallow import ValidationError
from jirassicpack.utils.jira import select_jira_user

def get_option(options, key, prompt=None, default=None, choices=None, required=False, validate=None, password=False, marshmallow_field=None, marshmallow_schema=None):
    value = options.get(key, default)
    while True:
        if choices:
            value = prompt_select(prompt or f"Select {key}:", choices=choices)
        elif password:
            value = prompt_password(prompt or f"Enter {key}:")
        else:
            value = prompt_text(prompt or f"Enter {key}:", default=default or '')
            if value == '' and default is not None:
                value = default
        if marshmallow_field:
            try:
                marshmallow_field.deserialize(value)
            except ValidationError as err:
                suggestion = None
                if hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages and isinstance(err.messages[0], tuple):
                    message, suggestion = err.messages[0]
                elif hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages:
                    message = err.messages[0]
                else:
                    message = str(err)
                rich_error(f"Input validation error: {message}", suggestion)
                continue
        if marshmallow_schema:
            try:
                marshmallow_schema.load({key: value})
            except ValidationError as err:
                suggestion = None
                if hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages and isinstance(err.messages[0], tuple):
                    message, suggestion = err.messages[0]
                elif hasattr(err, 'messages') and isinstance(err.messages, list) and err.messages:
                    message = err.messages[0]
                else:
                    message = str(err)
                rich_error(f"Input validation error: {message}", suggestion)
                continue
        if validate and not validate(value):
            rich_error(f"Invalid value for {key}.")
            continue
        if required and (not value or not value.strip()):
            rich_error(f"{key} is required.")
            continue
        break
    return value

def validate_required(value):
    """
    Return True if the value is not None and not empty (after stripping).
    """
    return value is not None and str(value).strip() != ""

def require_param(param, name):
    if not param:
        raise ValueError(f"Missing required parameter: {name}")
    return param

def safe_get(d, keys, default=None):
    """
    Safely get a nested value from a dict using a list of keys.
    Example: safe_get(issue, ['fields', 'summary'], '').
    """
    current = d
    try:
        for key in keys:
            current = current[key]
        return current
    except Exception:
        return default

def prompt_with_schema(schema, options, jira=None, abort_option=True):
    """
    Prompt for all fields in a Marshmallow schema, validate, and return the result dict.
    Args:
        schema: Marshmallow Schema instance.
        options: dict of initial/default values.
        jira: Optional Jira client for user/team selection fields.
        abort_option: If True, allow user to abort at any prompt.
    Returns:
        dict: Validated options, or '__ABORT__' if aborted.
    """
    from jirassicpack.utils.prompt_utils import prompt_text, prompt_select, prompt_password
    from jirassicpack.utils.rich_prompt import rich_error
    from jirassicpack.utils.jira import select_jira_user
    from marshmallow import ValidationError
    from jirassicpack.utils.message_utils import info
    data = dict(options)
    fields = schema.fields
    print(f"[DEEPDEBUG] prompt_with_schema called. Initial data: {data}")
    info(f"[DEEPDEBUG] prompt_with_schema called. Initial data: {data}")
    while True:
        for name, field in fields.items():
            # Always prompt for 'user', even if a value is present
            if name == 'user':
                print(f"[DEEPDEBUG] Forcing prompt for 'user'. Current data: {data}")
                info(f"[DEEPDEBUG] Forcing prompt for 'user'. Current data: {data}")
            elif name in data and data[name] not in (None, ''):
                continue
            prompt = field.metadata.get('prompt') or f"Enter {name.replace('_', ' ').title()}:"
            default = field.default if hasattr(field, 'default') else None
            if hasattr(field, 'load_default'):
                default = field.load_default
            if name == 'user' and jira:
                print(f"[DEEPDEBUG] Invoking select_jira_user for 'user' field.")
                info("[DEEPDEBUG] Invoking select_jira_user for 'user' field.")
                label_user_tuple = select_jira_user(jira, allow_multiple=False)
                if not label_user_tuple or not label_user_tuple[1]:
                    if abort_option:
                        return '__ABORT__'
                    else:
                        continue
                data[name] = label_user_tuple[1].get('accountId')
                continue
            if hasattr(field, 'choices') and field.choices:
                value = prompt_select(prompt, choices=field.choices, default=default)
            elif getattr(field, 'password', False):
                value = prompt_password(prompt)
            else:
                value = prompt_text(prompt, default=default)
            if abort_option and value in (None, '__ABORT__', '❌ Abort'):
                return '__ABORT__'
            data[name] = value
        try:
            validated = schema.load(data)
            print(f"[DEEPDEBUG] prompt_with_schema validated: {validated}")
            info(f"[DEEPDEBUG] prompt_with_schema validated: {validated}")
            return validated
        except ValidationError as err:
            for field_name, msgs in err.messages.items():
                suggestion = None
                if isinstance(msgs, list) and msgs and isinstance(msgs[0], tuple):
                    message, suggestion = msgs[0]
                elif isinstance(msgs, list) and msgs:
                    message = msgs[0]
                else:
                    message = str(msgs)
                rich_error(f"Input validation error for '{field_name}': {message}", suggestion)
            # Remove invalid fields so they are prompted again
            for field_name in err.messages:
                data.pop(field_name, None) 