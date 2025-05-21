import os
import sys
import subprocess
import time
import requests
import psutil
import yaml
import pprint

def load_ports():
    llm_port, http_port = 5001, 5000
    if os.path.exists("config.yaml"):
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
            llm_port = config.get('servers', {}).get('llm_api_port', 5001)
            http_port = config.get('servers', {}).get('http_api_port', 5000)
    if llm_port == http_port:
        print(f"[WARN] Ports conflict. Changing llm_api_port to {llm_port+1}")
        llm_port += 1
    return llm_port, http_port

def is_process_running(script_name):
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if script_name in ' '.join(proc.info['cmdline']):
                return True
        except Exception:
            continue
    return False

def log_cli_startup_context(server_name, port):
    cli_log_file = 'jirassicpack_cli.log'
    log_lines = []
    log_lines.append(f"[CLI-STARTUP] Starting {server_name} on port {port}")
    log_lines.append(f"[CLI-STARTUP] Python executable: {sys.executable}")
    log_lines.append(f"[CLI-STARTUP] CWD: {os.getcwd()}")
    log_lines.append(f"[CLI-STARTUP] sys.path: {sys.path}")
    log_lines.append(f"[CLI-STARTUP] ENV LLM_API_LOG_FILE: {os.environ.get('LLM_API_LOG_FILE')}")
    log_lines.append(f"[CLI-STARTUP] ENV OLLAMA_HOST: {os.environ.get('OLLAMA_HOST')}")
    log_lines.append(f"[CLI-STARTUP] ENV LLM_API_KEY: {os.environ.get('LLM_API_KEY')}")
    config_path = os.path.abspath('config.yaml')
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
            log_lines.append(f"[CLI-STARTUP] config.yaml contents:\n{pprint.pformat(config)}")
        except Exception as e:
            log_lines.append(f"[CLI-STARTUP] Failed to load config.yaml: {e}")
    else:
        log_lines.append("[CLI-STARTUP] config.yaml not found.")
    for line in log_lines:
        print(line)
    with open(cli_log_file, 'a') as f:
        for line in log_lines:
            f.write(line + '\n')

def start_server(script_path, port, health_endpoint, script_name, module_name=None):
    log_cli_startup_context(script_name, port)
    if is_process_running(script_name):
        print(f"{script_name} is already running. No action taken.")
        return
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if module_name:
        cmd = [sys.executable, '-m', module_name]
        log_file = f'{module_name}_subprocess.log'
    else:
        cmd = [sys.executable, script_path]
        log_file = f'{script_name}_subprocess.log'
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["PYTHONPATH"] = project_root
    with open(log_file, 'a') as out:
        subprocess.Popen(cmd, cwd=project_root, env=env, stdout=out, stderr=out)
    print(f"Started {script_name} in the background on port {port}. Output: {log_file}")
    url = f"http://localhost:{port}{health_endpoint}"
    for attempt in range(10):
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                print(f"{script_name} is healthy and running on port {port}.")
                return
            else:
                print(f"[WARN] Health endpoint returned non-ok status. Retrying...")
        except Exception:
            print(f"[INFO] Waiting for {script_name} to become healthy (attempt {attempt+1}/10)...")
            time.sleep(1)
    print(f"[ERROR] {script_name} health check failed after waiting.")

def stop_server(script_name):
    running = False
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if script_name in ' '.join(proc.info['cmdline']):
                proc.terminate()
                running = True
        except Exception:
            continue
    if running:
        print(f"Stopped all {script_name} processes.")
    else:
        print(f"No {script_name} processes found to stop. No action taken.") 