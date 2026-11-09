"""Lightweight, frame-clock-driven entry/exit fades for dashboard cards.

Only the short transitions affect widget opacity. A resting card remains fully
opaque as a *widget*; its CSS background retains its separate 90% translucency.
"""
from __future__ import annotations

FADE_IN_MS = 150
FADE_OUT_MS = 130


def opacity_at(elapsed_us: int, duration_ms: int, *, appearing: bool) -> float:
    """Clamp frame-time progress and smoothly interpolate whole-card opacity."""
    if duration_ms <= 0:
        return 1.0 if appearing else 0.0
    progress = max(0.0, min(1.0, elapsed_us / (duration_ms * 1000.0)))
    eased = progress * progress * (3.0 - 2.0 * progress)
    return eased if appearing else 1.0 - eased


def fade_widget(widget, *, appearing: bool, enabled: bool = True,
                on_finished=None, duration_ms: int | None = None):
    """Animate a GTK widget without changing its size, position, or allocation.

    Uses GTK's frame clock, not a second animation timer or CSS class. The
    completion callback runs after the final frame, enabling deferred removal.
    """
    if duration_ms is None:
        duration_ms = FADE_IN_MS if appearing else FADE_OUT_MS
    target = 1.0 if appearing else 0.0
    if not enabled or duration_ms <= 0:
        widget.set_opacity(target)
        if on_finished is not None:
            on_finished()
        return None

    widget.set_opacity(0.0 if appearing else 1.0)
    started_at = None

    def tick(card, clock):
        nonlocal started_at
        now = clock.get_frame_time()  # microseconds; fixed clock for all frames
        if started_at is None:
            started_at = now
        elapsed = max(0, now - started_at)
        card.set_opacity(opacity_at(elapsed, duration_ms, appearing=appearing))
        if elapsed >= duration_ms * 1000:
            card.set_opacity(target)
            if on_finished is not None:
                on_finished()
            return False
        return True

    return widget.add_tick_callback(tick)
