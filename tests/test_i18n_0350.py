"""Native-English default, Brazilian Portuguese, Gettext and catalog regression."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = '''from aeroscope.i18n import _,LANGUAGE
from aeroscope.metar_readable import CLOUDS
from aeroscope.regional_poll import describe_interval
from aeroscope.sigmet_readable import describe_sigmet
print(LANGUAGE)
print(_('Appearance'))
print(_('Language'))
print(describe_interval(15))
print(describe_interval(60))
print(describe_interval(120))
print(CLOUDS['OVC'])
print(describe_sigmet(type('S', (), {'name':'SIGMET TS','text':'OBS TS','metadata':{}})()).short)
'''


def launch(lang=None, config_home=None):
    env = os.environ.copy()
    env.pop('AEROSCOPE_LANGUAGE', None)
    if lang is not None:
        env['AEROSCOPE_LANGUAGE'] = lang
    if config_home is not None:
        env['XDG_CONFIG_HOME'] = str(config_home)
    out = subprocess.check_output([sys.executable, '-c', SCRIPT], cwd=ROOT, env=env, text=True)
    return out.splitlines()


def test_original_english_is_default(tmp_path):
    result = launch(config_home=tmp_path)
    assert result == ['en_US', 'Appearance', 'Language', '15 seconds', '1 minute',
                      '2 minutes', 'Overcast', 'Thunderstorms']


def test_explicit_portuguese_catalog(tmp_path):
    result = launch('pt_BR', config_home=tmp_path)
    assert result == ['pt_BR', 'Aparência', 'Idioma', '15 segundos', '1 minuto',
                      '2 minutos', 'Céu encoberto', 'Tempestades']


def test_preference_is_used_after_restart(tmp_path):
    config = tmp_path / 'aeroscope'
    config.mkdir()
    (config/'settings.json').write_text('{"language":"pt_BR"}', encoding='utf-8')
    assert launch(config_home=tmp_path)[0:3] == ['pt_BR', 'Aparência', 'Idioma']


def test_all_catalogs_are_included():
    assert (ROOT/'po/aeroscope.pot').exists()
    assert (ROOT/'po/en_US.po').exists()
    assert (ROOT/'po/pt_BR.po').exists()
    assert (ROOT/'aeroscope/locale/pt_BR/LC_MESSAGES/aeroscope.mo').exists()
