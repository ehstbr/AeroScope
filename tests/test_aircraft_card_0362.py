"""Regression against an oversized aircraft overlay caused by original image size."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_photo_is_header_action_only_not_part_of_body():
    src = (ROOT / 'aeroscope/aircraft_widget.py').read_text()
    tree = ast.parse(src)
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AircraftFloatingWidget')
    constructor = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    assert "Gtk.Button(icon_name='image-x-generic-symbolic')" in src
    assert "header.append(self.photo_button)" in src
    assert "self.body.append(identity_text)" in src
    assert "Gtk.Picture(" not in ast.get_source_segment(src, constructor)
    assert "Gtk.Image.new_from_icon_name('view-grid-symbolic')" in src
    assert "self.center_button = Gtk.Button" in src
    assert "self.follow_button = Gtk.Button" in src
    assert "self.photo_button.set_visible(False)" in src
    assert "self.photo_button.set_visible(True)" in src


def test_no_photo_size_change_or_extra_network_fetch():
    widget = (ROOT / 'aeroscope/aircraft_widget.py').read_text()
    dashboard = (ROOT / 'aeroscope/dashboard.py').read_text()
    assert 'self.set_size_request(310, -1)' in widget
    assert 'self.set_size_request(310, -1)' in widget
    assert 'card.photo_note' not in dashboard
    assert 'self.controller.radar._show_photo_preview(' in widget
    assert 'photo = self.radar.photo_info.get(hexid)' in dashboard
    assert 'fetch_history' not in widget
