"""High-level API for humex framework.

This module provides convenient Python functions and classes for analyzing scenarios,
loading scenarios, converting metrics configs, and interacting with humex via natural language.

Classes:
- ScenarioAPI: Load scenarios from various sources
- ConvertAnalyzerMetricsAPI: Convert analyzer configs to DAG format
- ComputeAnalyzerMetricsAPI: End-to-end metrics computation
- Chat: LLM chat interface
- TranslateMetrics: Natural language to metrics config translator

Functions (for backward compatibility):
- chat(): Functional chat interface
- translate_metrics(): Functional metrics translation interface
"""

from .scenario_api import ScenarioAPI
from .metrics_api import ConvertAnalyzerMetricsAPI, ComputeAnalyzerMetricsAPI
from .ai_api import Chat, TranslateMetrics

__all__ = [
    'ScenarioAPI',
    'ConvertAnalyzerMetricsAPI',
    'ComputeAnalyzerMetricsAPI',
    'Chat',
    'TranslateMetrics',
]
