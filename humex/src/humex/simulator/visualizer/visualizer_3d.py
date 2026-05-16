"""3D Visualizer for autonomous vehicle simulation scenarios.

This module provides 3D visualization of vehicle trajectories, collisions,
and scenario analysis results using matplotlib. The ego vehicle is highlighted
in orange for easy identification.

Note: This module requires matplotlib with a GUI backend (TkAgg or QtAgg) for
interactive visualization. For headless environments, set MPLBACKEND=Agg before
importing, but note that interactive plt.show() will not work.
"""

import os
import gc
import numpy as np

# Lazy imports for matplotlib - only imported when Visualizer is instantiated
_plt = None
_animation = None
_FuncAnimation = None
_Poly3DCollection = None
_patches = None


def _import_matplotlib():
    """Lazily import matplotlib with appropriate backend."""
    global _plt, _animation, _FuncAnimation, _Poly3DCollection, _patches

    if _plt is not None:
        return  # Already imported

    import matplotlib

    # Use TkAgg for interactive visualization, but allow override via environment
    backend = os.environ.get('MPLBACKEND', 'TkAgg')
    try:
        matplotlib.use(backend)
    except Exception:
        # If preferred backend fails, try Agg as fallback
        try:
            matplotlib.use('Agg')
        except Exception:
            pass  # Use whatever default is available

    import matplotlib.pyplot
    import matplotlib.animation
    from matplotlib.animation import FuncAnimation
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import matplotlib.patches

    _plt = matplotlib.pyplot
    _animation = matplotlib.animation
    _FuncAnimation = FuncAnimation
    _Poly3DCollection = Poly3DCollection
    _patches = matplotlib.patches

STATUS_COLOR = {
    "none": 'steelblue',
    "front": 'red',
    "collision": 'darkred',
    "ego": 'orange'}

# Traffic signal state to color mapping
SIGNAL_COLOR = {
    1: 'red',      # LANE_STATE_ARROW_STOP
    2: 'yellow',   # LANE_STATE_ARROW_CAUTION
    3: 'green',    # LANE_STATE_ARROW_GO
    4: 'red',      # LANE_STATE_STOP
    5: 'yellow',   # LANE_STATE_CAUTION
    6: 'green',    # LANE_STATE_GO
    7: 'red',      # LANE_STATE_FLASHING_STOP
    8: 'yellow',   # LANE_STATE_FLASHING_CAUTION
}

class Visualizer(object):
    """3D visualizer for autonomous vehicle scenarios.

    Renders vehicle movements, collisions, and metric results in a 3D environment.
    The ego vehicle is displayed in orange while other vehicles use status-based colors.
    """

    def __init__(self, scenario, metric_results=None, analyzer_results=None, ego_id=None, analyzer_name=None, dag_result=None, dag_name=None):
        """Initialize the 3D visualizer.

        Args:
            scenario: Simulation scenario containing vehicle trajectories
            metric_results (optional): Analysis results for overlay display
            analyzer_results (optional): Legacy analyzer results (deprecated, use dag_result)
            ego_id (optional): Override ego vehicle ID for highlighting
            analyzer_name (optional): Name of analyzer config (legacy, use dag_name)
            dag_result (optional): DagResult protobuf object with DAG evaluation results
            dag_name (optional): Name of DAG config for loading protobuf results
        """
        # Lazy import matplotlib when Visualizer is first instantiated
        _import_matplotlib()

        self.scenario = scenario
        self.map = scenario.map
        self.metric_results = metric_results
        self.analyzer_results = None
        self.ego_id = ego_id if ego_id is not None else scenario.ego_id
        self.dag_result = dag_result

        # Convert DagResult to analyzer_results format for metrics visualization
        if dag_result:
            self._convert_dag_result_to_analyzer_format(dag_result)
        else:
            # Fall back to legacy analyzer_results if provided
            self.analyzer_results = analyzer_results

        # Load protobuf results for accurate threshold-based coloring (legacy support)
        self.protobuf_results = None

        # Create figure with subplots for 3D scene and metrics
        self.fig = _plt.figure(figsize=(12, 10))

        # 3D visualization on top (takes up 85% of height)
        self.ax = self.fig.add_subplot(4, 1, (1, 3), projection='3d')
        self.ax.set_axis_off()

        # Metrics visualization underneath (takes up 15% of height)
        self.metrics_ax = self.fig.add_subplot(4, 1, 4)
        self.metrics_ax.set_title('Metrics Results', fontsize=10, weight='bold')

        # Adjust subplot spacing to minimize gaps
        _plt.subplots_adjust(hspace=0.05)

        # Initialize Objects
        self.artists = []
        self.objects = dict()
        self.plot_map(ax=self.ax)

        # Performance optimization variables
        self.frame_count = 0
        self.gc_interval = 60  # Run garbage collection every 60 frames
        self.max_trajectory_frames = 100  # Limit trajectory history
        self.object_trajectories = {}  # Track object trajectories for cleanup

        # Initialize metrics visualization
        if self.analyzer_results:
            self.setup_metrics_visualization()

        # self.metric_text = self.ax.text(0, 0, '', color='red', fontsize=10, weight='bold', ha='center')

    def _convert_dag_result_to_analyzer_format(self, dag_result):
        """Convert DagResult protobuf to analyzer_results dictionary format.

        Transforms the generic DagResult protobuf into a format compatible with
        the existing metrics visualization code.

        Args:
            dag_result: DagResult protobuf object from DAG evaluation
        """
        self.analyzer_results = {}

        # Extract frame values from each leaf node result
        for leaf_result in dag_result.leaf_node_results:
            # Use node name or node_id as the metric identifier
            metric_name = leaf_result.name if leaf_result.name else f"node_{leaf_result.node_id}"

            # Extract frame values from frame_results
            frame_values = []
            for frame_result in leaf_result.frame_results:
                # Use frame_result boolean as the frame value
                frame_values.append(frame_result.frame_result)

            # Store in analyzer_results format expected by visualization
            self.analyzer_results[metric_name] = {
                'frame_value': frame_values
            }

    def setup_metrics_visualization(self):
        """Setup the metrics visualization panel with all metric colors displayed upfront."""
        if not self.analyzer_results:
            return
            
        # Get metric names and frame count
        self.metric_names = list(self.analyzer_results.keys())
        self.num_frames = len(self.scenario.timestamps)
        
        # Display all metric bars immediately
        bar_height = 0.6  # Reduced gap between metrics
        
        for i, metric_name in enumerate(self.metric_names):
            details = self.analyzer_results[metric_name]['frame_value']  # Renamed from 'details'
            
            # Create and display all bars for this metric immediately
            for frame_idx, frame_value in enumerate(details):
                # Determine color using protobuf threshold results if available
                color = self._get_frame_color(metric_name, frame_idx, frame_value)
                
                # Create rectangle and add to plot immediately
                rect = _patches.Rectangle((frame_idx, i - bar_height/2), 1, bar_height,
                                       facecolor=color, edgecolor='none', linewidth=0, alpha=0.8)
                self.metrics_ax.add_patch(rect)
        
        # Setup metrics axes
        self.metrics_ax.set_xlim(0, self.num_frames)
        self.metrics_ax.set_ylim(-0.1, len(self.metric_names) - 0.9)
        self.metrics_ax.set_xlabel('Frame', fontsize=9)
        self.metrics_ax.set_yticks(range(len(self.metric_names)))
        self.metrics_ax.set_yticklabels(self.metric_names, fontsize=7)
        self.metrics_ax.grid(True, alpha=0.2)
        
        # Make axes labels and ticks smaller for compact display
        self.metrics_ax.tick_params(axis='both', which='major', labelsize=7)
        self.metrics_ax.tick_params(axis='x', which='major', pad=2)
        
        # Initialize the play needle (vertical line) - this will move during animation to show current frame
        self.play_needle = self.metrics_ax.axvline(x=0, color='blue', linewidth=3, alpha=0.9, zorder=10)
        
        # Add frame/time indicator text
        self.frame_text = self.metrics_ax.text(0.02, 0.95, '', transform=self.metrics_ax.transAxes, 
                                             fontsize=8, weight='bold', ha='left', va='top',
                                             bbox=dict(boxstyle='round,pad=0.3', facecolor='lightblue', alpha=0.8))
        
        # Add legend
        legend_elements = [
            _patches.Patch(color='green', label='Pass'),
            _patches.Patch(color='red', label='Fail'),
            _patches.Patch(color='gray', label='None'),
            _patches.Patch(color='orange', label='Error')
        ]
        self.metrics_ax.legend(handles=legend_elements, loc='upper right', fontsize=6, 
                              frameon=True, fancybox=False, shadow=False, framealpha=0.8)

    def _get_frame_color(self, metric_name, frame_idx, frame_value):
        """Get the appropriate color for a metric frame based on evaluation result.

        Args:
            metric_name: Name of the metric
            frame_idx: Frame index
            frame_value: Evaluation result value (boolean or numeric)

        Returns:
            str: Color string ('green', 'red', 'gray')
        """
        # Map frame_value to color
        # Boolean values: True = green (pass), False = red (fail)
        # Numeric values: > 0 = green, <= 0 = red
        # None = gray (no result)
        if frame_value is None:
            return 'gray'
        elif isinstance(frame_value, bool):
            return 'green' if frame_value else 'red'
        else:
            # For numeric values, assume > 0 is pass, <= 0 is fail
            return 'green' if frame_value > 0 else 'red'

    def update_metrics_needle(self, current_frame):
        """Update only the play needle position and frame indicator - all metric colors are already displayed."""
        if not self.analyzer_results:
            return
        
        # Update play needle position (all bars are already displayed)
        self.play_needle.set_xdata([current_frame, current_frame])
        
        # Update frame indicator text
        if hasattr(self, 'frame_text'):
            frame_time = current_frame * 0.1  # Assuming 10Hz frame rate
            self.frame_text.set_text(f'Frame: {current_frame}\nTime: {frame_time:.1f}s')

    def cleanup_artists(self):
        """Aggressively clean up matplotlib artists to prevent memory accumulation."""
        for artist in self.artists:
            try:
                if hasattr(artist, 'remove'):
                    artist.remove()
                # Force deletion of artist references
                del artist
            except (ValueError, AttributeError):
                # Artist may already be removed or invalid
                pass
        
        # Clear the artists list and force garbage collection of the list
        self.artists.clear()
        
        # Limit trajectory history for all tracked objects
        self.limit_trajectory_history()
    
    def limit_trajectory_history(self):
        """Limit the trajectory history to prevent memory accumulation."""
        for obj_id in list(self.object_trajectories.keys()):
            if obj_id in self.object_trajectories:
                trajectory = self.object_trajectories[obj_id]
                if len(trajectory) > self.max_trajectory_frames:
                    # Keep only the most recent frames
                    self.object_trajectories[obj_id] = trajectory[-self.max_trajectory_frames:]
                    
        # Clean up trajectories for objects that no longer exist
        if self.frame_count % (self.gc_interval * 2) == 0:  # Less frequent cleanup
            current_frame = self.scenario.get_frame_by_index(min(self.frame_count, len(self.scenario.timestamps) - 1))
            active_obj_ids = set(current_frame.obj_list.keys())
            inactive_obj_ids = set(self.object_trajectories.keys()) - active_obj_ids
            for obj_id in inactive_obj_ids:
                del self.object_trajectories[obj_id]

    def plot_map(self, ax, extra_points=[]):
        segments = self.map.get_segments(centerline=False)
        for pts in segments:
            if len(pts) <= 0:
                continue
            x, y= zip(*[(x, y) for x, y, *_ in pts])
            ax.plot(x, y, 'k')
        for pt in extra_points:
            ax.plot(pt[0], pt[1], 'b.')

    def render_traffic_signals(self, frame_idx):
        """Render colored lane polygons based on traffic signal states.

        Args:
            frame_idx: Current frame index for getting timestamp and signal states
        """
        # Check if map has signal data
        if not self.map.has_signals():
            return

        # Get current timestamp
        if frame_idx >= len(self.scenario.timestamps):
            return
        timestamp = self.scenario.timestamps[frame_idx]

        # Get all signal states for this timestamp
        signal_frame = self.map.get_signal_frame(timestamp)
        if signal_frame is None:
            return

        # Initialize counters for debug output
        rendered_count = 0
        skipped_missing_lane = 0

        # Render each lane with a signal
        for lane_id, signal_state in signal_frame.items():
            # Skip unknown states or states without color mapping
            if signal_state not in SIGNAL_COLOR:
                continue

            # Get lane data
            if lane_id not in self.map.map_data.lanes:
                skipped_missing_lane += 1
                continue
            lane = self.map.map_data.lanes[lane_id]
            rendered_count += 1

            # Extract left boundary points
            left_points = []
            for seg in lane.left_boundary:
                for pt in seg.points:
                    left_points.append([pt.x, pt.y, 0.0])  # Use ground level (z=0)

            # Extract right boundary points
            right_points = []
            for seg in lane.right_boundary:
                for pt in seg.points:
                    right_points.append([pt.x, pt.y, 0.0])

            # Skip if boundaries are empty
            if len(left_points) == 0 or len(right_points) == 0:
                continue

            # Create polygon vertices by connecting left and right boundaries
            # Go forward along left boundary, then backward along right boundary
            vertices = left_points + list(reversed(right_points))

            # Create filled polygon
            color = SIGNAL_COLOR[signal_state]
            polygon = _Poly3DCollection(
                [vertices],
                facecolors=color,
                edgecolors='none',
                alpha=0.3,  # Semi-transparent so map lines show through
                zorder=0    # Render below vehicles
            )

            self.ax.add_collection3d(polygon)
            self.artists.append(polygon)

        # Debug: Print rendering summary on first frame
        if frame_idx == 0:
            print(f"[Signal Debug] Rendered {rendered_count} lanes, Skipped {skipped_missing_lane} lanes (not in map)")

    def update(self, frame_idx):
        # Increment frame counter for performance tracking
        self.frame_count += 1

        # Aggressive memory cleanup every frame to prevent accumulation
        self.cleanup_artists()

        # Periodic garbage collection to free up memory
        if self.frame_count % self.gc_interval == 0:
            gc.collect()

        # Render traffic signals (colored lane polygons)
        self.render_traffic_signals(frame_idx)

        frame = self.scenario.get_frame_by_index(frame_idx)

        ego_x, ego_y, ego_z = None, None, None
        
        # Get front vehicle ID for this frame if available
        front_vehicle_id = None
        if (self.analyzer_results and
            'FrontVehicleDetection' in self.analyzer_results and
            frame_idx < len(self.analyzer_results['FrontVehicleDetection']['frame_value'])):
            front_vehicle_id = self.analyzer_results['FrontVehicleDetection']['frame_value'][frame_idx]  # Renamed from 'details'
        
        for obj_id, obj in frame.obj_list.items():
            sp = obj.sp
            # self.objects[obj_id].set_xy([sp.bbox.rear_left.x, sp.bbox.rear_left.y])
            if obj_id == self.ego_id:  #TODO check ego id
                ego_x, ego_y, ego_z = sp.position.x, sp.position.y, sp.position.z
            fl = [obj.bbox.front_left.x, obj.bbox.front_left.y]
            fr = [obj.bbox.front_right.x, obj.bbox.front_right.y]
            rl = [obj.bbox.rear_left.x, obj.bbox.rear_left.y]
            rr = [obj.bbox.rear_right.x, obj.bbox.rear_right.y]
            faces = self.create_cuboid(fl, fr, rl, rr, obj.height)
            
            # Determine vehicle color based on role
            if obj_id == self.ego_id:
                color = STATUS_COLOR["ego"]  # Orange for ego vehicle
            elif obj_id == front_vehicle_id and front_vehicle_id is not None:
                color = STATUS_COLOR["front"]  # Red for front vehicle
            else:
                color = STATUS_COLOR[obj.status]  # Status-based color for other vehicles
            
            # Create cuboid with optimized settings for performance
            cuboid = _Poly3DCollection(
                verts=faces,
                facecolors=color,
                edgecolors='black',
                linewidths=0.5,  # Reduced line width for performance
                alpha=0.7
            )
            self.ax.add_collection3d(cuboid)
            self.artists.append(cuboid)

            obj_x, obj_y, obj_z = obj.sp.position.x, obj.sp.position.y, obj.sp.position.z

            # Auto-detect if heading is in degrees or radians based on typical value ranges
            # Degrees: typically -360 to 360, Radians: typically -π to π (≈ -3.14 to 3.14)
            if abs(obj.sp.heading.yaw) > 10.0:  # Likely degrees (outside typical radian range)
                yaw_rad = np.radians(obj.sp.heading.yaw)  # Convert degrees to radians
            else:
                yaw_rad = obj.sp.heading.yaw  # Already in radians

            # Create heading arrow with reduced complexity
            arrow = self.create_heading_arrow(self.ax, obj.sp.position.to_tuple(), yaw_rad)
            self.artists.append(arrow)
            
            # Add ID number text on top of bounding box (reduced font size for performance)
            text_z = obj_z + obj.height + 1.0  # Position text above the object
            id_text = self.ax.text(obj_x, obj_y, text_z, str(obj_id), 
                                  fontsize=6, ha='center', va='bottom',  # Reduced font size
                                  color='gray', weight='normal')
            self.artists.append(id_text)
            
            # Track object position in trajectory (with memory limits)
            if obj_id not in self.object_trajectories:
                self.object_trajectories[obj_id] = []
            
            # Only keep limited trajectory history
            trajectory = self.object_trajectories[obj_id]
            trajectory.append((obj_x, obj_y, obj_z))
            if len(trajectory) > self.max_trajectory_frames:
                self.object_trajectories[obj_id] = trajectory[-self.max_trajectory_frames:]
        # self.ax.plot([ego_x, ego_y], 'ro')
        zoom = 30.0
        if ego_x is None:
            return

        self.ax.set_xlim(ego_x - zoom, ego_x + zoom)
        self.ax.set_ylim(ego_y - zoom, ego_y + zoom)
        self.ax.set_zlim(ego_z - zoom, ego_z + zoom)
        # self.ax.view_init(elev=20, azim=-90)

        # Update metrics needle position (all bars are already displayed)
        if self.analyzer_results:
            self.update_metrics_needle(frame_idx)

        # print metric result
        # if self.metric_results[frame_idx]:
        #     self.metric_text.set_text('Collision!')
        # else:
        #     self.metric_text.set_text('None')
        # self.metric_text.set_position((ego_x, ego_y + 10))
        #
        # return self.objects

    def create_cuboid(self,  fl, fr, rl, rr, height):
        vertices = np.array([
            [rr[0], rr[1], 0.0],
            [fr[0], fr[1], 0.0],
            [fl[0], fl[1], 0.0],
            [rl[0], rl[1], 0.0],
            [rr[0], rr[1], height],
            [fr[0], fr[1], height],
            [fl[0], fl[1], height],
            [rl[0], rl[1], height],
        ])
        faces = [
            [vertices[j] for j in [0, 1, 2, 3]],
            [vertices[j] for j in [4, 5, 6, 7]],
            [vertices[j] for j in [0, 1, 5, 4]],
            [vertices[j] for j in [2, 3, 7, 6]],
            [vertices[j] for j in [1, 2, 6, 5]],
            [vertices[j] for j in [0, 3, 7, 4]],
        ]
        return faces

    def create_heading_arrow(self, ax, center, yaw_rad, length=5.0, color='red'):
        """
        Create a simplified 3D line (arrow) indicating heading direction based on yaw.
        Optimized for performance with reduced complexity.
        """
        x, y, z = center
        dx = np.cos(yaw_rad) * length
        dy = np.sin(yaw_rad) * length
        dz = 0

        # Use simpler quiver with better visibility
        arrow = ax.quiver(x, y, z, dx, dy, dz, color=color,
                         linewidth=2.0, arrow_length_ratio=0.3,
                         normalize=False)
        return arrow

    def run(self, rtf=1.0, video_path=None, show=True):
        """Run the visualization.

        Args:
            rtf (float): Real-time factor (1.0 = real-time, 0.5 = 2x speed, 2.0 = half speed)
            video_path (str, optional): Path to save video file. If None, video is not saved.
            show (bool): Whether to display the animation window (default: True)
        """
        try:
            # Set up performance-optimized animation
            ani = _FuncAnimation(self.fig,
                                self.update,
                                frames=len(self.scenario.timestamps),
                                interval=self.scenario.interval*1000*rtf,
                                repeat=False,
                                blit=False,  # Disable blitting for 3D (not supported)
                                cache_frame_data=False)  # Disable frame caching to save memory

            if video_path is not None:
                print('Saving video ...')
                # Calculate effective FPS based on rtf factor
                base_fps = 1.0 / self.scenario.interval  # Original scenario FPS (typically 10 Hz = 0.1s interval)
                effective_fps = base_fps / rtf  # Adjust FPS by rtf factor

                print(f'RTF: {rtf}, Base FPS: {base_fps:.1f}, Video FPS: {effective_fps:.1f}')

                # Use RTF-adjusted video writer settings
                writer = _animation.FFMpegWriter(fps=effective_fps, bitrate=1800)
                ani.save(video_path, writer=writer)
                print(f'Video saved to: {video_path}')

            if show:
                _plt.show()
            else:
                # If not showing, we need to render frames for video saving
                # Draw all frames without displaying
                if video_path is None:
                    print("Warning: show=False but no video_path provided. No output will be generated.")

        finally:
            # Cleanup after animation completes or fails
            self.cleanup_visualization()
    
    def cleanup_visualization(self):
        """Final cleanup to free memory after visualization."""
        # Clear all artists
        self.cleanup_artists()
        
        # Clear trajectory data
        self.object_trajectories.clear()
        
        # Clear matplotlib figure and axes
        if hasattr(self, 'fig') and self.fig is not None:
            _plt.close(self.fig)
            
        # Force garbage collection
        gc.collect()
        
        print("Visualization cleanup completed.")
