"""Regressions for stable horizontal sidebar sizing."""
from pathlib import Path
from aeroscope.sidebar_layout import (
    needs_wrap, detail_needs_stacking, SIDEBAR_NATURAL_WIDTH_CHARS,
    MONITOR_NATURAL_WIDTH_CHARS,
)

ROOT = Path(__file__).resolve().parents[1] / 'aeroscope'


def test_long_metar_clouds_are_stacked_and_wrapped():
    text = ('Céu muito nublado a cerca de 335 m acima do aeroporto; '
            'Nuvens dispersas a cerca de 1.219 m acima do aeroporto; '
            'Céu muito nublado a cerca de 3.048 m acima do aeroporto')
    assert detail_needs_stacking('Nuvens', text)
    assert needs_wrap(text)
    assert detail_needs_stacking('Vento', 'Vento vindo do sul (180°), 28 km/h; rajadas de até 48 km/h')
    assert not detail_needs_stacking('Altitude', '36.000 pés')
    assert not detail_needs_stacking('ICAO24', 'E4962F')


def test_multiline_and_long_unbroken_identifiers_wrap():
    assert needs_wrap('N' * 160)
    assert needs_wrap('Uma linha\nOutra linha')
    assert needs_wrap('Curta', requested=True)
    assert SIDEBAR_NATURAL_WIDTH_CHARS <= 38
    assert MONITOR_NATURAL_WIDTH_CHARS <= 32


def test_main_sidebar_pane_is_user_resizable_and_not_forced_by_children():
    src = (ROOT/'ui.py').read_text()
    assert 'pane.set_shrink_start_child(True)' in src
    assert 'pane.set_resize_start_child(False)' in src
    assert 'self.sidebar_stack.set_hhomogeneous(False)' in src
    assert 'label.set_max_width_chars(SIDEBAR_NATURAL_WIDTH_CHARS)' in src
    assert 'label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)' in src
    assert "self.detail_box.append(line_row(label, value))" in src


def test_emergencies_favorites_history_share_bounded_text_components():
    src = (ROOT/'monitor_ui.py').read_text()
    assert 'label.set_max_width_chars(MONITOR_NATURAL_WIDTH_CHARS)' in src
    assert 'label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)' in src
    assert "self.global_message = _label(_('Not checked yet.'), wrap=True)" in src
    assert 'self._render_emergencies()' in src
    assert 'self._render_favorites()' in src


def test_monitor_action_buttons_cannot_force_wide_status_rows():
    src = (ROOT/'monitor_ui.py').read_text()
    assert 'self.fav_message.set_max_width_chars(18)' in src
    assert 'self.global_message.set_max_width_chars(22)' in src
    assert 'self.fav_message.set_hexpand(True)' in src
