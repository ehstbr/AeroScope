"""The initial preference follows Ubuntu's session language, not a stored English default."""
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def get_language(tmp_path, **updates):
    env=os.environ.copy()
    for key in ('LANGUAGE','LANG','LC_ALL','LC_MESSAGES','AEROSCOPE_LANGUAGE'):
        env.pop(key,None)
    env.update({'XDG_CONFIG_HOME':str(tmp_path),'LANG':'C'})
    env.update(updates)
    return subprocess.check_output([sys.executable,'-c',
                                    'from aeroscope.i18n import LANGUAGE; print(LANGUAGE)'],
                                   cwd=ROOT, env=env,text=True).strip()


def test_automatic_portuguese_system_and_explicit_english(tmp_path):
    assert get_language(tmp_path,LANG='pt_BR.UTF-8')=='pt_BR'
    assert get_language(tmp_path,LANG='C',LANGUAGE='pt_BR:pt:en')=='pt_BR'
    assert get_language(tmp_path,LANGUAGE='pt')=='pt_BR'
    assert get_language(tmp_path,LANG='pt_BR.UTF-8',AEROSCOPE_LANGUAGE='en_US')=='en_US'


def test_legacy_english_preference_migrates_to_system(tmp_path):
    dest=tmp_path/'aeroscope';dest.mkdir()
    (dest/'settings.json').write_text('{"language":"en_US"}')
    assert get_language(tmp_path,LANG='pt_BR.UTF-8')=='pt_BR'
    (dest/'settings.json').write_text('{"language":"en_US","language_schema":2}')
    assert get_language(tmp_path,LANG='pt_BR.UTF-8')=='en_US'
