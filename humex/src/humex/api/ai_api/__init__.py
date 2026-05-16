"""AI API module providing LLM integration with pluggable model support.

This module provides interfaces to various AI models (currently Claude via Claude CLI)
for tasks like chat interactions and metrics requirement translation.

Classes:
- Chat: Class-based chat interface
- TranslateMetrics: Class-based metrics translation interface

Functions (for backward compatibility):
- chat(): Functional chat interface
- translate_metrics(): Functional metrics translation interface
"""

from humex.api.ai_api.chat import Chat
from humex.api.ai_api.translate_metrics import TranslateMetrics

__all__ = ["Chat", "TranslateMetrics"]
