import os
import yaml
from jirassicpack.utils.logging import redact_sensitive, contextual_log
from marshmallow import Schema, fields, ValidationError, pre_load
from jirassicpack.utils.rich_prompt import rich_error
from jirassicpack.utils.io import get_option
from jirassicpack.utils.fields import BaseOptionsSchema

class ConfigLoader:
    """
    Loads configuration from YAML, environment variables, or provides defaults for CLI prompts.
    Now supports all feature-specific options as environment variables (e.g., JIRA_PROJECT, JIRA_ISSUE_TYPE, etc.).
    Priority: environment variable > YAML config > default.
    Supported environment variables (examples):
      - JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN
      - JIRA_PROJECT, JIRA_ISSUE_TYPE, JIRA_SUMMARY, JIRA_DESCRIPTION
      - JIRA_ISSUE_KEY, JIRA_FIELD, JIRA_VALUE
      - JIRA_JQL, JIRA_BULK_ACTION, JIRA_BULK_COMMENT, JIRA_BULK_FIELD, JIRA_BULK_VALUE
      - JIRA_TEAM, JIRA_START_DATE, JIRA_END_DATE
      - JIRA_INTEGRATION_JQL
      - JIRA_USER, JIRA_OUTPUT_DIR, JIRA_DOC_TYPE, JIRA_FIX_VERSION, JIRA_SPRINT, JIRA_CHANGELOG_START, JIRA_CHANGELOG_END
    """
    def __init__(self, config_path=None):
        self.config = {}
        if not config_path:
            config_path = "config.yaml"
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as file:
                self.config = yaml.safe_load(file)

    def get(self, key, default=None):
        env_key = key.upper()
        if env_key in os.environ:
            return os.environ[env_key]
        if key in self.config:
            return self.config[key]
        return default

    def get_jira_config(self):
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
        contextual_log('info', f"⚙️ [Config] Starting config operation '{operation}' with params: {redact_sensitive(params)}", operation=operation, params=redact_sensitive(params), extra=context)
        try:
            result = getattr(self, operation)(params)
            contextual_log('info', f"⚙️ [Config] Config operation '{operation}' completed successfully.", operation=operation, status="success", params=redact_sensitive(params), extra=context)
            return result
        except Exception as e:
            contextual_log('error', f"⚙️ [Config] Exception occurred during config operation '{operation}': {e}", exc_info=True, operation=operation, error_type=type(e).__name__, status="error", params=redact_sensitive(params), extra=context)
            raise 

    def get_llm_config(self):
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
    url = fields.Url(required=True, error_messages={"required": "Jira URL is required.", "invalid": "Invalid Jira URL."})
    email = fields.Email(required=True, error_messages={"required": "Jira email is required.", "invalid": "Invalid email address."})
    api_token = fields.Str(required=True, error_messages={"required": "Jira API token is required."})
    # output_dir and unique_suffix are inherited (but not used)

class LLMConfigSchema(BaseOptionsSchema):
    text_url = fields.Url(required=True, error_messages={"required": "Local LLM text URL is required.", "invalid": "Invalid URL for local LLM text endpoint."})
    github_url = fields.Url(required=True, error_messages={"required": "Local LLM GitHub URL is required.", "invalid": "Invalid URL for local LLM GitHub endpoint."})
    file_url = fields.Url(required=True, error_messages={"required": "Local LLM file URL is required.", "invalid": "Invalid URL for local LLM file endpoint."})
    health_url = fields.Url(required=True, error_messages={"required": "Local LLM health URL is required.", "invalid": "Invalid health URL for local LLM endpoint."})
    # output_dir and unique_suffix are inherited (but not used)

class OpenAIConfigSchema(BaseOptionsSchema):
    api_key = fields.Str(required=True, error_messages={"required": "OpenAI API key is required."})
    model = fields.Str(required=True, error_messages={"required": "OpenAI model is required."})
    # output_dir and unique_suffix are inherited (but not used)

class GitHubConfigSchema(BaseOptionsSchema):
    url = fields.Url(required=True, error_messages={"required": "GitHub URL is required.", "invalid": "Invalid GitHub URL."})
    token = fields.Str(required=True, error_messages={"required": "GitHub token is required."})
    # output_dir and unique_suffix are inherited (but not used) 