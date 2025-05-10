import os
import yaml

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
        return {
            'url': url,
            'email': email,
            'api_token': api_token
        }

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