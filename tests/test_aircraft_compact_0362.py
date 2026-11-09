"""Folded aircraft panels display more useful data without photographs."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
WIDGET = ROOT / 'aeroscope/aircraft_widget.py'


def test_compact_instruments_and_actions_are_built_once():
    code = WIDGET.read_text()
    ast.parse(code)
    assert 'self.compact_body = Gtk.Box' in code
    assert 'self.compact_descriptor = Gtk.Label' in code
    assert "(0, 0, 'altitude', _('Altitude'))" in code
    assert "(1, 0, 'speed', _('Ground speed'))" in code
    assert "(0, 1, 'heading', _('Ground track'))" in code
    assert "(1, 1, 'vertical_rate', _('Vertical speed'))" in code
    assert 'self.compact_values[key] = value' in code
    assert 'label.set_text(fact[key])' in code
    assert 'self.compact_revealer.set_reveal_child(self.collapsed)' in code
    assert 'self.set_size_request(310, -1)' in code
    assert 'self.center_button' in code and 'self.follow_button' in code
    assert 'Gtk.Picture(' not in code


def test_collapsed_alert_and_photo_action_safety():
    code = WIDGET.read_text()
    assert "self.compact_alert.set_text(fact['alert'])" in code
    assert "self.compact_alert.set_visible(self.collapsed and bool(fact['alert']))" in code
    assert 'self.compact_alert.set_visible(self.collapsed and bool(self.compact_alert.get_text()))' in code
    assert "self.photo_button = Gtk.Button(icon_name='image-x-generic-symbolic')" in code
    assert 'header.append(self.photo_button)' in code
    assert "self.photo_button.connect('clicked', self._open_photo)" in code
    assert 'self.compact_line' not in code


def test_compact_css_uses_legible_labels_and_keeps_translucent_surface():
    css = (ROOT / 'assets/style.css').read_text()
    for token in ('dashboard-aircraft-compact-caption', 'dashboard-aircraft-compact-value',
                  'dashboard-aircraft-compact-grid', 'dashboard-aircraft-compact-descriptor'):
        assert token in css
    assert '.dashboard-weather-card {' in css
