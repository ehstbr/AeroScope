"""Small, toolkit-independent position transitions for the live radar.

Only interpolate between two real received ADS-B fixes. No extrapolation,
predictions, API polling, or persistent storage. All times are monotonic.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
import math
import statistics


def normalize_lon(longitude: float) -> float:
    return ((float(longitude) + 180.0) % 360.0) - 180.0


def interpolate_position(start: tuple[float, float], end: tuple[float, float], fraction: float) -> tuple[float, float]:
    """Shortest longitude path (including crossings of the ±180° meridian)."""
    t = max(0.0, min(1.0, float(fraction)))
    if t == 0.0:
        return start
    if t == 1.0:
        return end
    delta = (end[1] - start[1] + 180.0) % 360.0 - 180.0
    latitude = start[0] + (end[0] - start[0]) * t
    longitude = normalize_lon(start[1] + delta * t)
    return latitude, longitude


@dataclass(frozen=True)
class PositionTransition:
    start: tuple[float, float]
    end: tuple[float, float]
    started_at: float
    duration: float = 27.6

    def sample(self, now: float) -> tuple[tuple[float, float], bool]:
        if self.duration <= 0:
            return self.end, True
        progress = max(0.0, min(1.0, (now - self.started_at) / self.duration))
        # Constant-speed interpolation avoids repeatedly accelerating and
        # braking at each refresh. Only previously received fixes are used.
        point = interpolate_position(self.start, self.end, progress)
        return point, progress >= 1


def transition_allowed(start: tuple[float, float], end: tuple[float, float],
                       age_seconds: float, *, min_nm: float = 0.04, max_nm: float = 20.0) -> bool:
    """Refuse stale, implausible, or effectively stationary fixes."""
    if not (0 < age_seconds <= 180):
        return False
    if not all(math.isfinite(x) for x in (*start, *end)):
        return False
    if not all(-90 <= p[0] <= 90 for p in (start, end)):
        return False
    lat1, lon1 = map(math.radians, start)
    lat2, lon2 = map(math.radians, end)
    delta_lon = math.radians(normalize_lon(end[1] - start[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    distance_nm = 3440.065 * 2 * math.asin(min(1.0, math.sqrt(max(0.0, h))))
    # 1200 kt is a generous upper bound to reject teleportation/jumps.
    plausible_max_nm = min(max_nm, max(0.5, age_seconds * 1200 / 3600))
    return min_nm <= distance_nm <= plausible_max_nm


def startup_poll_interval(configured_seconds: int, successful_polls: int,
                          *, failed: bool = False) -> float:
    """Three startup snapshots: immediately, +2.5s, then +5s.

    The configured cadence resumes thereafter (10s minimum). This sequence
    is only for successful startup responses, and is disabled after errors or
    rate limiting. Actual API rate limits may prevent the warm-up entirely.
    """
    regular = max(10.0, float(configured_seconds))
    if failed:
        return regular
    if successful_polls == 1:
        return 2.5
    if successful_polls == 2:
        return 5.0
    return regular


@dataclass
class RequestLatencyTracker:
    """Bounded moving average of successful request round-trip times.

    A very slow outlier should not make every plane crawl for the next minute;
    clamp each new observation relative to the recent median. A fresh app
    starts without guessing the provider's latency.
    """
    samples: deque = field(default_factory=lambda: deque(maxlen=5))

    def observe(self, seconds: float) -> None:
        value = float(seconds)
        if not math.isfinite(value) or value <= 0:
            return
        value = min(value, 8.0)
        if len(self.samples) >= 2:
            baseline = statistics.median(self.samples)
            value = min(value, max(1.5, 2.5 * baseline))
        self.samples.append(value)

    @property
    def estimate(self) -> float:
        return sum(self.samples) / len(self.samples) if self.samples else 0.0


def flight_animation_duration(next_poll_seconds: float, latency_seconds: float = 0.0) -> float:
    """Approach the *next completed response*, not merely the next request.

    Polling starts N seconds after the previous response completed. The next
    response arrives approximately N + measured request duration seconds later.
    Keep only a small margin to avoid freezing before a typical response.
    This never extrapolates beyond the last known ADS-B coordinates.
    """
    interval = max(0.1, float(next_poll_seconds))
    latency = max(0.0, min(8.0, float(latency_seconds)))
    margin = max(0.15, min(0.6, interval * 0.025))
    return max(0.3, min(130.0, interval + latency - margin))
