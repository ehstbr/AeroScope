from pathlib import Path
from babel.messages import extract, pofile, mofile
from babel.messages.catalog import Catalog

root = Path(__file__).resolve().parent
po_dir = root / 'po'
translations = {
    # 0.3.62: aircraft compact telemetry panel.
    'Altitude': 'Altitude',
    'Ground speed': 'Velocidade no solo',
    'Ground track': 'Rumo sobre o solo',
    'Vertical speed': 'Velocidade vertical',
    'Position source': 'Fonte da posição',
    'Squawk': 'Squawk',
    'Level · 0 ft/min': 'Nivelado · 0 ft/min',
    'On ground': 'No solo',
    'No callsign': 'Sem indicativo de voo',
    'Position: {value0}': 'Posição: {value0}',
    'ICAO24: {value0}': 'ICAO24: {value0}',
    'Other': 'Outro',
    'Unknown': 'Desconhecido',
    '{value0} · {value1}': '{value0} · {value1}',
    'Full screen dashboard (F11)': 'Painel em tela cheia (F11)',
    'Exit full screen (F11 or Esc)': 'Sair da tela cheia (F11 ou Esc)',
    'Create floating panel': 'Criar painel flutuante',
    'Remove floating panel': 'Remover painel flutuante',
    'Weather station': 'Estação meteorológica',
    'Airport': 'Aeroporto',
    'Maximum of {value0} floating panels reached.': 'Limite de {value0} painéis flutuantes atingido.',
    'Collapse panel': 'Recolher painel',
    'Expand panel': 'Expandir painel',
    'Close floating panel': 'Fechar painel flutuante',
    'METAR unavailable.': 'METAR indisponível.',
    'Time not provided': 'Horário não informado',
    'METAR update failed; displaying last observation.': 'Falha na atualização do METAR; exibindo a última observação.',
    'Checked: {value0} UTC': 'Consultado: {value0} UTC',
    'Awaiting next NOAA update.': 'Aguardando próxima atualização da NOAA.',
    # 0.3.62: station/airport SIGMET coverage and temporal validity progress.
    'SIGMET advisories · NOAA': 'Avisos SIGMET · NOAA',
    'Checking SIGMET coverage…': 'Verificando cobertura de SIGMET…',
    'SIGMET lookup unavailable; coverage cannot be confirmed.': 'Consulta de SIGMET indisponível; não é possível confirmar a cobertura.',
    'Position unavailable for SIGMET lookup.': 'Posição indisponível para consultar SIGMET.',
    'No matching active SIGMET was returned for this location.': 'Nenhum SIGMET ativo correspondente foi retornado para este local.',
    'A SIGMET area covers this location horizontally. The reported phenomenon may be aloft or forecast, not necessarily occurring at the airport.': 'Uma área SIGMET abrange este local horizontalmente. O fenômeno informado pode ocorrer em altitude ou ser previsto, não necessariamente no aeroporto.',
    'Plus {value0} additional SIGMET advisories.': 'Além de outros {value0} avisos SIGMET.',
    'Advisory coverage is approximate and does not replace official preflight briefings.': 'A cobertura do aviso é aproximada e não substitui as informações meteorológicas oficiais para planejamento de voo.',
    'SIGMET near a saved location: %s': 'SIGMET próximo a um local salvo: %s',
    'SIGMET area covers this location': 'Uma área SIGMET abrange este local',
    '⚠ SIGMET covering this location': '⚠ SIGMET nesta região',
    '+ {value0} more SIGMET advisories': '+ {value0} avisos SIGMET',
    'Horizontal area; phenomenon may be aloft or forecast.': 'Área horizontal; o fenômeno pode ocorrer em altitude ou ser previsto.',
    'SIGMET verification unavailable.': 'Verificação de SIGMET indisponível.',
    'Checking SIGMET…': 'Verificando SIGMET…',
    'Elapsed portion of the SIGMET validity period, not weather severity.': 'Período transcorrido de validade do SIGMET, não da gravidade do fenômeno.',
    # 0.3.62: aircraft dashboard and defensive routeset decoding.
    'Waiting for signal': 'Aguardando sinal',
    'Checking aircraft photo…': 'Buscando foto da aeronave…',
    'Awaiting aircraft position.': 'Aguardando posição da aeronave.',
    '{value0} · {value1} · heading {value2}°': '{value0} · {value1} · rumo {value2}°',
    'Live': 'Ao vivo',
    'Signal lost': 'Sinal perdido',
    'Last ADS-B position: {value0} UTC': 'Última posição ADS-B: {value0} UTC',
    'Aircraft photos disabled in Preferences.': 'Fotografias de aeronaves desativadas nas Preferências.',
    'Photo unavailable.': 'Foto indisponível.',
    'Route provider response is too large.': 'A resposta do serviço de rotas é grande demais.',
    'Route provider returned an empty response. Try again later.': 'O serviço de rotas retornou uma resposta vazia. Tente novamente mais tarde.',
    'Route provider returned invalid data. Try again later.': 'O serviço de rotas retornou dados inválidos. Tente novamente mais tarde.',
    'found': 'encontrada',
    'Refresh all': 'Atualizar tudo',
    'Refresh aircraft': 'Atualizar aviões',
    'Refresh METAR': 'Atualizar METAR',
    'Refresh SIGMET': 'Atualizar SIGMET',
    'Refresh all (aircraft and enabled weather layers)': 'Atualizar tudo (aviões e camadas meteorológicas ativadas)',
    'Choose what to refresh': 'Escolher o que atualizar',
    'Updating {value0}…': 'Atualizando {value0}…',
    'Weather refresh is unavailable in demo mode.': 'A atualização meteorológica não está disponível no modo demonstração.',
    'Open the map to refresh weather data.': 'Abra o mapa para atualizar os dados meteorológicos.',
    'Weather update queued.': 'Atualização meteorológica colocada na fila.',
    'Requested weather data is already updating.': 'Os dados meteorológicos solicitados já estão sendo atualizados.',
    'NOAA: wait {value0} s before refreshing again.': 'NOAA: aguarde {value0} s antes de atualizar novamente.',
    'Weather update failed; previous data kept.': 'Falha ao atualizar os dados meteorológicos; os dados anteriores foram preservados.',
    'Weather updated partially; unavailable data kept.': 'Meteorologia parcialmente atualizada; dados indisponíveis foram preservados.',
    'Weather data updated.': 'Dados meteorológicos atualizados.',
    'NOAA {value0}: queued; waiting for the current update…': 'NOAA {value0}: na fila; aguardando a atualização atual…',
    'NOAA {value0}: update already in progress…': 'NOAA {value0}: atualização já em andamento…',
    'NOAA {value0}: wait {value1} s before refreshing again.': 'NOAA {value0}: aguarde {value1} s para atualizar novamente.',
    'NOAA {value0}: update failed; previous data kept.': 'NOAA {value0}: falha na atualização; dados anteriores mantidos.',
    'NOAA {value0}: partially updated; previous data kept.': 'NOAA {value0}: atualização parcial; dados anteriores mantidos.',
    'NOAA {value0}: updated.': 'NOAA {value0}: atualizado.',


}
with (po_dir / 'pt_BR.po').open('rb') as f:
    br = pofile.read_po(f, locale='pt_BR')
with (po_dir / 'en_US.po').open('rb') as f:
    en = pofile.read_po(f, locale='en_US')

template = Catalog(project='AeroScope', version='0.3.72', copyright_holder='AeroScope Contributors', creation_date=None)
messages = {}
for source in sorted((root / 'aeroscope').glob('*.py')):
    with source.open('rb') as f:
        for line, msgid, _comments, _context in extract.extract(
                'python', f, keywords={'_': None, 'ngettext': (1, 2)}):
            if msgid:
                messages.setdefault(msgid, []).append((f'aeroscope/{source.name}', line))
for msgid, locations in sorted(messages.items(), key=lambda pair: str(pair[0])):
    template.add(msgid, locations=locations)
    for cat, new in ((br, translations), (en, {})):
        entry = cat.get(msgid)
        if entry is None:
            if cat is br and msgid not in new:
                raise ValueError(f'Missing Brazilian Portuguese translation: {msgid!r}')
            cat.add(msgid, new[msgid] if cat is br else msgid, locations=locations)
        else:
            entry.locations = locations
for cat in (br, en):
    cat.version = '0.3.72'
    cat.project = 'AeroScope'
for cat in (template, br, en):
    percent = cat.get('10% translucent fill; 18% for the selected area, and subtler in tower mode.')
    if percent is not None:
        percent.flags.discard('python-format')
for path, catalog in ((po_dir / 'aeroscope.pot', template),
                      (po_dir / 'pt_BR.po', br), (po_dir / 'en_US.po', en)):
    with path.open('wb') as file:
        pofile.write_po(file, catalog, width=96, sort_output=True)
mo = root / 'aeroscope/locale/pt_BR/LC_MESSAGES/aeroscope.mo'
with mo.open('wb') as file:
    mofile.write_mo(file, br, use_fuzzy=False)
issues = [(str(msg.id), str(error)) for cat in (br, en)
          for msg, errors in cat.check() for error in errors]
if issues:
    for error in issues[:20]:
        print('ISSUE', error)
    raise RuntimeError(f'{len(issues)} translation validation errors')
print(f'OK: {len(template)} catalog messages; {len(br)} Brazilian translations; {mo.stat().st_size} byte MO')
