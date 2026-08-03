import os
import subprocess
import requests
from dotenv import load_dotenv

# google-genai (new unified SDK)
from google import genai as _genai
from google.genai import types as _types

DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def get_base_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


class _SimpleResponse:
    """Minimal response wrapper so every backend exposes the same
    `.text` attribute that callers (osintai/passgenai/chatbot) rely on."""

    def __init__(self, text: str):
        self.text = text or ""


class _GeminiModelWrapper:
    """Thin compatibility shim around google-genai Client so that callers
    can still use model.generate_content(prompt) without knowing the
    underlying SDK version.
    """

    def __init__(self, client: _genai.Client, model_name: str):
        self._client = client
        self._model_name = model_name

    def generate_content(self, prompt: str):
        return self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
        )


class _OllamaModelWrapper:
    """Wrapper around a local Ollama service (`/api/generate`) that exposes
    the exact same `generate_content(prompt) -> response.text` interface
    as the Gemini wrapper, so callers don't need to know which backend
    is active.
    """

    def __init__(self, model_name: str, host: str = DEFAULT_OLLAMA_HOST, timeout: int = 300):
        self._model_name = model_name
        self._host = host.rstrip("/")
        self._timeout = timeout

    def generate_content(self, prompt: str):
        try:
            resp = requests.post(
                f"{self._host}/api/generate",
                json={"model": self._model_name, "prompt": prompt, "stream": False},
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama servisine ulaşılamadı ({self._host}): {e}")
        data = resp.json()
        return _SimpleResponse(data.get("response", ""))


# ── Ollama helpers ────────────────────────────────────────────────────────────
def get_ollama_host() -> str:
    load_dotenv(os.path.join(get_base_dir(), ".env"))
    return os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)


def check_ollama_running(host: str = None) -> bool:
    host = (host or get_ollama_host()).rstrip("/")
    try:
        r = requests.get(f"{host}/api/tags", timeout=3)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def list_ollama_models(host: str = None) -> list:
    """Return the model names currently pulled into the local Ollama service.
    Returns an empty list if the service is unreachable."""
    host = (host or get_ollama_host()).rstrip("/")
    try:
        r = requests.get(f"{host}/api/tags", timeout=5)
        r.raise_for_status()
        data = r.json()
        return [m["name"] for m in data.get("models", [])]
    except requests.exceptions.RequestException:
        return []


# ── Backend initializers ─────────────────────────────────────────────────────
def initialize_gemini(model_name: str = None) -> _GeminiModelWrapper:
    load_dotenv(os.path.join(get_base_dir(), ".env"))
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found. Please set your API key in Settings.")
    model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    client = _genai.Client(api_key=api_key)
    return _GeminiModelWrapper(client, model_name)


def initialize_ollama(model_name: str = None, host: str = None) -> _OllamaModelWrapper:
    load_dotenv(os.path.join(get_base_dir(), ".env"))
    host = host or get_ollama_host()
    model_name = model_name or os.getenv("OLLAMA_MODEL")
    if not model_name:
        raise ValueError("No Ollama model selected. Please choose one in Settings.")
    if not check_ollama_running(host):
        raise RuntimeError(
            f"Ollama service not reachable at {host}. Make sure `ollama serve` is running."
        )
    return _OllamaModelWrapper(model_name, host)


def initialize_model(backend: str = None, model_name: str = None, host: str = None):
    """Backend-agnostic entry point used by passgenai/osintai/chatbot.

    backend: "gemini" or "ollama". If omitted, falls back to the AI_BACKEND
    env var (default "gemini"), so existing callers keep working unchanged.
    """
    load_dotenv(os.path.join(get_base_dir(), ".env"))
    backend = (backend or os.getenv("AI_BACKEND", "gemini")).lower()
    if backend == "ollama":
        return initialize_ollama(model_name, host)
    return initialize_gemini(model_name)


def check_tool_installed(tool_name: str) -> bool:
    try:
        subprocess.run([tool_name, "--help"], check=True, capture_output=True, text=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
