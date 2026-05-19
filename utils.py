import os
import subprocess
from dotenv import load_dotenv

# google-genai (new unified SDK)
from google import genai as _genai
from google.genai import types as _types


def get_base_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


class _ModelWrapper:
    """
    Thin compatibility shim around google-genai Client so that callers
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


def initialize_gemini(model_name: str = None) -> _ModelWrapper:
    load_dotenv(os.path.join(get_base_dir(), ".env"))
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found. Please set your API key in Settings.")
    model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    client = _genai.Client(api_key=api_key)
    return _ModelWrapper(client, model_name)


def check_tool_installed(tool_name: str) -> bool:
    try:
        subprocess.run([tool_name, "--help"], check=True, capture_output=True, text=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
