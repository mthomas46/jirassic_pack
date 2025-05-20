"""
Local LLM server management for Jirassic Pack CLI.
"""
import os
import sys
import subprocess
import threading
import time
import shutil
import requests
from jirassicpack.utils.message_utils import error, info
from jirassicpack.utils.output_utils import rich_panel, rich_info, rich_success, rich_error
from jirassicpack.utils.logging import contextual_log

# Track started subprocesses for clean shutdown
LLM_PROCESSES = []

def is_process_running(process_name):
    """Check if a process with the given name is running."""
    try:
        import psutil
    except ImportError:
        print("[ERROR] The 'psutil' package is required for process management. Please install it with 'pip install psutil'.")
        return False
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if process_name in ' '.join(proc.info['cmdline']):
                return True
        except Exception:
            continue
    return False

def get_llm_status():
    """Return a status indicator for the local LLM server."""
    try:
        import psutil
    except ImportError:
        return '🔴 (psutil not installed)'
    ollama_running = is_process_running('ollama')
    http_api_running = is_process_running('http_api.py')
    if ollama_running and http_api_running:
        return '🟢'
    return '🔴'

def update_llm_menu():
    """Update the CLI menu with the current LLM server status indicator."""
    from jirassicpack.cli_menu import FEATURE_GROUPS
    status = get_llm_status()
    FEATURE_GROUPS["Test Connection"] = [
        ("🧪 Test connection to Jira", "test_connection"),
        (f"🦖 Start Local LLM Server {status}", "start_local_llm_server"),
        ("🛑 Stop Local LLM Server", "stop_local_llm_server"),
        ("🪵 View Local LLM Logs", "view_local_llm_logs"),
        ("🦖 Test Local LLM", "test_local_llm"),
        ("👀 Live Tail Local LLM Logs", "live_tail_local_llm_logs"),
    ]

def start_local_llm_server():
    """Start the local LLM server (ollama and http_api.py) if not already running."""
    print("🦖 Starting local LLM server...")
    if not shutil.which("ollama"):
        print("[ERROR] 'ollama' is not installed or not in PATH.")
        return
    if not is_process_running("ollama"): 
        try:
            p = subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            LLM_PROCESSES.append(p)
            print("Started 'ollama serve' in the background.")
        except Exception as e:
            print(f"[ERROR] Failed to start 'ollama serve': {e}")
    else:
        print("'ollama serve' is already running.")
    ollama_dir = os.path.abspath(os.path.join(os.getcwd(), "../Ollama7BPoc"))
    http_api_path = os.path.join(ollama_dir, "http_api.py")
    if not os.path.exists(http_api_path):
        print(f"[ERROR] Could not find http_api.py at {http_api_path}")
        return
    if not is_process_running("http_api.py"):
        try:
            p = subprocess.Popen(["python", http_api_path], cwd=ollama_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            LLM_PROCESSES.append(p)
            print("Started 'http_api.py' in the background.")
        except Exception as e:
            print(f"[ERROR] Failed to start 'http_api.py': {e}")
    else:
        print("'http_api.py' is already running.")
    # Health check
    print("Checking local LLM health endpoint...")
    try:
        for _ in range(10):
            try:
                resp = requests.get("http://localhost:5000/health", timeout=2)
                if resp.status_code == 200 and resp.json().get("status") == "ok":
                    print("🟢 Local LLM health check passed!")
                    break
                else:
                    print("[WARN] Health endpoint returned non-ok status.")
            except Exception:
                print("[INFO] Waiting for local LLM to become healthy...")
                time.sleep(1)
        else:
            print("[ERROR] Local LLM health check failed after waiting.")
    except Exception as e:
        print(f"[ERROR] Health check error: {e}")
    print("🦖 Local LLM server startup attempted. Use 'Test Local LLM' to verify health.")

def stop_local_llm_server():
    """Stop all local LLM server processes (ollama and http_api.py)."""
    print("🛑 Stopping local LLM server...")
    # First, try to kill any processes we started
    for p in LLM_PROCESSES:
        try:
            print(f"[DEBUG] Terminating process PID {p.pid}")
            p.terminate()
            p.wait(timeout=5)
            print(f"[DEBUG] Process PID {p.pid} terminated.")
        except Exception as e:
            print(f"[ERROR] Failed to terminate process PID {getattr(p, 'pid', '?')}: {e}")
    LLM_PROCESSES.clear()
    # Fallback: kill by name (legacy)
    try:
        import psutil
    except ImportError:
        print("[ERROR] The 'psutil' package is required for process management. Please install it with 'pip install psutil'.")
        return
    stopped = False
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            cmd = ' '.join(proc.info['cmdline'])
            if 'ollama' in cmd or 'http_api.py' in cmd:
                print(f"[DEBUG] Terminating process by name: {cmd}")
                proc.terminate()
                stopped = True
        except Exception:
            continue
    if stopped:
        print("🛑 Local LLM server processes terminated.")
    else:
        print("No local LLM server processes found to stop.")

def view_local_llm_logs():
    """Display the last 20 lines of ollama.log and http_api.log."""
    ollama_log = os.path.expanduser("~/.ollama/ollama.log")
    ollama_dir = os.path.abspath(os.path.join(os.getcwd(), "../Ollama7BPoc"))
    http_api_log = os.path.join(ollama_dir, "llm_api.log")
    print("--- ollama.log (last 20 lines) ---")
    if os.path.exists(ollama_log):
        with open(ollama_log) as f:
            lines = f.readlines()
            print(''.join(lines[-20:]))
    else:
        print("No ollama.log found.")
    print("--- http_api.log (last 20 lines) ---")
    if os.path.exists(http_api_log):
        with open(http_api_log) as f:
            lines = f.readlines()
            print(''.join(lines[-20:]))
    else:
        print("No http_api.log found.")

def live_tail_file(filepath, label):
    """Live tail a log file, printing new lines as they are written."""
    print(f"--- {label} (live tail, Ctrl+C to exit) ---")
    last_inode = None
    try:
        while True:
            try:
                if not os.path.exists(filepath):
                    print(f"No {label} found at {filepath}. Retrying in 2s...")
                    time.sleep(2)
                    continue
                with open(filepath, 'r') as f:
                    f.seek(0, os.SEEK_END)
                    last_inode = os.fstat(f.fileno()).st_ino
                    while True:
                        line = f.readline()
                        if line:
                            print(line, end='')
                        else:
                            time.sleep(0.5)
                            # Check for log rotation/truncation
                            try:
                                if os.stat(filepath).st_ino != last_inode:
                                    print(f"\n[INFO] {label} was rotated or truncated. Re-opening...")
                                    break
                            except Exception:
                                break
            except PermissionError:
                print(f"[ERROR] Permission denied for {label} at {filepath}. Retrying in 2s...")
                time.sleep(2)
                continue
            except FileNotFoundError:
                print(f"[ERROR] {label} not found at {filepath}. Retrying in 2s...")
                time.sleep(2)
                continue
            except Exception as e:
                print(f"[ERROR] Unexpected error tailing {label}: {e}. Retrying in 2s...")
                time.sleep(2)
                continue
    except KeyboardInterrupt:
        print(f"\nStopped tailing {label}.")
    except Exception as e:
        print(f"[ERROR] Fatal error in tailing {label}: {e}")

def live_tail_local_llm_logs():
    """Live tail both ollama.log and http_api.log in separate threads."""
    ollama_log = os.path.expanduser("~/.ollama/ollama.log")
    ollama_dir = os.path.abspath(os.path.join(os.getcwd(), "../Ollama7BPoc"))
    http_api_log = os.path.join(ollama_dir, "llm_api.log")
    def tail1():
        try:
            live_tail_file(ollama_log, "ollama.log")
        except Exception as e:
            print(f"[ERROR] ollama.log tailing thread: {e}")
    def tail2():
        try:
            live_tail_file(http_api_log, "http_api.log")
        except Exception as e:
            print(f"[ERROR] http_api.log tailing thread: {e}")
    print("Tailing both ollama.log and http_api.log. Press Ctrl+C to stop.")
    t1 = threading.Thread(target=tail1, daemon=True)
    t2 = threading.Thread(target=tail2, daemon=True)
    t1.start()
    t2.start()
    try:
        while t1.is_alive() or t2.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped live tailing logs.")
    except Exception as e:
        print(f"[ERROR] Fatal error in live tailing logs: {e}")

def view_ollama_server_log():
    pass

def live_tail_ollama_server_log():
    pass

def search_ollama_server_log():
    pass

def filter_ollama_server_log():
    pass

def analyze_logs_and_generate_report():
    pass 