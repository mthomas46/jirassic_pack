import os
from jirassicpack.features.ticket_discussion_summary import call_local_llm_text, call_local_llm_file, call_local_llm_github_pr
import questionary
import requests

def test_local_llm(params=None, user_email=None, batch_index=None, unique_suffix=None):
    """
    Interactive feature to test the local LLM endpoints with a prompt, file, github-pr, or health check.
    """
    print("\n🦖 Test Local LLM Endpoint 🦖\n")
    method = questionary.select(
        "How would you like to test the local LLM?",
        choices=[
            "Send text prompt",
            "Send file",
            "Test GitHub PR endpoint",
            "Check health",
            "Abort"
        ],
        default="Send text prompt"
    ).ask()
    if method == "Abort":
        print("Aborted.")
        return
    if method == "Send text prompt":
        prompt = questionary.text("Enter your prompt for the local LLM:").ask()
        if not prompt:
            print("No prompt entered. Aborting.")
            return
        try:
            response = call_local_llm_text(prompt)
            print("\n--- LLM Response ---\n")
            print(response)
        except Exception as e:
            print(f"Error calling local LLM: {e}")
    elif method == "Send file":
        file_path = questionary.path("Enter the path to the file to send:").ask()
        if not file_path or not os.path.isfile(file_path):
            print("Invalid file path. Aborting.")
            return
        try:
            response = call_local_llm_file(file_path)
            print("\n--- LLM Response ---\n")
            print(response)
        except Exception as e:
            print(f"Error calling local LLM: {e}")
    elif method == "Test GitHub PR endpoint":
        repo = questionary.text("Enter the GitHub repo (owner/repo):").ask()
        pr_number = questionary.text("Enter the PR number:").ask()
        token = questionary.password("Enter your GitHub token:").ask()
        custom_prompt = questionary.text("Enter a custom prompt (optional):").ask()
        if not repo or not pr_number or not token:
            print("Missing required input. Aborting.")
            return
        try:
            pr_number_int = int(pr_number)
        except ValueError:
            print("PR number must be an integer. Aborting.")
            return
        try:
            prompt_arg = custom_prompt if custom_prompt.strip() else None
            response = call_local_llm_github_pr(repo, pr_number_int, token, prompt=prompt_arg)
            print("\n--- LLM Response ---\n")
            print(response)
        except Exception as e:
            print(f"Error calling local LLM GitHub PR endpoint: {e}")
    elif method == "Check health":
        try:
            resp = requests.get("http://localhost:5000/health")
            resp.raise_for_status()
            data = resp.json()
            print("\n--- LLM Health ---\n")
            print(f"Status: {data.get('status')}")
            if 'llm_reply' in data:
                print(f"LLM reply: {data['llm_reply']}")
            if 'error' in data:
                print(f"Error: {data['error']}")
        except Exception as e:
            print(f"Error calling health endpoint: {e}")

def prompt_test_local_llm_options(opts, jira=None):
    # No options needed for this feature
    return {} 