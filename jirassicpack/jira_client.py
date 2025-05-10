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

    # Additional methods for POST, PUT, etc. can be added as needed. 