from ..utils.math_helper import *


class StatePoint(object):

    def __init__(self,
                 position=(0, 0, 0), velocity=(0, 0, 0), acceleration=(0, 0, 0), heading=(0, 0, 0),
                 timestamp=None, frameid=None, obj_id=None,
                 length=4.8, width=1.7):

        self.timestamp = timestamp
        self.frameid = frameid
        self.obj_id = obj_id

        self.length, self.width = length, width
        self.position = Position(position)
        self.velocity = Velocity(velocity)
        self.acceleration = Acceleration(acceleration)
        self.heading = Heading(heading)

        # self.bbox = BoundingBox2D(statepoint=self)

    def update_position(self, position):
        if isinstance(position, tuple):
            self.position = Position(position)
        elif isinstance(position, Position):
            self.position = position
        else:
            raise TypeError('Input position type: {} is not supported'.format(type(position)))

    def update_velocity(self, velocity):
        if isinstance(velocity, tuple):
            self.velocity = Velocity(velocity)
        elif isinstance(velocity, Velocity):
            self.velocity = velocity
        else:
            raise TypeError('Input velocity type: {} is not supported'.format(type(velocity)))

    def update_acceleration(self, acceleration):
        if isinstance(acceleration, tuple):
            self.acceleration = Acceleration(acceleration)
        elif isinstance(acceleration, Acceleration):
            self.acceleration = acceleration
        else:
            raise TypeError('Input acceleration type: {} is not supported'.format(type(acceleration)))

    def update_heading(self, heading):
        if isinstance(heading, tuple):
            self.heading = Heading(heading)
        elif isinstance(heading, Heading):
            self.heading = heading
        else:
            raise TypeError('Input heading type: {} is not supported'.format(type(heading)))

    def update_timestamp(self, timestamp):
        self.timestamp = timestamp

    def show(self):
        res = self.position.to_dict()
        res.update(self.heading.to_dict())
        res.update(self.velocity.to_dict())
        res.update(self.acceleration.to_dict())
        res.update({'timestamp': self.timestamp})
        print(res)

    def to_dict(self):
        res = {'position': self.position.to_tuple(), 'heading': self.heading.to_tuple()}
        return res

    @staticmethod
    def get_invisible_statepoint():
        res = StatePoint(position=(0.0, 0.0, 0.0))
        return res

    @staticmethod
    def is_invisible_statepoint(sp):
        assert isinstance(sp, StatePoint)
        if sp.position.x == 0.0 and sp.position.y == 0.0 and sp.position.z == 0.0:
            return True
        else:
            return False

    @staticmethod
    def from_dubins_point(point):
        assert isinstance(point, tuple)
        res = StatePoint(position=(point[0], point[1], 0.0), heading=(0.0, 0.0, point[2]))
        return res

    @staticmethod
    def to_dubins_point(point):
        assert isinstance(point, StatePoint)
        res = (point.position.x, point.position.y, point.heading.yaw)
        return res

    @staticmethod
    def get_heading(tail_point, head_point):
        # delta_yaw = tail_point.heading.yaw - head_point.heading.yaw
        x1, y1 = tail_point.position.x, tail_point.position.y
        x2, y2 = head_point.position.x, head_point.position.y

        delta_yaw = math.atan2(y2 - y1, x2 - x1)
        # return statepoint.minimum_equal_angle(math.acos(delta_yaw))
        return delta_yaw

    @staticmethod
    def get_dist(point1, point2):
        x1, y1 = point1.position.x, point1.position.y
        x2, y2 = point2.position.x, point2.position.y
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    @staticmethod
    def minimum_equal_angle(angle):
        if angle > math.pi:
            angle -= (int((angle - math.pi) / 2 / math.pi) + 1) * 2 * math.pi
        elif angle < -math.pi:
            angle += (int((-math.pi - angle) / 2 / math.pi) + 1) * 2 * math.pi
        return angle


class Position(object):
    def __init__(self, position=None):
        if position is not None and not isinstance(position, tuple):
            raise TypeError('input position is not tuple')
        self.x, self.y, self.z = None, None, None
        self.tuple = None
        if position:
            self.x = position[0]
            self.y = position[1]
            self.z = position[2]
            self.tuple = (self.x, self.y, self.z)

    def to_dict(self):
        return {'position:': (self.x, self.y, self.z)}

    def to_tuple(self):
        return (self.x, self.y, self.z)

    def update(self, position=None):
        if position is not None and not isinstance(position, tuple):
            raise TypeError('input position is not tuple')
        if position:
            self.x = position[0]
            self.y = position[1]
            self.z = position[2]
            self.tuple = (self.x, self.y, self.z)

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y and self.z == other.z

    def __sub__(self, other):
        return Position((self.x - other.x, self.y - other.y, self.z - other.z))

    def __add__(self, other):
        return Position((self.x + other.x, self.y + other.y, self.z + other.z))

    # other should be a scalar
    def __mul__(self, other):
        return Position((self.x * other, self.y * other, self.z * other))

    def __div__(self, other):
        return Position((self.x / other, self.y / other, self.z / other))

    def norm(self):
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)


class Velocity(object):
    def __init__(self, velocity=None):
        self.x, self.y, self.z = None, None, None
        self.tuple = None
        if velocity and isinstance(velocity, tuple):
            self.x = velocity[0]
            self.y = velocity[1]
            self.z = velocity[2]
            self.tuple = (self.x, self.y, self.z)

    def to_dict(self):
        return {'velocity': (self.x, self.y, self.z)}

    def to_tuple(self):
        return (self.x, self.y, self.z)

    def __add__(self, other):
        return Velocity((self.x + other.x, self.y + other.y, self.z + other.z))

    def __sub__(self, other):
        return Velocity((self.x - other.x, self.y - other.y, self.z - other.z))

    def __mul__(self, other):
        return Velocity((self.x * other, self.y * other, self.z * other))

    def __div__(self, other):
        return Velocity((self.x / other, self.y / other, self.z / other))

    def norm(self):
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)


class Acceleration(object):
    def __init__(self, acceleration=None):
        self.x, self.y, self.z = None, None, None
        self.tuple = None
        if acceleration and isinstance(acceleration, tuple):
            self.x = acceleration[0]
            self.y = acceleration[1]
            self.z = acceleration[2]
            self.tuple = (self.x, self.y, self.z)

    def to_dict(self):
        return {'acceleration': (self.x, self.y, self.z)}

    def to_tuple(self):
        return (self.x, self.y, self.z)

    def __add__(self, other):
        return Acceleration((self.x + other.x, self.y + other.y, self.z + other.z))

    def __sub__(self, other):
        return Acceleration((self.x - other.x, self.y - other.y, self.z - other.z))

    def __mul__(self, other):
        return Acceleration((self.x * other, self.y * other, self.z * other))

    def __div__(self, other):
        return Acceleration((self.x / other, self.y / other, self.z / other))

    def norm(self):
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)


class Heading(object):
    def __init__(self, heading=None):
        self.roll, self.pitch, self.yaw = None, None, None
        self.tuple = None
        if heading:
            self.roll = heading[0]
            self.pitch = heading[1]
            self.yaw = heading[2]
            self.tuple = (self.roll, self.pitch, self.yaw)

    def to_dict(self):
        return {'heading': (self.roll, self.pitch, self.yaw)}

    def to_tuple(self):
        return self.tuple

    def __add__(self, other):
        return Heading((self.roll + other.roll, self.pitch + other.pitch, self.yaw + other.yaw))

    def __sub__(self, other):
        return Heading((self.roll - other.roll, self.pitch - other.pitch, self.yaw - other.yaw))

    def __mul__(self, other):
        return Heading((self.roll * other, self.pitch * other, self.yaw * other))

    def __div__(self, other):
        return Heading((self.roll / other, self.pitch / other, self.yaw / other))


class BoundingBox2D(object):
    def __init__(self, statepoint=None, length=None, width=None):
        # TODO simplify structure

        self.sp = statepoint
        self.length = length
        self.width = width
        self.vertices = {'front_left': Position(),
                         'front_right': Position(),
                         'rear_left': Position(),
                         'rear_right': Position()}
        self.front_left = self.vertices['front_left']
        self.front_right = self.vertices['front_right']
        self.rear_left = self.vertices['rear_left']
        self.rear_right = self.vertices['rear_right']
        # self.update()


    def update(self, sp, length, width):
        center_x, center_y = sp.position.x, sp.position.y

        # Auto-detect if heading is in degrees or radians based on typical value ranges
        # Degrees: typically -360 to 360, Radians: typically -π to π (≈ -3.14 to 3.14)
        if abs(sp.heading.yaw) > 10.0:  # Likely degrees (outside typical radian range)
            heading = deg2rad(sp.heading.yaw)  # Convert degrees to radians
        else:
            heading = sp.heading.yaw  # Already in radians

        # Half dimensions
        half_length = length / 2.0
        half_width = width / 2.0

        # Define corners in local frame relative to center (x-forward, y-left)
        local_corners = [
            (+half_length, +half_width),  # Front-Left
            (+half_length, -half_width),  # Front-Right
            (-half_length, +half_width),  # Rear-Left
            (-half_length, -half_width),  # Rear-Right
        ]

        # Transform to global frame using transform2D
        global_corners = [transform2D(x, y, center_x, center_y, heading) for (x, y) in local_corners]
        x, y = global_corners[0]
        self.vertices['front_left'].update((x, y, 0.0))
        x, y = global_corners[1]
        self.vertices['front_right'].update((x, y, 0.0))
        x, y = global_corners[2]
        self.vertices['rear_left'].update((x, y, 0.0))
        x, y = global_corners[3]
        self.vertices['rear_right'].update((x, y, 0.0))
        self._sync()

    def _sync(self):
        self.front_left = self.vertices['front_left']
        self.front_right = self.vertices['front_right']
        self.rear_left = self.vertices['rear_left']
        self.rear_right = self.vertices['rear_right']