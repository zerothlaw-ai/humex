"""Pure-Python Dubins path computation.

Computes shortest curved paths between (x, y, yaw) configurations subject to
a minimum turning radius. Implements all 6 Dubins path types (LSL, RSR, LSR,
RSL, RLR, LRL) using closed-form solutions.

Replaces the C-based ``dubins`` (pydubins) package to avoid native compilation
dependencies in containerised builds.
"""

import math

_TWO_PI = 2.0 * math.pi


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _mod2pi(theta):
    """Normalize angle to [0, 2*pi)."""
    return theta - _TWO_PI * math.floor(theta / _TWO_PI)


# --- Path-type solvers (return (t, p, q) or None) -------------------------

def _LSL(alpha, beta, d):
    sa, sb = math.sin(alpha), math.sin(beta)
    ca, cb = math.cos(alpha), math.cos(beta)
    c_ab = math.cos(alpha - beta)
    tmp0 = d + sa - sb
    p_sq = 2 + d * d - 2 * c_ab + 2 * d * (sa - sb)
    if p_sq < 0:
        return None
    tmp1 = math.atan2(cb - ca, tmp0)
    return (_mod2pi(-alpha + tmp1), math.sqrt(p_sq), _mod2pi(beta - tmp1))


def _RSR(alpha, beta, d):
    sa, sb = math.sin(alpha), math.sin(beta)
    ca, cb = math.cos(alpha), math.cos(beta)
    c_ab = math.cos(alpha - beta)
    tmp0 = d - sa + sb
    p_sq = 2 + d * d - 2 * c_ab + 2 * d * (sb - sa)
    if p_sq < 0:
        return None
    tmp1 = math.atan2(ca - cb, tmp0)
    return (_mod2pi(alpha - tmp1), math.sqrt(p_sq), _mod2pi(-beta + tmp1))


def _LSR(alpha, beta, d):
    sa, sb = math.sin(alpha), math.sin(beta)
    ca, cb = math.cos(alpha), math.cos(beta)
    c_ab = math.cos(alpha - beta)
    p_sq = -2 + d * d + 2 * c_ab + 2 * d * (sa + sb)
    if p_sq < 0:
        return None
    p = math.sqrt(p_sq)
    tmp = math.atan2(-ca - cb, d + sa + sb) - math.atan2(-2.0, p)
    return (_mod2pi(-alpha + tmp), p, _mod2pi(-_mod2pi(beta) + tmp))


def _RSL(alpha, beta, d):
    sa, sb = math.sin(alpha), math.sin(beta)
    ca, cb = math.cos(alpha), math.cos(beta)
    c_ab = math.cos(alpha - beta)
    p_sq = d * d - 2 + 2 * c_ab - 2 * d * (sa + sb)
    if p_sq < 0:
        return None
    p = math.sqrt(p_sq)
    tmp = math.atan2(ca + cb, d - sa - sb) - math.atan2(2.0, p)
    return (_mod2pi(alpha - tmp), p, _mod2pi(_mod2pi(beta) - tmp))


def _RLR(alpha, beta, d):
    sa, sb = math.sin(alpha), math.sin(beta)
    ca, cb = math.cos(alpha), math.cos(beta)
    c_ab = math.cos(alpha - beta)
    tmp = (6.0 - d * d + 2 * c_ab + 2 * d * (sa - sb)) / 8.0
    if abs(tmp) > 1.0:
        return None
    p = _mod2pi(_TWO_PI - math.acos(tmp))
    t = _mod2pi(alpha - math.atan2(ca - cb, d - sa + sb) + _mod2pi(p / 2.0))
    q = _mod2pi(alpha - beta - t + _mod2pi(p))
    return (t, p, q)


def _LRL(alpha, beta, d):
    sa, sb = math.sin(alpha), math.sin(beta)
    ca, cb = math.cos(alpha), math.cos(beta)
    c_ab = math.cos(alpha - beta)
    tmp = (6.0 - d * d + 2 * c_ab + 2 * d * (sb - sa)) / 8.0
    if abs(tmp) > 1.0:
        return None
    p = _mod2pi(_TWO_PI - math.acos(tmp))
    t = _mod2pi(-alpha - math.atan2(ca - cb, d + sa - sb) + p / 2.0)
    q = _mod2pi(_mod2pi(beta) - alpha - t + _mod2pi(p))
    return (t, p, q)


_PATH_FUNCS = [
    ('LSL', _LSL), ('RSR', _RSR), ('LSR', _LSR),
    ('RSL', _RSL), ('RLR', _RLR), ('LRL', _LRL),
]

_SEG_TYPES = {
    'LSL': ('L', 'S', 'L'), 'RSR': ('R', 'S', 'R'),
    'LSR': ('L', 'S', 'R'), 'RSL': ('R', 'S', 'L'),
    'RLR': ('R', 'L', 'R'), 'LRL': ('L', 'R', 'L'),
}


# --- Geometry helpers ------------------------------------------------------

def _segment(t, qi, seg_type):
    """Advance from config *qi* by normalised distance *t* along *seg_type*.

    All values are in the normalised (turning_radius=1) coordinate system.
    """
    x, y, phi = qi
    if seg_type == 'L':
        x += math.sin(phi + t) - math.sin(phi)
        y += -math.cos(phi + t) + math.cos(phi)
        phi += t
    elif seg_type == 'R':
        x += -math.sin(phi - t) + math.sin(phi)
        y += math.cos(phi - t) - math.cos(phi)
        phi -= t
    else:  # 'S'
        x += t * math.cos(phi)
        y += t * math.sin(phi)
    return (x, y, phi)


def _shortest_path(q0, q1, turning_radius):
    """Return *(path_type, (t, p, q), path_length)* or *None*."""
    dx = q1[0] - q0[0]
    dy = q1[1] - q0[1]
    d = math.sqrt(dx * dx + dy * dy) / turning_radius
    theta = math.atan2(dy, dx)
    alpha = _mod2pi(q0[2] - theta)
    beta = _mod2pi(q1[2] - theta)

    best, best_cost = None, float('inf')
    for name, func in _PATH_FUNCS:
        result = func(alpha, beta, d)
        if result is not None:
            cost = result[0] + result[1] + result[2]
            if cost < best_cost:
                best_cost = cost
                best = (name, result, cost * turning_radius)
    return best


def _sample_at(q0, path_type, params, turning_radius, t):
    """Return (x, y, yaw) at distance *t* along the path."""
    tprime = t / turning_radius
    types = _SEG_TYPES[path_type]
    qi = (0.0, 0.0, q0[2])

    q1 = _segment(params[0], qi, types[0])
    q2 = _segment(params[1], q1, types[1])

    if tprime < params[0]:
        q = _segment(tprime, qi, types[0])
    elif tprime < params[0] + params[1]:
        q = _segment(tprime - params[0], q1, types[1])
    else:
        q = _segment(tprime - params[0] - params[1], q2, types[2])

    return (
        q[0] * turning_radius + q0[0],
        q[1] * turning_radius + q0[1],
        _mod2pi(q[2]),
    )


# ---------------------------------------------------------------------------
# Public API  (signatures unchanged from the old pydubins wrapper)
# ---------------------------------------------------------------------------

def compute_dubins_path(q0, q1, turning_radius=6.0, step_size=0.5):
    """Compute Dubins path between two (x, y, yaw) configurations.

    Args:
        q0: Start configuration (x, y, yaw) in radians
        q1: End configuration (x, y, yaw) in radians
        turning_radius: Minimum turning radius in meters
        step_size: Spacing between sample points in meters

    Returns:
        dict with keys:
            'path_length': float - total arc length of the path
            'sample_points': list of (x, y, yaw) tuples along the path
    """
    result = _shortest_path(q0, q1, turning_radius)
    if result is None:
        return {'path_length': 0.0, 'sample_points': [q0]}

    path_type, params, path_length = result

    configurations = []
    t = 0.0
    while t < path_length:
        configurations.append(_sample_at(q0, path_type, params, turning_radius, t))
        t += step_size

    return {
        'path_length': path_length,
        'sample_points': configurations,
    }


def compute_all_dubins_segments(poses, turning_radius=6.0, step_size=0.5):
    """Compute Dubins paths for all consecutive pose pairs.

    Args:
        poses: list of (x, y, yaw) tuples
        turning_radius: Minimum turning radius in meters
        step_size: Spacing between sample points in meters

    Returns:
        list of dicts, each with:
            'path_length': float - arc length of the segment
            'sample_points': list of (x, y, yaw) tuples
    """
    segments = []
    for i in range(len(poses) - 1):
        segment = compute_dubins_path(poses[i], poses[i + 1], turning_radius, step_size)
        segments.append(segment)
    return segments
