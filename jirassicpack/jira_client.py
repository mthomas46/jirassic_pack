import requests
from requests.adapters import HTTPAdapter, Retry
import logging

logger = logging.getLogger("jirassicpack")

class JiraClient:
    """
    Handles authentication and requests to the Jira REST API, with retry and timeout support.
    """
    def __init__(self, url, email, api_token, timeout=10, max_retries=3):
        self.base_url = url.rstrip('/')
        self.auth = (email, api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self.timeout = timeout
        self.session = requests.Session()
        retries = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT"]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session.mount('http://', HTTPAdapter(max_retries=retries))

    def get(self, endpoint, params=None):
        """
        Perform a GET request to the Jira API with retry and timeout.
        """
        url = f"{self.base_url}/rest/api/3/{endpoint.lstrip('/')}"
        response = self.session.get(url, headers=self.headers, auth=self.auth, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def post(self, endpoint, json=None):
        """
        Perform a POST request to the Jira API with retry and timeout.
        """
        url = f"{self.base_url}/rest/api/3/{endpoint.lstrip('/')}"
        response = self.session.post(url, headers=self.headers, auth=self.auth, json=json, timeout=self.timeout)
        response.raise_for_status()
        return response

    def put(self, endpoint, json=None):
        """
        Perform a PUT request to the Jira API with retry and timeout.
        """
        url = f"{self.base_url}/rest/api/3/{endpoint.lstrip('/')}"
        response = self.session.put(url, headers=self.headers, auth=self.auth, json=json, timeout=self.timeout)
        response.raise_for_status()
        return response

    def search_issues(self, jql, fields=None, max_results=100, context=None):
        """
        Search Jira issues using JQL.
        :param jql: Jira Query Language string
        :param fields: List of fields to return (comma-separated string or list)
        :param max_results: Maximum number of issues to return
        :return: List of issues
        """
        context = context or {}
        logger.info(
            f"[JiraClient] JQL sent: {jql}",
            extra={
                "feature": context.get("feature"),
                "user": context.get("user"),
                "batch": context.get("batch"),
                "suffix": context.get("suffix"),
            }
        )
        params = {
            'jql': jql,
            'maxResults': max_results
        }
        if fields:
            if isinstance(fields, list):
                params['fields'] = ','.join(fields)
            else:
                params['fields'] = fields
        response = self.get('search', params=params)
        return response.get('issues', [])

    def get_user(self, account_id=None, username=None, key=None, email=None):
        """
        Get a user by accountId, username, key, or email.
        """
        params = {}
        if account_id:
            params['accountId'] = account_id
        if username:
            params['username'] = username
        if key:
            params['key'] = key
        if email:
            params['email'] = email
        return self.get('user', params=params)

    def search_users(self, query=None, start_at=0, max_results=50):
        """
        Search for users using a query string.
        """
        params = {'startAt': start_at, 'maxResults': max_results}
        if query:
            params['query'] = query
        return self.get('users/search', params=params)

    def get_user_property(self, account_id, property_key):
        """
        Get a user's property by accountId and propertyKey.
        """
        endpoint = f'user/properties/{property_key}'
        params = {'accountId': account_id}
        return self.get(endpoint, params=params)

    def get_task(self, issue_id_or_key):
        """
        Get a Jira issue (task) by issueId or key.
        """
        endpoint = f'issue/{issue_id_or_key}'
        return self.get(endpoint)

    def get_mypreferences(self):
        """
        Get the current user's preferences.
        """
        return self.get('mypreferences')

    def get_current_user(self):
        """
        Get the current user (myself endpoint).
        """
        return self.get('myself')

    def list_boards(self, name=None, type=None, start_at=0, max_results=50):
        """
        List all boards (optionally filter by name/type) using the Jira Agile API.
        """
        endpoint = '/rest/agile/1.0/board'
        url = f"{self.base_url}{endpoint}"
        params = {'startAt': start_at, 'maxResults': max_results}
        if name:
            params['name'] = name
        if type:
            params['type'] = type
        response = self.session.get(url, headers=self.headers, auth=self.auth, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json().get('values', [])

    def list_sprints(self, board_id, state=None, start_at=0, max_results=50):
        """
        List all sprints for a given board (optionally filter by state).
        """
        endpoint = f'/rest/agile/1.0/board/{board_id}/sprint'
        url = f"{self.base_url}{endpoint}"
        params = {'startAt': start_at, 'maxResults': max_results}
        if state:
            params['state'] = state
        response = self.session.get(url, headers=self.headers, auth=self.auth, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json().get('values', [])

    # Additional methods for POST, PUT, etc. can be added as needed. 

    def contextual_log(self, level, message, operation, params=None, extra=None):
        """
        Logs a message with contextual information.
        :param level: Logging level (e.g., 'info', 'error')
        :param message: The message to log
        :param operation: The operation being performed
        :param params: Additional parameters for the log message
        :param extra: Extra information to include in the log message
        """
        context = {
            "feature": extra.get("feature"),
            "user": extra.get("user"),
            "batch": extra.get("batch"),
            "suffix": extra.get("suffix"),
        }
        if level == 'info':
            logger.info(message, extra=context)
        elif level == 'error':
            logger.error(message, exc_info=True, extra=context)
        else:
            logger.warning(f"Unsupported log level: {level}")

    def redact_sensitive(self, data):
        """
        Redacts sensitive information from a given data structure.
        :param data: The data to redact
        :return: Redacted data
        """
        if isinstance(data, dict):
            return {k: self.redact_sensitive(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.redact_sensitive(item) for item in data]
        elif isinstance(data, str):
            return "REDACTED" if "token" in data.lower() else data
        else:
            return data

    def start_operation(self, operation, params=None, extra=None):
        """
        Logs the start of an operation.
        :param operation: The operation being performed
        :param params: Additional parameters for the log message
        :param extra: Extra information to include in the log message
        """
        self.contextual_log('info', f"🧩 [Jira Client] Starting operation '{operation}' for user '{self.auth[0]}' with params: {self.redact_sensitive(params)}", operation=operation, params=params, extra=extra)

    def end_operation(self, operation, params=None, extra=None):
        """
        Logs the end of an operation.
        :param operation: The operation being performed
        :param params: Additional parameters for the log message
        :param extra: Extra information to include in the log message
        """
        self.contextual_log('info', f"🧩 [Jira Client] Operation '{operation}' completed successfully for user '{self.auth[0]}'.", operation=operation, status="success", params=self.redact_sensitive(params), extra=extra)

    def handle_exception(self, operation, e, params=None, extra=None):
        """
        Logs an exception during an operation.
        :param operation: The operation being performed
        :param e: The exception that occurred
        :param params: Additional parameters for the log message
        :param extra: Extra information to include in the log message
        """
        self.contextual_log('error', f"🧩 [Jira Client] Exception occurred during '{operation}': {e}", exc_info=True, operation=operation, error_type=type(e).__name__, status="error", params=self.redact_sensitive(params), extra=extra) 