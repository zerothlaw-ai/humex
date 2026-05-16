"""Claude CLI model implementation for AI API."""

import subprocess
from typing import Optional


class ClaudeCLIModel:
    """Interface to Claude AI via Claude Code CLI.

    This class provides methods to interact with Claude through the Claude Code CLI.
    It handles subprocess management, error handling, and response parsing.
    """

    @staticmethod
    def _call_claude(prompt: str) -> str:
        """Call Claude CLI with a prompt and return the response.

        Args:
            prompt: The full prompt to send to Claude (including system instructions if needed)

        Returns:
            The text response from Claude

        Raises:
            FileNotFoundError: If Claude CLI is not installed
            subprocess.CalledProcessError: If the Claude CLI command fails
        """
        try:
            result = subprocess.run(
                ["claude", "--print", prompt],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=120
            )

            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else result.stdout
                raise subprocess.CalledProcessError(
                    result.returncode,
                    "claude --print",
                    output=result.stdout,
                    stderr=result.stderr
                )

            return result.stdout.strip()

        except FileNotFoundError:
            raise FileNotFoundError(
                "Claude CLI not found. Please ensure Claude Code CLI is installed and available in PATH. "
                "Install with: npm install -g @anthropic-ai/claude"
            )

    @classmethod
    def chat(cls, message: str, context: Optional[str] = None) -> str:
        """Send a chat message to Claude and get a response.

        Args:
            message: User's question or message
            context: Optional context about what the user is working on

        Returns:
            Plain text response from Claude

        Raises:
            FileNotFoundError: If Claude CLI is not installed
            Exception: If Claude CLI call fails
        """
        context_msg = ""
        if context:
            context_msg = f"(Context: {context}) "

        prompt = f"{context_msg}{message}"

        try:
            reply = cls._call_claude(prompt)
            return reply
        except Exception as e:
            raise Exception(f"Chat failed: {str(e)}")

    @classmethod
    def translate_metrics(cls, prompt: str) -> str:
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
            FileNotFoundError: If Claude CLI is not installed
            Exception: If Claude CLI call fails
        """
        try:
            yaml_config = cls._call_claude(prompt)
            return yaml_config
        except Exception as e:
            raise Exception(f"Failed to translate requirement: {str(e)}")


if __name__=='__main__':
    x = ClaudeCLIModel.chat(message="hi, what question did i just ask you")
    print(x)