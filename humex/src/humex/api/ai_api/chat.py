"""Chat API for humex framework interactions."""

from typing import Optional

from humex.api.ai_api.models._claude_cli import ClaudeCLIModel
from humex.api.ai_api.models._qwen import QwenModel


class Chat:
    """Chat interface for humex-related queries.

    Provides a conversational interface for asking questions and getting advice
    about humex framework, scenarios, metrics, and analysis.
    """

    def __init__(self, model: str = "claude_cli", qwen_model: Optional[str] = None):
        """Initialize Chat with specified model.

        Args:
            model: Model to use for chat. Supports "claude_cli" (default) or "qwen".
            qwen_model: Ollama model name when using "qwen" (default: "qwen2.5:0.5b").
                       Examples: "qwen2.5:0.5b", "qwen2.5:7b", "qwen2.5-coder:7b"

        Raises:
            ValueError: If an unsupported model is specified
        """
        if model not in ("claude_cli", "qwen"):
            raise ValueError(
                f"Unsupported model: {model}. Supported models: 'claude_cli', 'qwen'"
            )
        self.model = model
        self._qwen_instance = QwenModel(qwen_model) if model == "qwen" else None

    def send(self, message: str, context: Optional[str] = None) -> str:
        """Send a chat message and get a response.

        Args:
            message: User's question or message
            context: Optional context about what the user is working on
                    (e.g., "scenario analysis", "metric configuration")

        Returns:
            Plain text response string from the selected model

        Raises:
            FileNotFoundError: If Claude CLI is not installed (when using claude_cli)
            Exception: If the model call fails

        Example:
            >>> chat_api = Chat()
            >>> response = chat_api.send("How do I analyze a scenario?")
            >>> print(response)
            # Returns helpful response about analyzing scenarios

            >>> response = chat_api.send("What metrics should I track?", context="vehicle safety")
            >>> print(response)
            # Returns response tailored to vehicle safety metrics
        """
        if self.model == "claude_cli":
            return ClaudeCLIModel.chat(message, context)
        elif self.model == "qwen":
            return self._qwen_instance.chat(message, context)
        else:
            raise ValueError(
                f"Unsupported model: {self.model}. Supported models: 'claude_cli', 'qwen'"
            )


# Convenience function for backward compatibility
def chat(
    message: str,
    model: str = "claude_cli",
    context: Optional[str] = None,
    qwen_model: Optional[str] = None
) -> str:
    """Convenience function for chat interactions.

    This function provides backward compatibility with the functional API.
    For new code, consider using the Chat class directly.

    Args:
        message: User's question or message
        model: Model to use for chat (default: "claude_cli"). Supports "claude_cli" or "qwen".
        context: Optional context about what the user is working on
        qwen_model: Ollama model name when using "qwen" (default: "qwen2.5:0.5b")

    Returns:
        Plain text response string from the selected model
    """
    chat_api = Chat(model=model, qwen_model=qwen_model)
    return chat_api.send(message, context=context)
