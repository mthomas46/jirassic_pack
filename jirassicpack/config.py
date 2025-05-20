import os
import yaml
from jirassicpack.utils.logging import redact_sensitive, contextual_log
from marshmallow import fields, ValidationError
from jirassicpack.utils.rich_prompt import rich_error
from jirassicpack.utils.io import get_option
from jirassicpack.utils.fields import BaseOptionsSchema

"""
config.py

Handles configuration loading for Jirassic Pack CLI. Supports YAML, environment variables, and interactive CLI prompts. Provides robust schema validation for all config sections (Jira, LLM, OpenAI, GitHub) and ensures all required fields are present before feature execution. Prioritizes environment variables > YAML > defaults. Used by all features for consistent config access and validation.
"""

class ConfigLoader:
    """
    Loads and manages configuration for the Jirassic Pack CLI.
    - Loads from YAML file, environment variables, or interactive prompts.
    - Supports all feature-specific options as environment variables (e.g., JIRA_PROJECT, JIRA_ISSUE_TYPE).
    - Priority: environment variable > YAML config > default.
    - Provides robust schema validation and interactive correction for missing/invalid fields.
    """
    def __init__(self, config_path=None):
        """
        Initialize the ConfigLoader.
        Args:
            config_path (str, optional): Path to the YAML config file. Defaults to 'config.yaml'.
        """
        self.config = {}
        if not config_path:
            config_path = "config.yaml"
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as file:
                self.config = yaml.safe_load(file)

    def get(self, key, default=None):
        """
        Retrieve a config value by key, checking environment variables first, then YAML, then default.
        Args:
            key (str): Config key.
            default (Any, optional): Default value if not found.
        Returns:
            Any: The config value.
        """
        env_key = key.upper()
        if env_key in os.environ:
            return os.environ[env_key]
        if key in self.config:
            return self.config[key]
        return default

    def get_jira_config(self):
        """
        Get and validate Jira configuration (URL, email, API token).
        Prompts interactively for missing/invalid fields using Marshmallow schema.
        Returns:
            dict: Validated Jira config.
        """
        url = os.environ.get('JIRA_URL') or self.config.get('jira', {}).get('url')
        email = os.environ.get('JIRA_EMAIL') or self.config.get('jira', {}).get('email')
        api_token = os.environ.get('JIRA_API_TOKEN') or self.config.get('jira', {}).get('api_token')
        config = {
            'url': url,
            'email': email,
            'api_token': api_token
        }
        schema = JirassicConfigSchema()
        while True:
            try:
                validated = schema.load(config)
                return validated
            except ValidationError as err:
                rich_error(f"Jira config validation error: {err.messages}")
                for field, msgs in err.messages.items():
                    prompt = f"🦖 Jira {field.replace('_', ' ').title()}: "
                    config[field] = get_option(config, field, prompt=prompt, required=True)
                # After correction, loop to re-validate

    def get_options(self, feature_name=None):
        """
        Compose options for a feature from environment, YAML, or defaults.
        Optionally filter by feature_name for batch mode.
        Args:
            feature_name (str, optional): Name of the feature for batch mode.
        Returns:
            dict: Options dictionary for the feature.
        """
        # Compose options from env > YAML > default for all known feature options
        def env_or_yaml(opt, section=None, default=None):
            env_key = f'JIRA_{opt.upper()}'
            if env_key in os.environ:
                return os.environ[env_key]
            if section and section in self.config and opt in self.config[section]:
                return self.config[section][opt]
            if 'options' in self.config and opt in self.config['options']:
                return self.config['options'][opt]
            return default

        options = {
            'project': env_or_yaml('project'),
            'issue_type': env_or_yaml('issue_type'),
            'summary': env_or_yaml('summary'),
            'description': env_or_yaml('description'),
            'issue_key': env_or_yaml('issue_key'),
            'field': env_or_yaml('field'),
            'value': env_or_yaml('value'),
            'jql': env_or_yaml('jql'),
            'bulk_action': env_or_yaml('bulk_action'),
            'bulk_comment': env_or_yaml('bulk_comment'),
            'bulk_field': env_or_yaml('bulk_field'),
            'bulk_value': env_or_yaml('bulk_value'),
            'team': env_or_yaml('team'),
            'user': env_or_yaml('user'),
            'start_date': env_or_yaml('start_date'),
            'end_date': env_or_yaml('end_date'),
            'output_dir': env_or_yaml('output_dir', default='output'),
            'integration_jql': env_or_yaml('integration_jql'),
            'doc_type': env_or_yaml('doc_type'),
            'fix_version': env_or_yaml('fix_version'),
            'sprint': env_or_yaml('sprint'),
            'changelog_start': env_or_yaml('changelog_start'),
            'changelog_end': env_or_yaml('changelog_end'),
            'sprint_name': env_or_yaml('sprint_name'),
            'dry_run': env_or_yaml('dry_run', default=False),
        }
        # Optionally filter by feature_name for batch mode
        if feature_name and 'features' in self.config:
            for feat in self.config['features']:
                if feat.get('name') == feature_name:
                    options.update(feat.get('options', {}))
        return options

    def contextual_log(self, operation, params, context):
        """
        Log a config operation with context, handling exceptions and redacting sensitive data.
        Args:
            operation (str): Name of the config operation.
            params (dict): Parameters for the operation.
            context (dict): Context for logging.
        Returns:
            Any: Result of the config operation.
        """
        contextual_log('info', f"⚙️ [Config] Starting config operation '{operation}' with params: {redact_sensitive(params)}", operation=operation, params=redact_sensitive(params), extra=context)
        try:
            result = getattr(self, operation)(params)
            contextual_log('info', f"⚙️ [Config] Config operation '{operation}' completed successfully.", operation=operation, status="success", params=redact_sensitive(params), extra=context)
            return result
        except Exception as e:
            contextual_log('error', f"⚙️ [Config] Exception occurred during config operation '{operation}': {e}", exc_info=True, operation=operation, error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context)
            raise 

    def get_llm_config(self):
        """
        Get and validate local LLM configuration (all endpoints).
        Prompts interactively for missing/invalid fields using Marshmallow schema.
        Returns:
            dict: Validated LLM config.
        """
        # Unified loader for all LLM endpoints (text, github, file, health)
        text_url = os.environ.get('LOCAL_LLM_TEXT_URL') or self.config.get('local_llm', {}).get('text_url')
        github_url = os.environ.get('LOCAL_LLM_GITHUB_URL') or self.config.get('local_llm', {}).get('github_url')
        file_url = os.environ.get('LOCAL_LLM_FILE_URL') or self.config.get('local_llm', {}).get('file_url')
        health_url = os.environ.get('LOCAL_LLM_HEALTH_URL') or self.config.get('local_llm', {}).get('health_url')
        config = {
            'text_url': text_url,
            'github_url': github_url,
            'file_url': file_url,
            'health_url': health_url
        }
        schema = LLMConfigSchema()
        while True:
            try:
                validated = schema.load(config)
                return validated
            except ValidationError as err:
                rich_error(f"Local LLM config validation error: {err.messages}")
                for field, msgs in err.messages.items():
                    prompt = f"🦖 Local LLM {field.replace('_', ' ').title()}: "
                    config[field] = get_option(config, field, prompt=prompt, required=True)

    def get_openai_config(self):
        """
        Get and validate OpenAI configuration (API key, model).
        Prompts interactively for missing/invalid fields using Marshmallow schema.
        Returns:
            dict: Validated OpenAI config.
        """
        api_key = os.environ.get('OPENAI_API_KEY') or self.config.get('openai', {}).get('api_key')
        model = os.environ.get('OPENAI_MODEL') or self.config.get('openai', {}).get('model')
        config = {
            'api_key': api_key,
            'model': model
        }
        schema = OpenAIConfigSchema()
        while True:
            try:
                validated = schema.load(config)
                return validated
            except ValidationError as err:
                rich_error(f"OpenAI config validation error: {err.messages}")
                for field, msgs in err.messages.items():
                    prompt = f"🦖 OpenAI {field.replace('_', ' ').title()}: "
                    config[field] = get_option(config, field, prompt=prompt, required=True)

    def get_github_config(self):
        """
        Get and validate GitHub configuration (URL, token).
        Prompts interactively for missing/invalid fields using Marshmallow schema.
        Returns:
            dict: Validated GitHub config.
        """
        url = os.environ.get('GITHUB_URL') or self.config.get('github', {}).get('url')
        token = os.environ.get('GITHUB_TOKEN') or self.config.get('github', {}).get('token')
        config = {
            'url': url,
            'token': token
        }
        schema = GitHubConfigSchema()
        while True:
            try:
                validated = schema.load(config)
                return validated
            except ValidationError as err:
                rich_error(f"GitHub config validation error: {err.messages}")
                for field, msgs in err.messages.items():
                    prompt = f"🦖 GitHub {field.replace('_', ' ').title()}: "
                    config[field] = get_option(config, field, prompt=prompt, required=True)

class JirassicConfigSchema(BaseOptionsSchema):
    """
    Marshmallow schema for validating Jira config section.
    Ensures URL, email, and API token are present and valid.
    """
    url = fields.Url(required=True, error_messages={"required": "Jira URL is required.", "invalid": "Invalid Jira URL."})
    email = fields.Email(required=True, error_messages={"required": "Jira email is required.", "invalid": "Invalid email address."})
    api_token = fields.Str(required=True, error_messages={"required": "Jira API token is required."})
    # output_dir and unique_suffix are inherited (but not used)

class LLMConfigSchema(BaseOptionsSchema):
    """
    Marshmallow schema for validating local LLM config section.
    Ensures all endpoint URLs are present and valid.
    """
    text_url = fields.Url(required=True, error_messages={"required": "Local LLM text URL is required.", "invalid": "Invalid URL for local LLM text endpoint."})
    github_url = fields.Url(required=True, error_messages={"required": "Local LLM GitHub URL is required.", "invalid": "Invalid URL for local LLM GitHub endpoint."})
    file_url = fields.Url(required=True, error_messages={"required": "Local LLM file URL is required.", "invalid": "Invalid URL for local LLM file endpoint."})
    health_url = fields.Url(required=True, error_messages={"required": "Local LLM health URL is required.", "invalid": "Invalid health URL for local LLM endpoint."})
    # output_dir and unique_suffix are inherited (but not used)

class OpenAIConfigSchema(BaseOptionsSchema):
    """
    Marshmallow schema for validating OpenAI config section.
    Ensures API key and model are present.
    """
    api_key = fields.Str(required=True, error_messages={"required": "OpenAI API key is required."})
    model = fields.Str(required=True, error_messages={"required": "OpenAI model is required."})
    # output_dir and unique_suffix are inherited (but not used)

class GitHubConfigSchema(BaseOptionsSchema):
    """
    Marshmallow schema for validating GitHub config section.
    Ensures URL and token are present and valid.
    """
    url = fields.Url(required=True, error_messages={"required": "GitHub URL is required.", "invalid": "Invalid GitHub URL."})
    token = fields.Str(required=True, error_messages={"required": "GitHub token is required."})
    # output_dir and unique_suffix are inherited (but not used) 