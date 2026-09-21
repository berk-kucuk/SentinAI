import os
import subprocess
import requests
from dotenv import load_dotenv

# google-genai (new unified SDK)
from google import genai as _genai
from google.genai import types as _types

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
# Matches Maze AI's default so the two apps share one pulled model.
DEFAULT_OLLAMA_MODEL = "llama3.1"


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


def pick_ollama_model(host: str = None) -> str | None:
    """The local model to use when the user has not named one.

    Prefers the same model Maze AI defaults to, so a machine that already ran
    Maze AI does not have to pull a second one. Falls back to whatever is
    actually installed, and returns None only when Ollama has no models at all.
    """
    models = list_ollama_models(host)
    if not models:
        return None
    for want in (DEFAULT_OLLAMA_MODEL, DEFAULT_OLLAMA_MODEL + ":latest"):
        if want in models:
            return want
    # A tag-less preference still matches "llama3.1:8b" and friends.
    for m in models:
        if m.split(":", 1)[0] == DEFAULT_OLLAMA_MODEL:
            return m
    return models[0]


def initialize_ollama(model_name: str = None, host: str = None) -> _OllamaModelWrapper:
    load_dotenv(os.path.join(get_base_dir(), ".env"))
    host = host or get_ollama_host()
    if not check_ollama_running(host):
        raise RuntimeError(
            f"Ollama service not reachable at {host}. Make sure `ollama serve` is running."
        )
    model_name = model_name or os.getenv("OLLAMA_MODEL") or pick_ollama_model(host)
    if not model_name:
        raise ValueError(
            "Ollama is running but has no models installed. "
            f"Pull one first, e.g. `ollama pull {DEFAULT_OLLAMA_MODEL}`."
        )
    return _OllamaModelWrapper(model_name, host)


def resolve_backend(backend: str = None) -> str:
    """Decide which backend to use when the caller does not name one.

    Maze Linux ships this app on a distribution whose whole promise is that
    nothing leaves the machine unless the user asks. So the local backend is
    the default, and the cloud one is only chosen when the user has actually
    configured it. The order is deliberate:

      1. an explicit argument, then AI_BACKEND — the user said what they want
      2. a reachable local Ollama — private, costs nothing, needs no account
      3. a configured GOOGLE_API_KEY — an existing install keeps working
      4. otherwise local, so the error message points at the private path
    """
    if backend:
        return backend.lower()
    load_dotenv(os.path.join(get_base_dir(), ".env"))
    env = os.getenv("AI_BACKEND")
    if env:
        return env.lower()
    if check_ollama_running():
        return "ollama"
    if os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    return "ollama"


def initialize_model(backend: str = None, model_name: str = None, host: str = None):
    """Backend-agnostic entry point used by passgenai/osintai/chatbot.

    backend: "gemini" or "ollama". If omitted, resolve_backend() picks one,
    preferring the local service — see the note there.
    """
    load_dotenv(os.path.join(get_base_dir(), ".env"))
    backend = resolve_backend(backend)
    if backend == "ollama":
        return initialize_ollama(model_name, host)
    return initialize_gemini(model_name)


def check_tool_installed(tool_name: str) -> bool:
    try:
        subprocess.run([tool_name, "--help"], check=True, capture_output=True, text=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
