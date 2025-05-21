"""
Production-ready Flask API for Code Llama, designed to be run with Gunicorn for multi-threaded/multi-process serving.
Example:
    gunicorn -w 2 --threads 4 -b 0.0.0.0:5000 http_api:app
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, abort
from github import Github
import difflib
from marshmallow import Schema, fields, ValidationError
import sys
import socket
import multiprocessing
from loguru import logger
from rich.console import Console
from dotenv import load_dotenv
import yaml
import time
import platform
import datetime
import psutil
from jirassicpack.jira_client import JiraClient
from jirassicpack.config import ConfigLoader

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Persistent logging
LOG_FILE = os.environ.get('OLLAMA_LOG_FILE', 'ollama_server.log')
handler = RotatingFileHandler(LOG_FILE, maxBytes=1000000, backupCount=3)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max upload

API_KEY = os.environ.get('OLLAMA_API_KEY', 'changeme')

# Load config.yaml for fallback
CONFIG_PATH = 'config.yaml'
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
else:
    config = {}

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') or config.get('github', {}).get('token')
logger.info(f"GITHUB_TOKEN loaded: {'yes' if GITHUB_TOKEN else 'no'}")

console = Console()

# --- JIRA INTEGRATION ENDPOINTS ---
jira_config = ConfigLoader().get_jira_config()
jira = JiraClient(jira_config['url'], jira_config['email'], jira_config['api_token'])

# API key requirement is optional: if OLLAMA_API_KEY is not set or is 'changeme', all requests are allowed.
# If set to a real value, require X-API-KEY for all endpoints except /health, /help, and /endpoints.
@app.before_request
def require_api_key():
    logger.info(f"Incoming request: {request.method} {request.path} from {request.remote_addr}")
    # Always allow public endpoints
    if request.endpoint in ('health', 'help', 'endpoints'):
        return
    # If API key is not set or is 'changeme', allow all
    if not API_KEY or API_KEY == 'changeme':
        return
    # Otherwise, require correct API key
    if request.headers.get('X-API-KEY') != API_KEY:
        abort(401)

# Marshmallow Schemas
class TextSchema(Schema):
    prompt = fields.Str(required=True)

class GithubPRSchema(Schema):
    repo = fields.Str(required=True)
    pr_number = fields.Int(required=True)
    token = fields.Str(required=True)
    prompt = fields.Str(required=False)

@app.route('/help', methods=['GET'])
def help():
    info = {
        "endpoints": {
            "/generate/text": "POST JSON {prompt}",
            "/generate/file": "POST multipart/form-data file=@...",
            "/generate/github-pr": "POST JSON {repo, pr_number, token, prompt?}",
            "/health": "GET",
            "/help": "GET"
        },
        "auth": "Set X-API-KEY header to your API key."
    }
    return jsonify(info)

START_TIME = time.time()
SERVER_NAME = "jirassicpack-http-api"
SERVER_VERSION = "1.0.0"

@app.route('/health', methods=['GET'])
def health():
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    uptime = int(time.time() - START_TIME)
    return jsonify({
        'status': 'ok',
        'server': SERVER_NAME,
        'version': SERVER_VERSION,
        'timestamp': now,
        'uptime_seconds': uptime
    })

@app.route('/logs', methods=['GET'])
def logs():
    try:
        with open(LOG_FILE) as f:
            lines = f.readlines()
        return jsonify({
            'status': 'ok',
            'lines': len(lines[-50:]),
            'log': lines[-50:]
        })
    except FileNotFoundError:
        return jsonify({'status': 'error', 'error': 'Log file not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/endpoints', methods=['GET'])
def list_endpoints():
    """Return a list of all available API endpoints and their descriptions."""
    endpoints = [
        {"path": "/status", "method": "GET", "description": "Basic server status (does not call any backend). Always returns 200."},
        {"path": "/health", "method": "GET", "description": "Health check for the API server. Returns status, server, version, timestamp, uptime."},
        {"path": "/logs", "method": "GET", "description": "Get the last 50 lines of the HTTP API server log with status, lines, and error info."},
        {"path": "/jira/projects", "method": "GET", "description": "List all Jira projects."},
        {"path": "/jira/users", "method": "GET", "description": "List all Jira users."},
        {"path": "/jira/boards", "method": "GET", "description": "List all Jira boards."},
        {"path": "/jira/sprints", "method": "GET", "description": "List all sprints for a board (requires board_id param)."},
        {"path": "/jira/issue/transition", "method": "POST", "description": "Transition a Jira issue to a new status."},
        {"path": "/jira/issue/comment", "method": "POST", "description": "Add a comment to a Jira issue."},
        {"path": "/jira/issue/assign", "method": "POST", "description": "Assign a Jira issue to a user."},
        {"path": "/analytics/export", "method": "GET", "description": "Export analytics in various formats (stub)."},
        {"path": "/auth/validate", "method": "POST", "description": "Validate an API key."},
        {"path": "/auth/rotate", "method": "POST", "description": "Rotate API key (stub)."},
        {"path": "/system/info", "method": "GET", "description": "Get server and system info."},
        {"path": "/system/reload", "method": "POST", "description": "Reload config or restart server (stub)."},
        {"path": "/docs", "method": "GET", "description": "API documentation (stub)."},
        {"path": "/config", "method": "GET", "description": "Show current config with sensitive info masked."},
        {"path": "/endpoints", "method": "GET", "description": "List all available API endpoints."},
    ]
    return jsonify({"endpoints": endpoints}), 200

def mask_sensitive(value):
    if not value or not isinstance(value, str):
        return value
    if len(value) <= 8:
        return '*' * len(value)
    return '*' * (len(value) - 8) + value[-8:]

@app.route('/config', methods=['GET'])
def get_config():
    """Return the current config, masking sensitive API info except for the last 8 characters."""
    # Load config.yaml if present
    config_data = dict(config) if config else {}
    # Add env overrides
    config_data.update({
        'OLLAMA_API_KEY': os.environ.get('OLLAMA_API_KEY'),
        'GITHUB_TOKEN': os.environ.get('GITHUB_TOKEN'),
        'OLLAMA_HOST': os.environ.get('OLLAMA_HOST'),
        'LLM_API_PORT': os.environ.get('LLM_API_PORT'),
    })
    # Mask sensitive fields
    sensitive_keys = ['api_key', 'token', 'OLLAMA_API_KEY', 'GITHUB_TOKEN', 'OPENAI_API_KEY']
    def mask_dict(d):
        for k, v in d.items():
            if isinstance(v, dict):
                d[k] = mask_dict(v)
            elif any(s in k.lower() for s in sensitive_keys):
                d[k] = mask_sensitive(v)
        return d
    masked = mask_dict(dict(config_data))
    return jsonify(masked), 200

def log_startup_context():
    mode = 'production (Gunicorn)' if 'gunicorn' in sys.argv[0] else 'development (Flask app.run)'
    host = os.environ.get('HOST', '0.0.0.0')
    port = os.environ.get('PORT', '5000')
    pid = os.getpid()
    cpu_count = multiprocessing.cpu_count()
    logger.info(f"=== HTTP API Server Startup ===")
    logger.info(f"Mode: {mode}")
    logger.info(f"Host: {host}")
    logger.info(f"Port: {port}")
    logger.info(f"Process ID: {pid}")
    logger.info(f"CPU count: {cpu_count}")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info(f"API key set: {'yes' if API_KEY != 'changeme' else 'no'}")
    logger.info(f"GitHub token set: {'yes' if GITHUB_TOKEN else 'no'}")
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        logger.info(f"Hostname: {hostname} | IP: {ip}")
    except Exception as e:
        logger.info(f"Could not determine hostname/IP: {e}")
    logger.info("Server is starting up...")
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        logger.info(f"Endpoint: {rule.endpoint} | Methods: {methods} | Path: {rule}")
    logger.info("Server ready to accept requests.")

# Call this function at startup for both app.run and Gunicorn
log_startup_context()

# 5. Advanced Analytics Export
@app.route('/analytics/export', methods=['GET'])
def analytics_export():
    # Example: export analytics as JSON (stub)
    # In real use, accept params for type/format
    data = {"message": "Export analytics as JSON, CSV, Markdown, or PDF (not implemented)"}
    return jsonify(data)

# 7. Security & Auth
@app.route('/auth/validate', methods=['POST'])
def auth_validate():
    api_key = request.headers.get('X-API-KEY')
    valid = api_key == API_KEY
    return jsonify({"valid": valid})

@app.route('/auth/rotate', methods=['POST'])
def auth_rotate():
    # Stub: In real use, rotate and return new API key
    return jsonify({"message": "API key rotation not implemented in demo."}), 501

# 8. System & Server Info
@app.route('/system/info', methods=['GET'])
def system_info():
    info = {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "server_time": datetime.datetime.utcnow().isoformat() + 'Z',
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "log_file": LOG_FILE,
        "api_version": "1.0.0"
    }
    return jsonify(info)

@app.route('/system/reload', methods=['POST'])
def system_reload():
    # Stub: In real use, reload config or restart server
    return jsonify({"message": "Reload not implemented. Please restart the server manually."}), 501

# 9. Documentation & Help (Swagger/OpenAPI placeholder)
@app.route('/docs', methods=['GET'])
def docs():
    # Stub: In real use, serve Swagger/OpenAPI docs
    return jsonify({"message": "API documentation not implemented. See /endpoints for available routes."})

@app.route('/jira/projects', methods=['GET'])
def jira_projects():
    try:
        resp = jira.get('project/search')
        return jsonify(resp.get('values', resp)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/jira/users', methods=['GET'])
def jira_users():
    try:
        users = jira.get('users/search', params={'maxResults': 1000})
        return jsonify(users), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/jira/boards', methods=['GET'])
def jira_boards():
    try:
        boards = jira.list_boards()
        return jsonify(boards), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/jira/sprints', methods=['GET'])
def jira_sprints():
    board_id = request.args.get('board_id')
    if not board_id:
        return jsonify({'error': 'Missing required board_id parameter'}), 400
    try:
        sprints = jira.list_sprints(board_id)
        return jsonify(sprints), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/jira/issue/transition', methods=['POST'])
def jira_issue_transition():
    data = request.json
    issue_id = data.get('issue_id')
    transition_id = data.get('transition_id')
    if not issue_id or not transition_id:
        return jsonify({'error': 'Missing required issue_id or transition_id'}), 400
    try:
        resp = jira.post(f'issue/{issue_id}/transitions', json={"transition": {"id": transition_id}})
        return jsonify({'status': 'transitioned', 'issue_id': issue_id, 'transition_id': transition_id}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/jira/issue/comment', methods=['POST'])
def jira_issue_comment():
    data = request.json
    issue_id = data.get('issue_id')
    comment = data.get('comment')
    if not issue_id or not comment:
        return jsonify({'error': 'Missing required issue_id or comment'}), 400
    try:
        resp = jira.post(f'issue/{issue_id}/comment', json={"body": comment})
        return jsonify({'status': 'commented', 'issue_id': issue_id}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/jira/issue/assign', methods=['POST'])
def jira_issue_assign():
    data = request.json
    issue_id = data.get('issue_id')
    account_id = data.get('account_id')
    if not issue_id or not account_id:
        return jsonify({'error': 'Missing required issue_id or account_id'}), 400
    try:
        resp = jira.put(f'issue/{issue_id}/assignee', json={"accountId": account_id})
        return jsonify({'status': 'assigned', 'issue_id': issue_id, 'account_id': account_id}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    log_startup_context()
    # Load port from config.yaml if present
    port = 5000
    if os.path.exists("config.yaml"):
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
            port = config.get('servers', {}).get('http_api_port', 5000)
    app.run(host="0.0.0.0", port=port, debug=True)

# Note: Do NOT use app.run() here. Use Gunicorn to run this app in production. 