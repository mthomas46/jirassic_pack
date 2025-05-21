import requests
import os
import logging
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_TIMEOUT = 10  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds

class OllamaCodeLlama:
    def __init__(self, model="codellama:latest"):
        self.model = model
        self.logger = logging.getLogger("OllamaCodeLlama")
        self.session = requests.Session()
        retries = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=[502, 503, 504],
            allowed_methods=["POST", "GET"]
        )
        self.session.mount("http://", HTTPAdapter(max_retries=retries))
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def generate(self, prompt, timeout=DEFAULT_TIMEOUT, stream=False):
        payload = {
            "model": self.model,
            "prompt": prompt
        }
        url = f"{OLLAMA_HOST}/api/generate"
        try:
            if stream:
                with self.session.post(url, json=payload, timeout=timeout, stream=True) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if line:
                            yield line.decode('utf-8')
            else:
                resp = self.session.post(url, json=payload, timeout=timeout)
                resp.raise_for_status()
                result = resp.json()
                self.logger.info(f"LLM call succeeded for model={self.model}")
                return result.get("response", result)
        except requests.RequestException as e:
            self.logger.error(f"LLM backend error: {e}")
            if stream:
                yield {"error": f"LLM backend error: {e}"}
            else:
                return {"error": f"LLM backend error: {e}"}

    def get_model_info(self, timeout=DEFAULT_TIMEOUT):
        """Try to get model/version info from Ollama backend."""
        url = f"{OLLAMA_HOST}/api/tags"
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            tags = resp.json().get("models", [])
            for tag in tags:
                if tag.get("name") == self.model or tag.get("name") == self.model.split(':')[0]:
                    return {
                        "model": tag.get("name"),
                        "version": tag.get("digest", "unknown")
                    }
            return {"model": self.model, "version": "unknown"}
        except Exception as e:
            self.logger.error(f"Failed to get model info: {e}")
            return {"model": self.model, "version": "unknown", "error": str(e)}

    def is_backend_available(self, timeout=DEFAULT_TIMEOUT):
        url = f"{OLLAMA_HOST}/api/tags"
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            return True
        except Exception as e:
            self.logger.warning(f"Ollama backend not available: {e}")
            return False

def is_http_api_running():
    try:
        import psutil
    except ImportError:
        return False
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if 'http_api.py' in ' '.join(proc.info['cmdline']):
                return True
        except Exception:
            continue
    return False 