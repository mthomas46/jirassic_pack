import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, abort
from .ollama_code_llama import OllamaCodeLlama
from github import Github
from marshmallow import Schema, fields, ValidationError
import yaml
from rich.console import Console
import time
import datetime
import tempfile
import pprint

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max upload
llama = OllamaCodeLlama()
console = Console()

# Persistent logging
LOG_FILE = os.environ.get('LLM_API_LOG_FILE', 'llm_api_server.log')
if not os.path.isabs(LOG_FILE):
    LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), LOG_FILE))
try:
    # Ensure the log file exists
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'a') as f:
            f.write('')
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1000000, backupCount=3)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    logger = logging.getLogger("llm_api")
    logger.info(f"LLM API server starting up. Logging to {LOG_FILE}")
    logger.info("[TEST] Logging is active and log file is writable.")
except Exception as e:
    fallback_log = os.path.join(tempfile.gettempdir(), 'llm_api_server.log')
    handler = RotatingFileHandler(fallback_log, maxBytes=1000000, backupCount=3)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    logger = logging.getLogger("llm_api")
    logger.warning(f"Failed to open log file {LOG_FILE}, using fallback {fallback_log}: {e}")
    logger.info("LLM API server starting up (fallback log)")
    logger.info("[TEST] Logging is active and fallback log file is writable.")

# --- Startup Diagnostics ---
logger.info(f"[DIAGNOSTIC] CWD: {os.getcwd()}")
logger.info(f"[DIAGNOSTIC] sys.path: {sys.path}")
logger.info(f"[DIAGNOSTIC] ENV LLM_API_LOG_FILE: {os.environ.get('LLM_API_LOG_FILE')}")
logger.info(f"[DIAGNOSTIC] ENV OLLAMA_HOST: {os.environ.get('OLLAMA_HOST')}")
logger.info(f"[DIAGNOSTIC] ENV LLM_API_KEY: {os.environ.get('LLM_API_KEY')}")
config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../config.yaml'))
if os.path.exists(config_path):
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        logger.info(f"[DIAGNOSTIC] config.yaml contents:\n{pprint.pformat(config)}")
    except Exception as e:
        logger.warning(f"[DIAGNOSTIC] Failed to load config.yaml: {e}")
else:
    logger.info("[DIAGNOSTIC] config.yaml not found.")

@app.after_request
def after_request_logging(response):
    logger.info(f"[REQUEST] {request.method} {request.path} {response.status_code}")
    return response

# Marshmallow Schemas
class TextSchema(Schema):
    prompt = fields.Str(required=True)

class GithubPRSchema(Schema):
    repo = fields.Str(required=True)
    pr_number = fields.Int(required=True)
    token = fields.Str(required=True)
    prompt = fields.Str(required=False)

# API key requirement is optional: if LLM_API_KEY is not set or is 'changeme', all requests are allowed.
# If set to a real value, require X-API-KEY for all endpoints except /health, /status, /help, and /endpoints.
LLM_API_KEY = os.environ.get('LLM_API_KEY', 'changeme')
@app.before_request
def require_api_key():
    logger.info(f"Incoming request: {request.method} {request.path} from {request.remote_addr}")
    # Always allow public endpoints
    if request.endpoint in ('health', 'status', 'help', 'endpoints'):
        return
    # If API key is not set or is 'changeme', allow all
    if not LLM_API_KEY or LLM_API_KEY == 'changeme':
        return
    # Otherwise, require correct API key
    if request.headers.get('X-API-KEY') != LLM_API_KEY:
        abort(401)

# 2. LLM Usage & Monitoring
@app.route('/llm/stats', methods=['GET'])
def llm_stats():
    # Example stub: return dummy stats
    stats = {
        "requests": 1234,
        "avg_response_time_ms": 150,
        "uptime_seconds": int(time.time() - os.getpid()) if hasattr(os, 'getpid') else None,
        "active_model": getattr(llama, 'model', 'unknown')
    }
    return jsonify(stats)

START_TIME = time.time()
SERVER_NAME = "jirassicpack-llm-api"
SERVER_VERSION = "1.0.0"

@app.route('/status', methods=['GET'])
def status():
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    uptime = int(time.time() - START_TIME)
    info = llama.get_model_info()
    llm_status = 'ready' if info.get('model') and not info.get('error') else 'unavailable'
    resp = {
        'status': 'ok',
        'server': SERVER_NAME,
        'version': SERVER_VERSION,
        'timestamp': now,
        'uptime_seconds': uptime,
        'llm_model': info.get('model', 'unknown'),
        'llm_status': llm_status
    }
    if 'version' in info:
        resp['llm_version'] = info['version']
    if 'error' in info:
        resp['llm_error'] = info['error']
    return jsonify(resp)

@app.route('/health', methods=['GET'])
def health():
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    uptime = int(time.time() - START_TIME)
    info = llama.get_model_info()
    try:
        reply = llama.generate('ping')
        if hasattr(reply, '__iter__') and not isinstance(reply, str):
            reply = ''.join(reply)
        model_name = info.get('model', 'unknown')
        logger.info("/health check successful.")
        return jsonify({
            'status': 'ok',
            'server': SERVER_NAME,
            'version': SERVER_VERSION,
            'timestamp': now,
            'uptime_seconds': uptime,
            'llm_model': model_name,
            'llm_status': 'ready',
            'llm_version': info.get('version', 'unknown'),
            'llm_reply': reply
        })
    except Exception as e:
        logger.error(f"/health check failed: {e}")
        return jsonify({
            'status': 'error',
            'server': SERVER_NAME,
            'version': SERVER_VERSION,
            'timestamp': now,
            'uptime_seconds': uptime,
            'llm_model': info.get('model', 'unknown'),
            'llm_status': 'unavailable',
            'llm_version': info.get('version', 'unknown'),
            'error': str(e)
        }), 500

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

@app.route('/generate/text', methods=['POST'])
def generate_text():
    stream = request.args.get('stream', 'false').lower() == 'true'
    try:
        data = request.get_json()
        validated = TextSchema().load(data)
        prompt = validated['prompt']
        if stream:
            def generate():
                for chunk in llama.generate(prompt, stream=True):
                    yield chunk if isinstance(chunk, str) else str(chunk)
            return app.response_class(generate(), mimetype='text/plain')
        else:
            result = llama.generate(prompt)
            logger.info(f"/generate/text called. Prompt: {prompt[:50]}...")
            return jsonify({'response': result})
    except ValidationError as ve:
        logger.error(f"Validation error in /generate/text: {ve.messages}")
        return jsonify({'error': ve.messages}), 400
    except Exception as e:
        console.print_exception()
        logger.error(f"Internal server error in /generate/text: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/generate/file', methods=['POST'])
def generate_file():
    stream = request.args.get('stream', 'false').lower() == 'true'
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Missing file'}), 400
        file = request.files['file']
        prompt = file.read().decode('utf-8')
        if not prompt.strip():
            return jsonify({'error': 'File is empty'}), 400
        if stream:
            def generate():
                for chunk in llama.generate(prompt, stream=True):
                    yield chunk if isinstance(chunk, str) else str(chunk)
            return app.response_class(generate(), mimetype='text/plain')
        else:
            result = llama.generate(prompt)
            logger.info(f"/generate/file called. File length: {len(prompt)}")
            return jsonify({'response': result})
    except Exception as e:
        console.print_exception()
        logger.error(f"Internal server error in /generate/file: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/generate/github-pr', methods=['POST'])
def generate_github_pr():
    try:
        data = request.get_json()
        validated = GithubPRSchema().load(data)
        repo_name = validated['repo']
        pr_number = validated['pr_number']
        token = validated.get('token')
        prompt_prefix = validated.get('prompt', 'Review the following GitHub pull request diff for bugs, improvements, and best practices.')
        g = Github(token)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        files = pr.get_files()
        diff_summary = []
        for file in files:
            filename = file.filename
            patch = file.patch if hasattr(file, 'patch') else ''
            diff_summary.append(f"File: {filename}\n{patch}")
        diff_text = '\n\n'.join(diff_summary)
        prompt = f"{prompt_prefix}\n\n{diff_text}"
        result = llama.generate(prompt)
        logger.info(f"/generate/github-pr called. Repo: {repo_name}, PR: {pr_number}")
        return jsonify({'response': result})
    except ValidationError as ve:
        logger.error(f"Validation error in /generate/github-pr: {ve.messages}")
        return jsonify({'error': ve.messages}), 400
    except Exception as e:
        console.print_exception()
        logger.error(f"Internal server error in /generate/github-pr: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/endpoints', methods=['GET'])
def list_endpoints():
    endpoints = [
        {"path": "/status", "method": "GET", "description": "Basic server and LLM status (does not call/generate from LLM). Always returns 200."},
        {"path": "/health", "method": "GET", "description": "Tests the LLM backend and returns a reply or error. Always returns 200."},
        {"path": "/logs", "method": "GET", "description": "Get the last 50 lines of the LLM API server log with status, lines, and error info."},
        {"path": "/generate/text", "method": "POST", "description": "Generate text from a prompt using the local LLM. Supports streaming with ?stream=true."},
        {"path": "/generate/file", "method": "POST", "description": "Generate text from a file using the local LLM. Supports streaming with ?stream=true."},
        {"path": "/generate/github-pr", "method": "POST", "description": "Analyze a GitHub PR using the local LLM."},
        {"path": "/endpoints", "method": "GET", "description": "List all available API endpoints."},
    ]
    return jsonify({"endpoints": endpoints}), 200

if __name__ == "__main__":
    # Load port from config.yaml if present
    port = 5001
    if os.path.exists("config.yaml"):
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
            port = config.get('servers', {}).get('llm_api_port', 5001)
    app.run(host="0.0.0.0", port=port, debug=True) 