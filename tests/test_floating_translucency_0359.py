"""Ensure GTK translucency is on the floating card background, not content."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_weather_card_background_has_subtle_alpha_without_fading_child_content():
    css = (ROOT / 'assets' / 'style.css').read_text()
    match = re.search(r'\.dashboard-weather-card\s*\{([^}]*)\}', css)
    assert match, 'A dashboard weather card CSS rule is required'
    props = match.group(1)
    color = re.search(r'background\s*:\s*alpha\(@window_bg_color,\s*([0-9.]+)\)', props)
    assert color, 'Use the Libadwaita theme color with alpha'
    opacity = float(color.group(1))
    assert .88 <= opacity <= .94, 'Translucency should remain gentle'
    assert 'opacity:' not in props, 'Do not fade the complete card contents'
    assert 'border:' in props and 'box-shadow:' in props


def test_card_class_attached_to_floating_widget_and_no_global_opacity():
    source = (ROOT / 'aeroscope' / 'floating_widget.py').read_text()
    assert "self.add_css_class('dashboard-weather-card')" in source
    assert '.set_opacity(' not in source
    assert "self.category_label.add_css_class('dashboard-flight-category')" in source
    assert "self.sigmet_chip.add_css_class('dashboard-sigmet-chip')" in source


def test_version_bumped_consistently():
    for name in ('aeroscope/__init__.py', 'aeroscope/settings.py',
                 'packaging/build-deb.sh'):
        assert '0.3.72' in (ROOT / name).read_text()
