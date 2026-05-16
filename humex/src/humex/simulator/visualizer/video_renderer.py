"""2D bird's-eye video renderer for AV scenarios.

Generates MP4 preview videos from scenario data (converted or simulated).
Uses matplotlib with the Agg backend so it works headless (no GUI required).

Usage:
    from humex.simulator.visualizer.video_renderer import render_scenario_video
    render_scenario_video(scenario, "output.mp4")
"""

import os
import numpy as np

# Force Agg backend before any matplotlib import — this module is headless-only
os.environ.setdefault('MPLBACKEND', 'Agg')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter


# Vehicle colors
EGO_COLOR = '#FF8C00'       # Orange
OTHER_COLOR = '#4682B4'     # Steel blue
PEDESTRIAN_COLOR = '#9370DB' # Medium purple
CYCLIST_COLOR = '#20B2AA'   # Light sea green
TRUCK_COLOR = '#CD853F'     # Peru

# Map colors
LANE_BOUNDARY_COLOR = '#555555'
LANE_BOUNDARY_ALPHA = 0.6
CENTERLINE_COLOR = '#AAAAAA'
CENTERLINE_ALPHA = 0.3



def _get_vehicle_color(obj, ego_id):
    """Get color based on object type and role."""
    if obj.id == ego_id:
        return EGO_COLOR
    obj_type = getattr(obj, 'object_type', 'car')
    if obj_type == 'pedestrian':
        return PEDESTRIAN_COLOR
    if obj_type == 'cyclist':
        return CYCLIST_COLOR
    if obj_type == 'truck':
        return TRUCK_COLOR
    return OTHER_COLOR


def _get_vehicle_alpha(obj, ego_id):
    """Ego is fully opaque, others are slightly transparent."""
    return 0.9 if obj.id == ego_id else 0.6


def _rotated_rect(x, y, yaw, length, width):
    """Compute 4 corners of a rotated rectangle (vehicle footprint).

    Returns corners in order: rear-left, rear-right, front-right, front-left
    suitable for matplotlib Polygon.
    """
    cos_yaw = np.cos(yaw)
    sin_yaw = np.sin(yaw)

    # Half dimensions
    hl = length / 2.0
    hw = width / 2.0

    # Corners relative to center (front is +x in body frame)
    corners_body = np.array([
        [-hl, -hw],  # rear-left
        [-hl,  hw],  # rear-right
        [ hl,  hw],  # front-right
        [ hl, -hw],  # front-left
    ])

    # Rotation matrix
    rot = np.array([[cos_yaw, -sin_yaw],
                     [sin_yaw,  cos_yaw]])

    corners_world = corners_body @ rot.T + np.array([x, y])
    return corners_world


def _draw_map(ax, ava_map):
    """Draw lane boundaries on the axes."""
    segments = ava_map.get_segments(centerline=False)
    for pts in segments:
        if len(pts) == 0:
            continue
        xs, ys = zip(*[(x, y) for x, y, *_ in pts])
        ax.plot(xs, ys, color=LANE_BOUNDARY_COLOR, linewidth=0.5,
                alpha=LANE_BOUNDARY_ALPHA, solid_capstyle='round')




def render_scenario_video(
    scenario,
    output_path,
    zoom=50.0,
    dpi=120,
    figsize=(10, 8),
    follow_ego=True,
    show_ids=True,
    show_heading=True,
    show_trails=True,
    trail_length=30,
    title=None,
    bg_color='#1A1A2E',
    speed_factor=1.0,
):
    """Render a scenario to an MP4 video file.

    Args:
        scenario: humex Scenario object with frames, map, ego_id
        output_path: Path to write the .mp4 file
        zoom: Half-width of the view window in meters (centered on ego)
        dpi: Output resolution (120 = ~1200x960 for 10x8 figure)
        figsize: Figure size in inches (width, height)
        follow_ego: If True, camera follows ego vehicle
        show_ids: Show object ID labels
        show_heading: Show heading arrows on vehicles
        show_trails: Show trajectory trails behind vehicles
        trail_length: Number of past frames to show in trail
        title: Optional title text overlay
        bg_color: Background color
        speed_factor: Video speed multiplier (2.0 = 2x speed)
    """
    scenario_fps = 1.0 / scenario.interval  # native frequency (e.g., 10 Hz)
    # TODO: make fps configurable per-deployment or based on scenario duration
    fps = 5

    # Skip frames if requested fps is lower than scenario fps
    frame_step = max(1, round(scenario_fps / fps))
    frame_indices = list(range(0, len(scenario.timestamps), frame_step))
    num_frames = len(frame_indices)

    video_fps = fps * speed_factor
    ego_id = scenario.ego_id

    # Setup figure
    fig, ax = plt.subplots(1, 1, figsize=figsize, facecolor=bg_color)
    ax.set_facecolor(bg_color)
    ax.set_aspect('equal')
    ax.axis('off')

    # Draw static map
    _draw_map(ax, scenario.map)

    # Compute scene bounds from map if not following ego
    if not follow_ego:
        all_pts = []
        for seg_pts in scenario.map.get_segments(centerline=False):
            for pt in seg_pts:
                all_pts.append((pt[0], pt[1]))
        if all_pts:
            xs, ys = zip(*all_pts)
            margin = 10
            ax.set_xlim(min(xs) - margin, max(xs) + margin)
            ax.set_ylim(min(ys) - margin, max(ys) + margin)

    # Trail storage: {obj_id: [(x, y), ...]}
    trails = {}

    # Dynamic artists that get redrawn each frame
    dynamic_artists = []

    # Time overlay text
    time_text = ax.text(
        0.02, 0.97, '', transform=ax.transAxes,
        fontsize=10, color='white', weight='bold',
        verticalalignment='top',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.6),
        zorder=100,
    )

    # Title overlay
    if title:
        ax.text(
            0.5, 0.97, title, transform=ax.transAxes,
            fontsize=12, color='white', weight='bold',
            horizontalalignment='center', verticalalignment='top',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.5),
            zorder=100,
        )

    def update(anim_idx):
        # Remove previous dynamic artists
        for a in dynamic_artists:
            a.remove()
        dynamic_artists.clear()

        frame_idx = frame_indices[anim_idx]
        frame = scenario.get_frame_by_index(frame_idx)

        # Time display
        time_sec = frame_idx * scenario.interval
        total_sec = (len(scenario.timestamps) - 1) * scenario.interval
        time_text.set_text(f'{time_sec:.1f}s / {total_sec:.1f}s')

        ego_x, ego_y = None, None

        for obj_id, obj in frame.obj_list.items():
            sp = obj.sp
            x, y = sp.position.x, sp.position.y

            # Detect yaw units (same heuristic as visualizer_3d)
            yaw = sp.heading.yaw
            if abs(yaw) > 10.0:
                yaw = np.radians(yaw)

            length = obj.length or 4.8
            width = obj.width or 1.7
            color = _get_vehicle_color(obj, ego_id)
            alpha = _get_vehicle_alpha(obj, ego_id)

            # Track ego position
            if obj_id == ego_id:
                ego_x, ego_y = x, y

            # Draw trail
            if show_trails:
                if obj_id not in trails:
                    trails[obj_id] = []
                trails[obj_id].append((x, y))
                if len(trails[obj_id]) > trail_length:
                    trails[obj_id] = trails[obj_id][-trail_length:]

                if len(trails[obj_id]) > 1:
                    txs, tys = zip(*trails[obj_id])
                    # Fade trail from transparent to semi-opaque
                    trail_line, = ax.plot(
                        txs, tys, color=color, linewidth=1.5,
                        alpha=alpha * 0.4, solid_capstyle='round', zorder=2,
                    )
                    dynamic_artists.append(trail_line)

            # Draw vehicle rectangle
            corners = _rotated_rect(x, y, yaw, length, width)
            rect = plt.Polygon(
                corners, closed=True,
                facecolor=color, edgecolor='white',
                linewidth=0.5, alpha=alpha, zorder=5,
            )
            ax.add_patch(rect)
            dynamic_artists.append(rect)

            # Heading arrow (thin line from center toward front)
            if show_heading:
                arrow_len = length * 0.5
                dx = np.cos(yaw) * arrow_len
                dy = np.sin(yaw) * arrow_len
                arrow, = ax.plot(
                    [x, x + dx], [y, y + dy],
                    color='white', linewidth=0.6, alpha=0.7,
                    solid_capstyle='round', zorder=6,
                )
                dynamic_artists.append(arrow)

            # ID label
            if show_ids:
                label = 'EGO' if obj_id == ego_id else str(obj_id)
                txt = ax.text(
                    x, y + width * 0.8, label,
                    fontsize=5, color='white', alpha=0.8,
                    ha='center', va='bottom', weight='bold', zorder=7,
                )
                dynamic_artists.append(txt)

        # Follow ego
        if follow_ego and ego_x is not None:
            ax.set_xlim(ego_x - zoom, ego_x + zoom)
            ax.set_ylim(ego_y - zoom, ego_y + zoom)

        return dynamic_artists

    print(f'Rendering {num_frames} frames at {video_fps:.1f} fps → {output_path}')

    # Diagnostic: dump first-frame state so we can tell if the camera ever
    # locks onto ego, what coordinate frame the scene is in, and whether
    # ego_id type matches any object key in the frames.
    try:
        f0 = scenario.get_frame_by_index(frame_indices[0])
        keys = list(f0.obj_list.keys())
        sample_keys = keys[:3]
        sample_xy = [
            (k, f0.obj_list[k].sp.position.x, f0.obj_list[k].sp.position.y)
            for k in sample_keys
        ]
        ego_in_frame = ego_id in f0.obj_list
        print(
            f'[render-debug] ego_id={ego_id!r} ({type(ego_id).__name__}), '
            f'first-frame keys[:3]={sample_keys} ({type(keys[0]).__name__ if keys else "n/a"}), '
            f'ego_in_first_frame={ego_in_frame}, '
            f'sample positions={sample_xy}'
        )
        if not ego_in_frame and ego_id is not None:
            # Try a string/int swap to detect type-mismatch
            alt = str(ego_id) if not isinstance(ego_id, str) else (
                int(ego_id) if str(ego_id).isdigit() else None
            )
            print(
                f'[render-debug] ego_id type-cast probe: '
                f'alt={alt!r}, alt_in_frame={alt in f0.obj_list if alt is not None else False}'
            )
        ax_xlim_pre = ax.get_xlim()
        ax_ylim_pre = ax.get_ylim()
        print(f'[render-debug] axes limits before animation: x={ax_xlim_pre}, y={ax_ylim_pre}')
    except Exception as _e:
        print(f'[render-debug] diagnostic failed: {_e}')

    ani = FuncAnimation(fig, update, frames=num_frames, interval=1, repeat=False)
    writer = FFMpegWriter(fps=video_fps, bitrate=2400)
    ani.save(output_path, writer=writer, dpi=dpi)

    print(
        f'[render-debug] axes limits after animation: '
        f'x={ax.get_xlim()}, y={ax.get_ylim()}'
    )
    plt.close(fig)
    print(f'Video saved: {output_path}')


def render_scenario_thumbnail(
    scenario,
    output_path,
    frame_index=None,
    zoom=50.0,
    dpi=120,
    figsize=(10, 8),
    follow_ego=True,
    show_ids=True,
    show_heading=True,
    bg_color='#1A1A2E',
):
    """Render a single frame of a scenario to a PNG thumbnail.

    Args:
        scenario: humex Scenario object with frames, map, ego_id
        output_path: Path to write the .png file
        frame_index: Which frame to render. None = middle frame.
        zoom: Half-width of the view window in meters
        dpi: Output resolution
        figsize: Figure size in inches
        follow_ego: If True, center on ego vehicle
        show_ids: Show object ID labels
        show_heading: Show heading lines on vehicles
        bg_color: Background color
    """
    num_frames = len(scenario.timestamps)
    ego_id = scenario.ego_id

    if frame_index is None:
        frame_index = num_frames // 2

    frame_index = max(0, min(frame_index, num_frames - 1))

    fig, ax = plt.subplots(1, 1, figsize=figsize, facecolor=bg_color)
    ax.set_facecolor(bg_color)
    ax.set_aspect('equal')
    ax.axis('off')

    # Draw map
    _draw_map(ax, scenario.map)

    # Draw all vehicle trajectories as faded lines (full scenario overview)
    obj_positions = {}  # {obj_id: [(x, y), ...]}
    for i in range(num_frames):
        f = scenario.get_frame_by_index(i)
        for obj_id, obj in f.obj_list.items():
            if obj_id not in obj_positions:
                obj_positions[obj_id] = []
            obj_positions[obj_id].append((obj.sp.position.x, obj.sp.position.y))

    for obj_id, pts in obj_positions.items():
        if len(pts) < 2:
            continue
        xs, ys = zip(*pts)
        color = EGO_COLOR if obj_id == ego_id else OTHER_COLOR
        ax.plot(xs, ys, color=color, linewidth=0.8, alpha=0.3, solid_capstyle='round', zorder=2)

    # Draw vehicles at the selected frame
    frame = scenario.get_frame_by_index(frame_index)
    ego_x, ego_y = None, None

    for obj_id, obj in frame.obj_list.items():
        sp = obj.sp
        x, y = sp.position.x, sp.position.y
        yaw = sp.heading.yaw
        if abs(yaw) > 10.0:
            yaw = np.radians(yaw)

        length = obj.length or 4.8
        width = obj.width or 1.7
        color = _get_vehicle_color(obj, ego_id)
        alpha = _get_vehicle_alpha(obj, ego_id)

        if obj_id == ego_id:
            ego_x, ego_y = x, y

        corners = _rotated_rect(x, y, yaw, length, width)
        rect = plt.Polygon(
            corners, closed=True,
            facecolor=color, edgecolor='white',
            linewidth=0.5, alpha=alpha, zorder=5,
        )
        ax.add_patch(rect)

        if show_heading:
            arrow_len = length * 0.5
            dx = np.cos(yaw) * arrow_len
            dy = np.sin(yaw) * arrow_len
            ax.plot([x, x + dx], [y, y + dy],
                    color='white', linewidth=0.6, alpha=0.7,
                    solid_capstyle='round', zorder=6)

        if show_ids:
            label = 'EGO' if obj_id == ego_id else str(obj_id)
            ax.text(x, y + width * 0.8, label,
                    fontsize=5, color='white', alpha=0.8,
                    ha='center', va='bottom', weight='bold', zorder=7)

    if follow_ego and ego_x is not None:
        ax.set_xlim(ego_x - zoom, ego_x + zoom)
        ax.set_ylim(ego_y - zoom, ego_y + zoom)

    fig.savefig(output_path, dpi=dpi, bbox_inches='tight', pad_inches=0.1, facecolor=bg_color)
    plt.close(fig)
    print(f'Thumbnail saved: {output_path}')
