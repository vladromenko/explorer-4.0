"""Velocity limits for Tank commands. No permit files: the operator drives from Explorer.

Kept names (BENCH_V/BENCH_W, bench_authorized, require_motion_permission) are imported by
older modules; they no longer gate motion.
"""
if __package__:
    from .limits import load, clip
else:
    from limits import load, clip

BENCH_V = .3     # default manual forward speed, m/s
BENCH_W = 1.0    # default manual yaw rate, rad/s


def bench_authorized(root):
    return False


def neutral_diagnostic_authorized(root):
    return False


def require_motion_permission(root):
    return None


def limited_command(root, v, w, mode='manual', *, autonomous_goal=False, limits=None):
    current = load(root) if limits is None else limits
    v, w = clip(current, v, w, mode)
    if autonomous_goal and mode == 'manual':
        return clip(current, v, w, 'policy')
    return v, w
