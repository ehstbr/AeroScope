"""Keep airspace and overlays north-up without disabling touch pinch/pan."""
from __future__ import annotations

import logging


def lock_north_up(viewport, map_widget, gtk):
    """Disable only Libshumate's GtkGestureRotate, then guard its viewport.

    Libshumate has no public Shumate.Map::rotation-enabled property. Inspecting
    controllers once at initialization is safe; we do not keep the dynamic
    ListModel around or observe it on every frame.
    """
    disabled = 0
    try:
        controllers = map_widget.observe_controllers()
        for index in range(controllers.get_n_items()):
            controller = controllers.get_item(index)
            if isinstance(controller, gtk.GestureRotate):
                controller.set_propagation_phase(gtk.PropagationPhase.NONE)
                controller.reset()
                disabled += 1
    except (AttributeError, RuntimeError, TypeError) as exc:
        logging.getLogger('aeroscope').debug('Map rotation controller unavailable: %s', exc)

    def enforce_north(obj, *_args):
        if abs(obj.get_rotation()) > 1e-9:
            obj.set_rotation(0.0)

    viewport.set_rotation(0.0)
    viewport.connect('notify::rotation', enforce_north)
    return disabled
