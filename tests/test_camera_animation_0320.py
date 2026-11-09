from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "aeroscope" / "ui.py").read_text()


def test_native_map_animation_on_selection():
    assert "self._pan_to_aircraft(p.lat, p.lon)" in SRC
    assert "self.map.go_to_full_with_duration(lat, lon, zoom, duration_ms)" in SRC
    assert "self.map.stop_go_to()" in SRC


def test_follow_pauses_during_camera_transition():
    assert "if time.monotonic() < self._camera_transition_until:" in SRC
    assert "generation != self._camera_transition_generation" in SRC


def test_zoom_preserved_and_no_per_frame_network():
    assert "zoom = self.viewport.get_zoom_level()" in SRC
    assert "GLib.timeout_add(duration_ms + 250, self._camera_transition_completed, generation)" in SRC
