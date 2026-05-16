"""
Comprehensive API Facade for humex Framework.

This module provides a single, centralized entry point to all available humex APIs.
Users can discover, understand, and import all public APIs from this single location.

================================================================================
QUICK START - BASIC IMPORTS
================================================================================

    from humex.api.core_apis import (
        ScenarioAPI,
        SimulationAPI,
        ConvertAnalyzerMetricsAPI,
        ComputeAnalyzerMetricsAPI,
        ComputeDagMetricsAPI,
        VisualizeDagAPI,
        MonitorDiscoveryAPI,
        OperatorDiscoveryAPI,
        chat,
        translate_metrics,
    )

================================================================================
AVAILABLE API GROUPS
================================================================================

SCENARIO LOADING APIs
=====================
  • ScenarioAPI
    Load and prepare scenarios from various sources (files, folders, gRPC)

SIMULATION APIs
===============
  • SimulationAPI
    Run simulations from JSON config and map files, generate scenario protobufs

METRICS COMPUTATION APIs
========================
  • ConvertAnalyzerMetricsAPI
    Convert analyzer/logic YAML configs to unified DAG YAML format

  • ComputeAnalyzerMetricsAPI
    End-to-end metrics computation: load scenario → convert analyzer → evaluate

  • ComputeDagMetricsAPI
    End-to-end metrics computation: load scenario → load DAG directly → evaluate

  • VisualizeDagAPI
    Generate PNG/SVG/PDF visualizations of DAG YAML configurations

  • MonitorDiscoveryAPI
    Discover available monitors and their metadata (for frontend UI)

  • OperatorDiscoveryAPI
    Discover available operators and their metadata (for frontend UI)

AI INTEGRATION APIs
===================
  • chat()
    Interactive chat with Claude about humex

  • translate_metrics()
    Translate natural language requirements to metrics YAML configurations

================================================================================
API DETAILS
================================================================================
"""

# Scenario Loading APIs
from .scenario_api import ScenarioAPI

# Simulation APIs
from .simulation_api import (
    RunSimulationAPI,
    RunSimulationWithAnalyzerMetricsAPI,
    RunSimulationWithDagMetricsAPI,
)

# Preview APIs
from .preview_api import KeyframePreviewAPI

# Metrics Computation APIs
from .metrics_api import (
    ConvertAnalyzerMetricsAPI,
    ComputeAnalyzerMetricsAPI,
    ComputeDagMetricsAPI,
    VisualizeDagAPI,
    MonitorDiscoveryAPI,
    OperatorDiscoveryAPI,
    TestDagMetricsAPI,
)

# AI Integration APIs
from .ai_api import Chat, TranslateMetrics, chat, translate_metrics

# Public API exports
__all__ = [
    # Scenario Loading APIs
    "ScenarioAPI",
    # Simulation APIs
    "RunSimulationAPI",
    "RunSimulationWithAnalyzerMetricsAPI",
    "RunSimulationWithDagMetricsAPI",
    # Preview APIs
    "KeyframePreviewAPI",
    # Metrics Computation APIs
    "ConvertAnalyzerMetricsAPI",
    "ComputeAnalyzerMetricsAPI",
    "ComputeDagMetricsAPI",
    "VisualizeDagAPI",
    "MonitorDiscoveryAPI",
    "OperatorDiscoveryAPI",
    "TestDagMetricsAPI",
    # AI Integration APIs
    "Chat",
    "TranslateMetrics",
    "chat",
    "translate_metrics",
]
