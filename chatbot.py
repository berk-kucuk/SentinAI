import requests
from google import genai as _genai
from google.genai import types as _types

from utils import (get_ollama_host, check_ollama_running, resolve_backend,
                   pick_ollama_model)

SYSTEM_INSTRUCTION = (
    "You are SentinAI, an expert cybersecurity assistant. "
    "You have deep knowledge of: OSINT techniques, password security and authentication, "
    "network security and penetration testing concepts, malware analysis and threat intelligence, "
    "security frameworks (MITRE ATT&CK, NIST, ISO 27001), CTF challenges, and defensive security "
    "best practices. Provide accurate, detailed, and practical guidance. Always emphasize ethical use. "
    "When discussing offensive techniques, frame them in a defensive or authorized testing context."
)


class Chatbot:
    """Backend-agnostic chat wrapper. Supports:
      - backend="gemini": uses google-genai chat sessions (multi-turn, server-side history)
      - backend="ollama": uses a local Ollama service's /api/chat endpoint,
        with conversation history kept client-side.
    """

    def __init__(
        self,
        backend: str = None,
        api_key: str = None,
        model_name: str = None,
        ollama_host: str = None,
        timeout: int = 300,
    ):
        # No backend named means "pick the private one if you can" — see
        # utils.resolve_backend().
        self.backend = resolve_backend(backend)
        self._model_name = model_name
        self._timeout = timeout

        if self.backend == "ollama":
            self._ollama_host = (ollama_host or get_ollama_host()).rstrip("/")
            if not check_ollama_running(self._ollama_host):
                raise RuntimeError(
                    f"Ollama service not reachable at {self._ollama_host}. "
                    "Make sure `ollama serve` is running."
                )
            model_name = model_name or pick_ollama_model(self._ollama_host)
            if not model_name:
                raise ValueError(
                    "Ollama is running but has no models installed. "
                    "Pull one first, e.g. `ollama pull llama3.1`."
                )
            self._model_name = model_name
            self._messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
        else:
            if not api_key:
                raise ValueError("API key cannot be empty.")
            self._client = _genai.Client(api_key=api_key)
            self._config = _types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
            self.chat = self._client.chats.create(model=self._model_name, config=self._config)

    def send_message(self, message: str) -> str:
        if not message.strip():
            return ""

        if self.backend == "ollama":
            self._messages.append({"role": "user", "content": message})
            try:
                resp = requests.post(
                    f"{self._ollama_host}/api/chat",
                    json={
                        "model": self._model_name,
                        "messages": self._messages,
                        "stream": False,
                    },
                    timeout=self._timeout,
                )
                resp.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"Ollama servisine ulaşılamadı ({self._ollama_host}): {e}")
            data = resp.json()
            reply = (data.get("message") or {}).get("content", "")
            self._messages.append({"role": "assistant", "content": reply})
            return reply

        response = self.chat.send_message(message)
        return response.text

    def clear_history(self):
        if self.backend == "ollama":
            self._messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
        else:
            self.chat = self._client.chats.create(model=self._model_name, config=self._config)
