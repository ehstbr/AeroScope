"""Avoid GTK marker tooltips competing with a modal right-click popover."""
from __future__ import annotations


def protect_context_menu(popover, marker, idle_add, detach):
    """Suspend tooltip on the clicked marker, then safely restore it.

    GTK4 popovers are modal by default. A hover tooltip can be requested
    simultaneously with right click; suppress it until the popover is closed.
    The widget and popover are cleaned only once the event stack has unwound.
    """
    previous_tooltip = marker.get_tooltip_text()
    if previous_tooltip is not None:
        marker.set_tooltip_text(None)

    def on_closed(closed_popover):
        def cleanup():
            try:
                if previous_tooltip is not None and marker.get_parent() is not None:
                    marker.set_tooltip_text(previous_tooltip)
            except (RuntimeError, TypeError):
                pass  # The map may have replaced the marker before dismissal.
            detach(closed_popover)
            return False
        idle_add(cleanup)
    popover.connect('closed', on_closed)
