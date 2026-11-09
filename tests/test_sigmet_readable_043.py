"""SIGMET Portuguese explanations, geometry and sidebar integration without GTK."""
from pathlib import Path
from aeroscope.sigmet_readable import (describe_sigmet, sigmet_label_point,
                                        sigmet_at_point)
from aeroscope.weather_data import (Sigmet, parse_sigmets, known_airport_icaos_for_bbox,
                                    fetch_metar_stations, noaa_bbox)

ROOT = Path(__file__).resolve().parents[1]


def warning(name, text='', metadata=None):
    return Sigmet(name, (((-20.,-44.),(-20.,-42.),(-18.,-42.),(-18.,-44.)),), text, metadata)


def test_thunderstorms_translated_with_observation_and_top():
    value = describe_sigmet(warning('TS','SBBS SIGMET 17 EMBD TS FCST TOP FL380 MOV NE 20KT'))
    assert value.icon == '⛈'
    assert value.short == 'Tempestades'
    assert 'descargas elétricas' in value.description
    assert ('Tipo de informação', 'Fenômeno previsto') in value.fields
    assert any('FL380' in v for k,v in value.fields)
    assert any('37 km/h' in v for k,v in value.fields)


def test_turbulence_icing_volcano_cyclone_unknown():
    assert describe_sigmet(warning('TURB', 'SEV TURB OBS')).short == 'Turbulência'
    assert ('Intensidade', 'Severa') in describe_sigmet(warning('ICE','SEV ICE')).fields
    assert describe_sigmet(warning('VA', 'VA CLD')).short == 'Cinzas vulcânicas'
    assert describe_sigmet(warning('TC', 'TC MARIA')).short == 'Ciclone tropical'
    generic = describe_sigmet(warning('SIGMET', 'REGIONAL ADVISORY'))
    assert generic.icon == '⚠' and generic.short == 'SIGMET'


def test_no_substring_false_positive_and_validity_only_if_given():
    report = describe_sigmet(warning('SIGMET','METEOROLOGICAL CONDITIONS'))
    assert report.short == 'SIGMET'
    assert not any('validade' in key.lower() for key, _ in report.fields)
    report = describe_sigmet(warning('TS','FRQ TS OBS', {
        'validTimeFrom':'2026-11-08T11:00:00Z', 'validTimeTo':'2026-11-08T15:00:00Z'}))
    assert ('Início da validade', '08/11/2026 11:00 UTC') in report.fields
    assert ('Fim da validade', '08/11/2026 15:00 UTC') in report.fields


def test_geojson_metadata_and_polygon_placement():
    poly = [[-44,-20],[-42,-20],[-42,-18],[-44,-18],[-44,-20]]
    payload = {'type':'FeatureCollection','features': [{
        'type':'Feature','properties':{'hazard':'TS','rawSigmet':'FRQ TS FCST', 'validTimeTo':'2026-11-08T18:00:00Z'},
        'geometry':{'type':'Polygon','coordinates':[poly]}}]}
    rows = parse_sigmets(payload)
    assert len(rows) == 1
    assert rows[0].metadata['hazard']=='TS'
    center = sigmet_label_point(rows[0].rings)
    assert -20 < center[0] < -18 and -44 < center[1] < -42
    assert sigmet_at_point(rows,*center) == rows[0]
    assert sigmet_at_point(rows,-10,-30) is None


def test_concave_area_centre_stays_inside():
    ring = ((0,0),(0,5),(1,5),(1,1),(5,1),(5,0))
    center = sigmet_label_point((ring,))
    sig = Sigmet('ICE', (ring,), 'SEV ICE')
    assert sigmet_at_point([sig], *center) is sig


def test_metar_cnfs_plu_batch_region(monkeypatch):
    center = (-19.7, -43.9)
    codes = known_airport_icaos_for_bbox(noaa_bbox(*center))
    assert 'SBCF' in codes and 'SBBH' in codes
    calls = []
    def get_json(url, *, limit=0):
        calls.append(url)
        return [
            {'icaoId':'SBCF','lat':-19.6244,'lon':-43.9719,'rawOb':'SBCF 081200Z 09010KT 9999'},
            {'icaoId':'SBBH','lat':-19.8512,'lon':-43.9506,'rawOb':'SBBH 081200Z 18004KT 9999'},
            {'icaoId':'KJFK','lat':40.6,'lon':-73.7,'rawOb':'KJFK 081200Z'}]
    monkeypatch.setattr('aeroscope.weather_data.get_json',get_json)
    rows=fetch_metar_stations(codes)
    assert {'SBCF','SBBH'}.issubset({m.station for m in rows})
    assert all(row.station in codes for row in rows)
    assert len(calls)==1 and 'ids=' in calls[0]


def test_sidebar_not_dialog_and_no_extra_sigmet_fetch():
    ui = (ROOT/'aeroscope'/'ui.py').read_text()
    weather = (ROOT/'aeroscope'/'weather_ui.py').read_text()
    assert 'def select_sigmet(self, sigmet)' in ui
    assert 'if self.selected_sigmet is not None' in ui
    assert "Gtk.Expander(label=_('View original SIGMET (technical bulletin)'))" in ui
    click_section = weather.split('def _show_sigmet(self,',1)[1].split('def _show_metar(self,',1)[0]
    assert 'radar.select_sigmet(sigmet)' in click_section
    assert 'Adw.MessageDialog' not in click_section
    # The 0.3.47 optimizer prepares NOAA label points once per response.
    assert 'sigmets, sigmet_label_point, previous=self.sigmet_scene)' in weather
    assert "self._refresh_known_airport_metars(center)" in weather


def test_known_station_report_with_missing_coordinates(monkeypatch):
    monkeypatch.setattr('aeroscope.weather_data.get_json', lambda url, **kw: [
        {'icaoId':'SBBH','rawOb':'SBBH 081200Z 18004KT 9999', 'fltCat':'VFR'}])
    rows = fetch_metar_stations(['SBBH'])
    assert len(rows)==1 and rows[0].station == 'SBBH'
    assert rows[0].lat < 0 and rows[0].lon < 0
    assert rows[0].raw.startswith('SBBH')
