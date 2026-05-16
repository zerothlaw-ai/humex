"""Qwen model implementation for AI API via local Ollama.

The Ollama endpoint defaults to ``http://localhost:11434``. Override with the
``HUMEX_LLM_BASE_URL`` env var to point at a remote Ollama instance.
"""

import os
import requests
from typing import Optional


class QwenModel:
    """Interface to Qwen AI via local Ollama API.

    This class provides methods to interact with Qwen through a locally running
    Ollama server. It handles HTTP requests, error handling, and response parsing.
    """

    BASE_URL = os.environ.get("HUMEX_LLM_BASE_URL", "http://localhost:11434")
    DEFAULT_MODEL = "qwen2.5:0.5b"

    def __init__(self, model_name: Optional[str] = None):
        """Initialize QwenModel with specified model.

        Args:
            model_name: Ollama model name to use (default: "qwen2.5:0.5b").
                       Examples: "qwen2.5:0.5b", "qwen2.5:7b", "qwen2.5-coder:7b"
        """
        self.model_name = model_name or self.DEFAULT_MODEL

    def _call_qwen(self, prompt: str) -> str:
        """Call Qwen via Ollama HTTP API and return the response.

        Args:
            prompt: The full prompt to send to Qwen (including system instructions if needed)

        Returns:
            The text response from Qwen

        Raises:
            ConnectionError: If cannot connect to Ollama server
            requests.exceptions.RequestException: If the API request fails
        """
        url = f"{self.BASE_URL}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
        }

        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()

            result = response.json()
            return result.get("response", "").strip()

        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"Cannot connect to Ollama server at {QwenModel.BASE_URL}. "
                "Please ensure Ollama is running with: ollama serve"
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(
                f"Request to Qwen timed out after 120 seconds. "
                "The model may be overloaded or the prompt too complex."
            )

    def chat(self, message: str, context: Optional[str] = None) -> str:
        """Send a chat message to Qwen and get a response.

        Args:
            message: User's question or message
            context: Optional context about what the user is working on

        Returns:
            Plain text response from Qwen

        Raises:
            ConnectionError: If cannot connect to Ollama server
            Exception: If Qwen API call fails
        """
        context_msg = ""
        if context:
            context_msg = f"(Context: {context}) "

        prompt = f"{context_msg}{message}"

        try:
            reply = self._call_qwen(prompt)
            return reply
        except Exception as e:
            raise Exception(f"Chat failed: {str(e)}")

    def translate_metrics(self, prompt: str) -> str:
        """Translate requirement to metrics YAML configuration using a complete prompt.

        This method accepts a full prompt that combines system knowledge with user requirements.
        The prompt should be properly formatted and include all necessary context about
        monitors, operators, and DAG structure.

        Args:
            prompt: Complete prompt for translation, combining system context and user requirement

        Returns:
            YAML formatted string containing the configuration. Can be directly used
            with humex's analyzer or logic systems.

        Raises:
            ConnectionError: If cannot connect to Ollama server
            Exception: If Qwen API call fails
        """
        try:
            yaml_config = self._call_qwen(prompt)
            return yaml_config
        except Exception as e:
            raise Exception(f"Failed to translate requirement: {str(e)}")



if __name__ == '__main__':
    model = QwenModel()
    response = model.chat("Hello, world!")
    print(response)
