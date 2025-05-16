from flask import Flask, request, jsonify
from jirassicpack.jira_client import JiraClient
from jirassicpack.config import ConfigLoader
import os
import argparse

app = Flask(__name__)

# Load config and initialize Jira client
config = ConfigLoader().get_jira_config()
jira = JiraClient(config['url'], config['email'], config['api_token'])

@app.route('/jira/ticket', methods=['POST'])
def create_ticket():
    """
    Create a new Jira ticket.
    Expects JSON: { "project": "KEY", "summary": "...", "description": "...", "issuetype": "Task" }
    """
    data = request.json
    try:
        payload = {
            "fields": {
                "project": {"key": data["project"]},
                "summary": data["summary"],
                "description": data.get("description", ""),
                "issuetype": {"name": data.get("issuetype", "Task")}
            }
        }
        resp = jira.post("issue", json=payload)
        return jsonify(resp.json()), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/jira/ticket/<issue_id>', methods=['PUT'])
def update_ticket(issue_id):
    """
    Update an existing Jira ticket.
    Expects JSON: { "fields": { ... } }
    """
    data = request.json
    try:
        resp = jira.put(f"issue/{issue_id}", json=data)
        return jsonify({"status": "updated", "issue_id": issue_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/jira/ticket/<issue_id>', methods=['GET'])
def get_ticket(issue_id):
    """
    Get a Jira ticket by issue ID.
    """
    try:
        ticket = jira.get_task(issue_id)
        return jsonify(ticket), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 404

@app.route('/jira/search', methods=['GET'])
def search_issues():
    """
    Search Jira issues by JQL.
    Query parameter: ?jql=JQL_STRING
    Returns a list of issues matching the JQL.
    """
    jql = request.args.get('jql')
    if not jql:
        return jsonify({"error": "Missing required 'jql' query parameter."}), 400
    try:
        issues = jira.search_issues(jql)
        return jsonify(issues), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint. Returns status ok if the server is running.
    """
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Jirassic Pack API Server")
    parser.add_argument('--port', type=int, default=int(os.environ.get('JIRASSICPACK_API_PORT', 5050)), help='Port to run the API server on')
    args = parser.parse_args()
    app.run(port=args.port, debug=True) 