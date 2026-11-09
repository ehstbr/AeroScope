"""Frame-based, inertial keyboard panning, independent of GTK/libshumate."""
from __future__ import annotations
import math

KEY_DIRECTIONS = {
    'Left': (-1, 0), 'Right': (1, 0),
    'Up': (0, -1), 'Down': (0, 1),
    'KP_Left': (-1, 0), 'KP_Right': (1, 0),
    'KP_Up': (0, -1), 'KP_Down': (0, 1),
}


class KeyboardPan:
    SPEED = 650.0          # pixels per second
    PRESS_RESPONSE = 0.13 # gradual acceleration
    RELEASE_RESPONSE = 0.095  # brief coast after release
    INITIAL_SPEED = 325.0  # useful distance even on a quick tap

    def __init__(self):
        self.held = set()
        self.vx = 0.0
        self.vy = 0.0
        self.last_time = None

    def reset(self):
        self.held.clear()
        self.vx = self.vy = 0.0
        self.last_time = None

    def _direction(self):
        dx = dy = 0
        for key in self.held:
            x, y = KEY_DIRECTIONS[key]
            dx += x
            dy += y
        length = math.hypot(dx, dy)
        return (dx / length, dy / length) if length else (0.0, 0.0)

    def press(self, key, now):
        if key not in KEY_DIRECTIONS:
            return False
        if key in self.held:  # Ignore keyboard auto-repeat for acceleration.
            return True
        was_still = not self.held and math.hypot(self.vx, self.vy) < 3
        self.held.add(key)
        if self.last_time is None:
            self.last_time = now
        if was_still:
            x, y = self._direction()
            self.vx, self.vy = x * self.INITIAL_SPEED, y * self.INITIAL_SPEED
        return True

    def release(self, key):
        if key in KEY_DIRECTIONS:
            self.held.discard(key)
            return True
        return False

    def step(self, now):
        """Return (eastward pixels, southward pixels, run_next_frame)."""
        if self.last_time is None:
            self.last_time = now
            return 0.0, 0.0, bool(self.held)
        dt = max(0.0, min(0.05, now - self.last_time))
        self.last_time = now
        direction_x, direction_y = self._direction()
        target_x, target_y = direction_x * self.SPEED, direction_y * self.SPEED
        response = self.PRESS_RESPONSE if self.held else self.RELEASE_RESPONSE
        blend = -math.expm1(-dt / response)
        old_vx, old_vy = self.vx, self.vy
        self.vx += (target_x - self.vx) * blend
        self.vy += (target_y - self.vy) * blend
        dx, dy = (old_vx + self.vx) * dt / 2, (old_vy + self.vy) * dt / 2
        if not self.held and math.hypot(self.vx, self.vy) < 3:
            self.reset()
            return dx, dy, False
        return dx, dy, True
