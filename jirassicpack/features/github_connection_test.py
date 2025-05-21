"""
github_connection_test.py

Feature module for testing GitHub API connection and branch/PR listing via the CLI.
Prompts for owner and repo, uses config if available, and prints/logs the results.
Now uses PyGithub for all GitHub API interactions, and mimics LlamalyticsHub's branch and PR lookup.
"""

from jirassicpack.utils.prompt_utils import prompt_text
from jirassicpack.utils.decorators import feature_error_handler
from jirassicpack.config import ConfigLoader
from jirassicpack.utils.logging import contextual_log
from github import Github, GithubException


def safe_contextual_log(level, msg, context, **kwargs):
    try:
        contextual_log(level, msg, extra=context, **kwargs)
    except Exception:
        print(f"[LOGGING ERROR] {level}: {msg} | context: {context}")


def prompt_github_connection_test_options(opts, jira=None):
    # Return a non-empty dictionary to ensure the feature always runs
    return {"run": True}


@feature_error_handler('github_connection_test')
def github_connection_test(params=None):
    """
    Interactive feature to test GitHub API connectivity, list branches, and list PRs for a repo using PyGithub.
    Mimics LlamalyticsHub's branch and PR lookup logic.
    """
    print("\n🐙 Test GitHub API Connection (PyGithub, Branch & PR Lookup) 🐙\n")
    config = ConfigLoader()
    github_conf = config.get_github_config()
    github_token = github_conf.get('token')
    github_url = github_conf.get('url', '')
    default_owner = ''
    default_repo = ''
    if github_url:
        # Try to parse owner/repo from config URL if possible
        import re
        m = re.match(r"https://github.com/([^/]+)/([^/]+)", github_url)
        if m:
            default_owner, default_repo = m.group(1), m.group(2)
    owner = github_conf.get('owner', default_owner)
    repo = github_conf.get('repo', default_repo)
    context = {"feature": "github_connection_test", "owner": owner, "repo": repo}

    if not github_token:
        print("Missing GitHub token. Please check your config and try again.")
        safe_contextual_log('error', "Missing GitHub token.", context)
        return

    g = Github(github_token)
    try:
        user = g.get_user()
        print(f"Authenticated as: {user.login}")
        safe_contextual_log('info', f"Authenticated as: {user.login}", context)
    except GithubException as e:
        print(f"Token test failed: {e}")
        safe_contextual_log('error', f"Token test failed: {e}", context)
        return
    except Exception as e:
        print(f"Unexpected error during token test: {e}")
        safe_contextual_log('error', f"Unexpected error during token test: {e}", context)
        return

    # If owner or repo are missing, prompt the user to select from accessible repos
    if not owner or not repo:
        print("Owner or repo not provided. Fetching accessible repositories...")
        try:
            # Get all repos the user can access (limit to 100 for performance)
            repos = list(g.get_user().get_repos()[:100])
            if not repos:
                print("No accessible repositories found for this user/token.")
                safe_contextual_log('warning', "No accessible repositories found.", context)
                return
            repo_choices = [f"{r.owner.login}/{r.name}" for r in repos]
            from jirassicpack.cli_menu import prompt_select
            selected = prompt_select("Select a repository to test:", choices=repo_choices)
            if not selected:
                print("No repository selected. Skipping repo-specific tests.")
                safe_contextual_log('warning', "No repository selected. Skipping repo-specific tests.", context)
                return
            owner, repo = selected.split('/', 1)
            context["owner"] = owner
            context["repo"] = repo
        except Exception as e:
            print(f"Error fetching accessible repositories: {e}")
            safe_contextual_log('error', f"Error fetching accessible repositories: {e}", context)
            return

    try:
        repo_obj = g.get_repo(f"{owner}/{repo}")
        print(f"\nBranches in {owner}/{repo}:")
        branches = list(repo_obj.get_branches())
        if not branches:
            print("(No branches found or accessible.)")
        else:
            for branch in branches:
                print(f"- {branch.name}")
            print(f"Total branches: {len(branches)}")
        safe_contextual_log('info', f"Listed branches for {owner}/{repo}", context)
    except GithubException as e:
        print(f"Error listing branches: {e}")
        safe_contextual_log('error', f"Error listing branches: {e}", context)
        return
    except Exception as e:
        print(f"Unexpected error listing branches: {e}")
        safe_contextual_log('error', f"Unexpected error listing branches: {e}", context)
        return

    try:
        print(f"\nPull Requests in {owner}/{repo}:")
        prs = list(repo_obj.get_pulls(state='all'))
        if not prs:
            print("(No pull requests found or accessible.)")
        else:
            for pr in prs:
                print(f"- PR #{pr.number}: {pr.title} [{pr.state}] (head: {pr.head.ref})")
            print(f"Total pull requests: {len(prs)}")
        safe_contextual_log('info', f"Listed PRs for {owner}/{repo}", context)
    except GithubException as e:
        print(f"Error listing PRs: {e}")
        safe_contextual_log('error', f"Error listing PRs: {e}", context)
    except Exception as e:
        print(f"Unexpected error listing PRs: {e}")
        safe_contextual_log('error', f"Unexpected error listing PRs: {e}", context) 