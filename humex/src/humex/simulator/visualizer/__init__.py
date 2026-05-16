"""Visualization for autonomous vehicle scenarios.

- Visualizer: Interactive 3D viewer (requires GUI backend)
- render_scenario_video: Headless 2D bird's-eye MP4 renderer

Imports are lazy to avoid loading matplotlib unless visualization is needed.
"""

__all__ = ['Visualizer', 'render_scenario_video', 'render_scenario_thumbnail']


def __getattr__(name):
    """Lazy import visualizers only when accessed."""
    if name == 'Visualizer':
        from .visualizer_3d import Visualizer
        return Visualizer
    if name == 'render_scenario_video':
        from .video_renderer import render_scenario_video
        return render_scenario_video
    if name == 'render_scenario_thumbnail':
        from .video_renderer import render_scenario_thumbnail
        return render_scenario_thumbnail
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
