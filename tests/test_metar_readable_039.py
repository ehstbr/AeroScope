"""Regressions for readable METAR without GUI or network dependencies."""
from pathlib import Path
from aeroscope.weather_data import Metar, parse_metars
from aeroscope.metar_readable import describe_metar

ROOT=Path(__file__).resolve().parents[1]


def metar(raw='', cat='VFR', details=None):
    return Metar('SBCF', -19.6, -43.9, raw, cat, '08/11 18:00 UTC', details)


def rows(report):
    return dict(describe_metar(report).fields)


def test_noaa_json_fields_are_preserved_and_decoded():
    payload={'type':'FeatureCollection','features':[
        {'type':'Feature','geometry':{'type':'Point','coordinates':[-43.9,-19.6]},'properties':{
            'icaoId':'SBCF','fltCat':'VFR','rawOb':'SBCF 081800Z 18008G14KT 9999 BKN030 26/20 Q1015',
            'temp':26.0,'dewp':20.0,'wdir':180,'wspd':8,'wgst':14,
            'visib':'10+', 'clouds':[{'cover':'BKN','base':3000}], 'altim':1015}}]}
    report = parse_metars(payload)[0]
    assert report.details['temp'] == 26
    plain=describe_metar(report)
    assert 'voo visual' in plain.condition
    values=dict(plain.fields)
    assert values['Temperatura'] == '26 °C'
    assert values['Ponto de orvalho'] == '20 °C'
    assert 'sul (180°)' in values['Vento']
    assert '15 km/h' in values['Vento']
    assert '26 km/h' in values['Vento']
    assert values['Visibilidade']=='Mais de 16 km'
    assert '914 m' in values['Nuvens']
    assert values['Pressão atmosférica (QNH)']=='1015 hPa'


def test_raw_metar_fallback_without_structured_fields():
    parts=rows(metar('SBCF 081800Z 20012G20KT 9999 FEW020 SCT040 23/19 Q1018'))
    assert '22 km/h' in parts['Vento']
    assert '37 km/h' in parts['Vento']
    assert parts['Visibilidade']=='Pelo menos 10 km'
    assert 'Poucas nuvens' in parts['Nuvens']
    assert parts['Temperatura']=='23 °C'


def test_var_wind_freezing_temps_and_cavok():
    parts=rows(metar('SBSP 081200Z VRB03KT CAVOK M02/M05 Q1020'))
    assert 'direção variável' in parts['Vento']
    assert parts['Temperatura']=='-2 °C'
    assert parts['Visibilidade']=='Pelo menos 10 km'
    assert 'Sem nuvens significativas' in parts['Nuvens']


def test_specific_weather_intensity_and_category():
    result=describe_metar(metar(cat='IFR',details={'wxString':'-TSRA BR','wspd':10,'wdir':'270','visib':'1/2'}))
    assert 'reduzidos' in result.condition
    parts=dict(result.fields)
    assert 'trovoada com chuva (fraca)' in parts['Tempo observado'].lower()
    assert 'névoa úmida' in parts['Tempo observado']
    assert parts['Visibilidade']=='0.8 km'
    assert 'oeste' in parts['Vento']


def test_do_not_invent_missing_or_invalid_information():
    report=describe_metar(metar(cat='N/D',details={
        'temp': 'NaN','wspd': 'unknown','visib':'garbled',
        'clouds':[{'cover':'UNKNOWN','base':-100}], 'altim':999999}))
    assert report.fields == ()
    assert 'não classificadas' in report.condition


def test_report_from_geojson_remains_compatible():
    original=Metar('SBCF',-19.6,-43.9,'SBCF 081800Z 18008KT 9999', 'VFR','date')
    assert 'Vento' in rows(original)


def test_technical_report_is_preserved_in_shared_sidebar_inspector():
    ui=(ROOT/'aeroscope'/'ui.py').read_text()
    weather=(ROOT/'aeroscope'/'weather_ui.py').read_text()
    assert 'describe_metar(metar)' in ui
    assert 'self._append_metar_report(metar)' in ui
    assert "Gtk.Expander(label=_('View original METAR (technical code)'))" in ui
    assert 'radar.select_weather_station(metar)' in weather
    assert 'Adw.MessageDialog.new(' not in weather


def test_no_extra_network_call_in_formatter():
    code=(ROOT/'aeroscope'/'metar_readable.py').read_text()
    assert 'urllib' not in code and 'requests' not in code
