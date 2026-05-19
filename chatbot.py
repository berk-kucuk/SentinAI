from google import genai as _genai
from google.genai import types as _types

SYSTEM_INSTRUCTION = (
    "You are SentinAI, an expert cybersecurity assistant. "
    "You have deep knowledge of: OSINT techniques, password security and authentication, "
    "network security and penetration testing concepts, malware analysis and threat intelligence, "
    "security frameworks (MITRE ATT&CK, NIST, ISO 27001), CTF challenges, and defensive security "
    "best practices. Provide accurate, detailed, and practical guidance. Always emphasize ethical use. "
    "When discussing offensive techniques, frame them in a defensive or authorized testing context."
)


class Chatbot:
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        if not api_key:
            raise ValueError("API key cannot be empty.")
        self._client = _genai.Client(api_key=api_key)
        self._model_name = model_name
        self._config = _types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
        self.chat = self._client.chats.create(model=self._model_name, config=self._config)

    def send_message(self, message: str) -> str:
        if not message.strip():
            return ""
        response = self.chat.send_message(message)
        return response.text

    def clear_history(self):
        self.chat = self._client.chats.create(model=self._model_name, config=self._config)
