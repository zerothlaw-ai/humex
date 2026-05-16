"""Base class for vehicle behavior handlers."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from ...components.statepoint import StatePoint


class BaseBehavior(ABC):
    """Abstract base class for behavior handlers.

    Defines the interface that all behavior implementations must follow.
    Behaviors are responsible for generating vehicle trajectories during simulation.
    """

    def __init__(self, keystates: List[StatePoint], scenario, obj_id: int = None):
        """Initialize behavior.

        Args:
            keystates: List of StatePoints defining the behavior
            scenario: Parent scenario for timing information
            obj_id: Object ID for generated StatePoints
        """
        self.keystates = keystates if keystates else []
        self.scenario = scenario
        self.obj_id = obj_id
        self.interpolated_states: Dict[int, StatePoint] = {}

    @abstractmethod
    def get_state_at_time(self, timestamp: int) -> Optional[StatePoint]:
        """Get state at specific timestamp.

        Args:
            timestamp: Target timestamp (nanoseconds)

        Returns:
            StatePoint at the given time, or None if vehicle should not be present
        """
        pass

    @abstractmethod
    def get_trajectory(self) -> List[StatePoint]:
        """Get complete trajectory as list of StatePoints.

        Returns:
            List of StatePoints sorted by timestamp
        """
        pass

    @abstractmethod
    def get_keystate_times(self) -> List[int]:
        """Get the calculated timestamps for each keystate.

        Returns:
            List of timestamps (nanoseconds) for each keystate
        """
        pass
