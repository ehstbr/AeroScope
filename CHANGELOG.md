## AeroScope 0.3.72 — unified refresh menu and NOAA status subtitle

- **Native refresh menu:** the single refresh icon in the header opens the
  same GTK/Gio-style menu as the application's hamburger button. Choose All,
  Aircraft, METAR or SIGMET; no adjacent split arrow or implicit action.
- **NOAA updates in the subtitle:** manual METAR/SIGMET progress, rate-limit
  waits, in-flight requests, and results use the existing window subtitle,
  never a transient toast. Notices briefly take precedence over routine ADS-B
  updates, then restore the latest ADS-B status; ADS-B errors remain visible.
- **Unchanged data policy:** per-product 60-second minimum, independent NOAA
  scheduling, and preservation of unrelated meteorological data remain intact.

---

## AeroScope 0.3.71 — manual refresh by source

The header refresh control is now a split button. Its main icon refreshes aircraft
and enabled METAR/SIGMET layers. The adjacent arrow lets you refresh **All**,
**Aircraft**, **METAR**, or **SIGMET** independently. NOAA manual refreshes may
bypass the 15-minute automatic cycle but observe a 60-second per-product request
floor; an in-flight weather request is coalesced or queued. A METAR-only refresh
preserves existing SIGMET data, and vice versa. The rest of the app's automatic
polling and Ctrl/Alt/F-key shortcuts are unchanged.

# AeroScope 0.3.70 — Navegação suave pelas teclas de seta

- **Setas ← ↑ ↓ →:** deslocamento em pixels, com aceleração suave enquanto pressionadas e pequena desaceleração ao soltar. Duas teclas permitem movimento diagonal sem excesso de velocidade.
- **Toque ou tecla mantida:** uma pressão breve produz um movimento perceptível; manter a tecla pressionada não reinicia a animação a cada repetição do teclado.
- **Foco preservado:** as setas só controlam o mapa quando ele está focado. A busca e demais controles mantêm suas teclas, assim como Ctrl+A/C/V, Alt e F1/F11.
- **Sem requisições por quadro:** a atualização da área continua sujeita à espera e aos limites de consultas. Os deslocamentos são calculados localmente pelo Libshumate.
- **Cancelamento seguro:** ao perder o foco, clicar no mapa ou centralizar um local, o movimento por teclado é interrompido. Navegar com as setas desliga o acompanhamento automático de aeronave.

---

# AeroScope 0.3.69 — Atalhos no menu do aplicativo

- **Menu sanduíche atualizado:** os atalhos existentes agora aparecem à direita dos itens correspondentes, no estilo nativo GTK4: Alt+T, Alt+S, Alt+M, Alt+A, Alt+B, Alt+E, Alt+P, Alt+, e Alt+Q, além de F1 e F11.
- **Nenhuma tecla nova foi criada:** os atalhos são apresentados junto às ações já existentes, preservando Ctrl+A/C/V para a edição de textos. Opções sem atalho continuam sem indicação.
- **Tela cheia:** o texto da opção deixa de conter “(F11)”, porque o GTK passa a exibir o atalho no local apropriado.

- Todos os atalhos próprios do aplicativo usam **Alt** em vez de Ctrl, inclusive **Alt++**, **Alt+−**, **Alt+A** (SIGMET) e **Alt+V** (aeronaves visíveis), sem combinações Ctrl+Alt.
- **Ctrl+A**, **Ctrl+C** e **Ctrl+V** continuam reservados para seleção, cópia e colagem, assim como outros atalhos de edição do GTK.
- **F1** (ajuda), **F11** (painel em tela cheia) e **Esc** (sair da tela cheia) permanecem sem modificadores.
- Atualizados os aceleradores de Preferências (**Alt+,**) e Sair (**Alt+Q**), a janela de atalhos, as traduções e os testes.

---

# AeroScope 0.3.67 — Atalhos com Ctrl e janela de ajuda corrigida

- Comandos de zoom, busca, localização, camadas e monitoramento agora exigem **Ctrl**, inclusive **Ctrl++** e **Ctrl+−**; F1 e F11 continuam funcionando sem Ctrl.
- O mapa recebe foco inicial em vez de manter o campo de busca selecionado; um clique em espaço vazio também transfere o foco para o mapa.
- Atalhos continuam disponíveis quando a busca está focada, sem interferir em Ctrl+A (selecionar tudo), Ctrl+C (copiar), Ctrl+V (colar) e outros controles comuns de edição. Para preservar essas três combinações, SIGMET usa Ctrl+Alt+A e a lista de aeronaves visíveis usa Ctrl+Alt+V.
- Janela de atalhos com apenas uma barra de título, eliminando o cabeçalho duplicado.

---

# AeroScope 0.3.66 — Correção dos atalhos no GTK4

- Corrigido o modificador de teclado Alt para o nome compatível com GDK4: `Gdk.ModifierType.ALT_MASK`. Em 0.3.65, `MOD1_MASK` provocava um traceback toda vez que uma tecla era pressionada.
- Mantidos os atalhos já introduzidos em 0.3.65, incluindo zoom, localização, busca e janela de ajuda.
- Adicionado teste de regressão que executa o callback de teclado com uma representação de GDK4 sem `MOD1_MASK`.

---

# AeroScope 0.3.65 — Animação de entrada e saída dos widgets

- **Posição fixa ao recolher/expandir:** aeronaves, aeroportos e estações mantêm o canto superior esquerdo imóvel quando mudam de tamanho. A posição agora é salva em uma âncora relativa ao mapa inteiro, e não ao espaço livre após descontar o tamanho do cartão.
- **Migração das posições anteriores:** os layouts `dashboard.json` da versão 0.3.62 continuam aceitos e são convertidos automaticamente, preservando o enquadramento sempre que possível.
- **Animação GTK4 discreta:** `Gtk.Revealer` desliza o conteúdo verticalmente ao recolher/expandir (220 ms), sem animações custosas nem impacto no radar. O cabeçalho e os controles continuam no lugar.
- **Dados e Favoritos preservados:** nada foi alterado na consulta de METAR/SIGMET, no monitoramento ADS-B, nas preferências ou nos controles de centralizar/acompanhar.
- **Teste visual:** na sessão GTK real, confira o mesmo widget perto do centro e próximo à borda inferior, além de reiniciar o aplicativo e alternar F11.

---

# AeroScope 0.3.62 — Widget de aeronave verdadeiramente compacto

- **Cartão de aeronave com foco nos dados:** identificação, matrícula e modelo; altitude; velocidade no sistema de unidades das Preferências; razão de subida/descida; rumo com direção cardinal; squawk; tipo de fonte ADS-B/MLAT; posição e ICAO24. Dados ausentes são indicados por travessão, sem inferências.
- **Widget sem fotografia incorporada:** o cartão apresenta somente dados ADS-B e fica com largura aproximada de 310 px. Quando uma foto estiver disponível, um ícone discreto no cabeçalho abre a visualização ampliada existente, com os créditos no tooltip. A imagem não influencia mais o tamanho do cartão.
- **Recolhido com mais conteúdo:** identificação/modelo e quatro leituras em uma grade 2×2 (altitude, velocidade, rumo e razão de subida/descida), além do estado do sinal e alerta de emergência se houver; o cartão continua pequeno.
- **Alerta prioritário:** destaca somente sinais de emergência/atenção efetivamente informados, preservando o código squawk na grade e evitando inferências sobre declarações de emergência.
- **Cartão recolhido:** exibe altitude e velocidade, com estado do sinal e controles no cabeçalho. Não faz novas requisições, não consulta histórico nem altera o monitoramento de aeronaves.
- **Atualizações sem reconstrução:** os valores recebem as atualizações ADS-B na própria grade. Quando o sinal some, a última posição é preservada com identificação de sinal perdido.
- **Teste recomendado:** conferir em GTK4/GNOME os cortes de texto, o comportamento do thumbnail e a mudança de altura do cartão enquanto arrasta.

---

# AeroScope 0.3.60 — Widgets flutuantes para aeronaves e ação de acompanhamento

- **Aeronaves nos painéis:** clique com o botão direito em uma aeronave e use **Criar painel flutuante**. O cartão mostra foto e crédito quando disponíveis, identificação/voo, altitude, velocidade, rumo, squawk/alerta e último sinal ADS-B. Não consulta nem exibe o histórico de voos no widget.
- **Ações discretas ao lado do X:** no cabeçalho do painel de aeronave, botões pequenos para **centralizar** suavemente no mapa e **acompanhar/parar acompanhamento** (com estado sincronizado ao painel lateral). Continuam acessíveis quando o widget está recolhido. Se a aeronave deixar de aparecer no radar, os botões são desativados, e a última informação fica marcada como sinal perdido.
- **Fotos reaproveitadas:** os widgets utilizam o mesmo cache e serviço de fotos do painel lateral, sem requisições duplicadas; quando disponíveis, um clique abre a foto ampliada. Não inventam imagem quando a API falha.
- **Widgets persistentes:** os cartões de aeronaves compartilham o modo tela cheia, a translucidez, a movimentação suave do arraste e a persistência de posições dos cartões meteorológicos. O identificador ICAO24 permite restabelecer o cartão após reiniciar.
- **Resposta routeset inválida:** respostas HTTP sem conteúdo, JSON vazio/incorreto e excesso de tamanho são tratados com mensagens legíveis; origem e destino permanecem indisponíveis quando o provedor não fornece uma associação válida.
- **Teste recomendado no GNOME:** mover e recolher cartões de aeronaves, centralizar, ativar/desativar seguimento, abrir foto, perder sinal e reiniciar para conferir persistência; a renderização GTK requer teste visual no Ubuntu.

---

# AeroScope 0.3.59 — Translucidez discreta nos widgets flutuantes

- **Fundo levemente translúcido:** os cartões meteorológicos exibidos sobre o mapa têm fundo com 90% de opacidade, deixando aproximadamente 10% do mapa aparecer através deles.
- **Leitura preservada:** títulos, VFR/MVFR/IFR/LIFR, alertas SIGMET, barra de validade e botões continuam opacos e legíveis; a transparência não é aplicada ao widget inteiro.
- **Aparência integrada:** mantém cores do tema claro/escuro do GNOME, cantos arredondados, borda suave e sombra original. Não usa desfoque de fundo e não modifica a renderização do mapa.
- **Sem alterar dados ou preferências:** os widgets existentes conservam posições, tamanho recolhido/expandido e persistência da versão anterior.

---

# AeroScope 0.3.58 — SIGMET no aeroporto, mesmo sem METAR, e barras de validade

- **Meteorologia complementar:** detalhes de aeroportos e estações exibem SIGMETs ativos cujo polígono horizontal contenha as coordenadas do local, mesmo quando também há METAR. Se não houver METAR, o aviso SIGMET ainda aparece, sem inventar categoria VFR/IFR.
- **Favoritos e widgets flutuantes:** mostram indicador SIGMET e fenômenos conhecidos de forma independente do METAR. No widget recolhido, o aviso continua visível. Estações preservam as coordenadas salvas para consultar avisos mesmo após reiniciar e quando a NOAA não entrega METAR.
- **Validade visual:** barras discretas de aproximadamente 4 px nos detalhes SIGMET e nos widgets expandidos, com início e término em UTC, avanço proporcional ao período e atualização a cada minuto. Só aparecem quando a NOAA fornece ambos os horários com ordem válida; porcentagem significa **tempo transcorrido**, nunca severidade do fenômeno.
- **Consulta SIGMET independente:** a verificação dos aeroportos/estações monitorados continua quando o mapa é deslocado, quando a camada SIGMET está ocultada e sem depender de METAR. Consultas NOAA regionais agrupam localidades próximas, possuem limite de frequência, cache de 15 minutos e distinguem falha de consulta de ausência de aviso.
- **Segurança da interpretação:** uma área SIGMET que inclua o aeroporto não significa ocorrência do fenômeno na pista ou na altitude de superfície. O AeroScope não altera o indicador de regras de voo com base apenas nesse aviso; não substitui informação aeronáutica oficial.
- **Testes:** inclui regressões para validade, metadados UTC, região geográfica, cobertura sem METAR, duplicação de avisos e composição das telas.

---

# AeroScope 0.3.57 — Modo Painel em tela cheia e mapa orientado ao norte

- **Tela cheia:** pressione **F11**, use **Menu → Janela → Painel em tela cheia** ou o botão discreto **Sair da tela cheia**. O modo oculta o cabeçalho e o painel lateral; **Esc** ou **F11** restaura a interface completa.
- **Orientação norte no topo:** desativa somente o gesto nativo de rotação da biblioteca Libshumate e restaura rotação zero caso algum outro componente a altere. Arrastar e ampliar com dois dedos continuam disponíveis. A restrição também vale para o mini-mapa.
- **Painéis flutuantes:** clique com o botão direito sobre um aeroporto ou estação NOAA e selecione **Criar painel flutuante**. Podem ser abertos até 20 painéis simultâneos. Arraste-os pelo cabeçalho; **X** fecha e o botão de seta recolhe/expande o conteúdo. O menu mostra **Remover painel flutuante** quando aquele local já está aberto.
- **METAR informativo:** cada painel mostra ICAO, nome, condição (VFR/MVFR/IFR/LIFR quando NOAA informar), vento, visibilidade, nuvens, temperatura, QNH e outros campos disponíveis, além de data/hora da **observação e última consulta em UTC**, em tipografia discreta. Dados inexistentes não são inventados. O cartão sinaliza falhas sem tratar boletins antigos como atualizações.
- **Persistência:** tela cheia, itens abertos, posições proporcionais e estado recolhido ficam em `~/.config/aeroscope/dashboard.json` (ou em `$XDG_CONFIG_HOME/aeroscope/dashboard.json`). O layout é recuperado ao reiniciar e adaptado à área disponível do mapa.
- **NOAA em lote:** painéis utilizam o mesmo cache e monitoramento de METAR da aba Favoritos, com intervalos de 15 minutos e sem chamadas por quadro ou por movimento. Um widget não precisa estar favoritado; nesse caso, não ativa notificações de alterações por si só. O monitoramento visual dos painéis continua mesmo com a opção de monitoramento dos Favoritos desativada.
- **Mini-mapa como miniatura visual:** usa o mesmo tema de mapa, modo Torre de Controle, anéis, distâncias, varredura sincronizada, relógio relativo e opções de exibição de aeronaves, aeroportos, METAR e SIGMET do mapa principal. Não realiza uma segunda busca de voos ou meteorologia para desenhar essas camadas. O mini-mapa mantém controle próprio de enquadramento e zoom.
- **Arraste dos painéis corrigido:** usa coordenadas da superfície da janela, evitando a oscilação causada por offsets calculados em relação ao próprio widget em movimento.
- **Painel recolhido:** agora mostra apenas o identificador do aeroporto/estação e a categoria VFR/MVFR/IFR/LIFR (ou — quando não houver dados), escondendo observação e atualização; os horários voltam ao expandir.
- **Menus de contexto:** os tooltips dos marcadores ficam suspensos enquanto o menu do botão direito estiver aberto e são restaurados após o fechamento, sem desativar os tooltips do restante do aplicativo.
- **Validação automatizada:** inclui regressões para bloqueio de rotação sem bloquear zoom, persistência, entrada malformada, atalhos e integrações. A execução real em GTK4/Wayland/X11 e em tela touch exige teste no Ubuntu.

**Atenção:** o METAR recebido da NOAA é destinado a acompanhamento informativo; para decisões operacionais aeronáuticas, confirme os boletins oficiais e sua validade.

---

# AeroScope 0.3.55 — Geolocation Gettext fix and smooth favorite navigation

- Fixes `TypeError: 'tuple' object is not callable` in geolocation when reusing an approximate IP location or a GeoClue fix. The same Gettext `_()` argument-shadowing risk was removed from main search, favorite searching and adding, and the About dialog.
- When centering a **favorite aircraft already in the regional radar**, reuses the native smooth selection pan and preserves the current zoom. For a distant favorite outside the regional area, smoothly animates the flight to the new position and zoom while keeping the existing regional-fetch logic.
- Includes automated tests that execute the cached-IP callback path with a simulated GTK click and assert smooth favorites navigation, plus an AST regression scan of all Python files.
- No change to aircraft position interpolation, follow mode, METAR polling, stored favorites or the Gettext message IDs. The full-screen floating-widget dashboard remains a separate future feature.

---

# AeroScope 0.3.54 — Correção da galeria de fotografias

- Corrige o conflito entre argumentos dos callbacks GTK (`lambda *_`) e a função GNU Gettext `_()` nos botões **Original photo** e **View aircraft gallery**.
- Adiciona testes de regressão para execução dos callbacks de fotografias com argumento de clique, além de verificação estática em todos os módulos.
- Mantém os recursos e configurações da versão 0.3.53 sem alterações.

---

# AeroScope 0.3.54 — Automatic locale, airport and station favorites, NOAA METAR notifications

- **Language / Idioma:** default **Automatic (system)** now honors Ubuntu's `pt_BR` locale, with English-US native source. Users may explicitly choose English or Portuguese in Preferences; changes take effect after restart. Old implicit `en_US` settings are migrated to Automatic.
- **Map right-click:** aircraft context menu includes **Center aircraft**. Airport right-click immediately opens its inspector, so the redundant **Open airport details** item is removed; the menu offers **Center airport** and add/remove favorite. NOAA weather stations retain their context actions.
- **Airport and station favorites:** ICAO stations have a separate local bookmark store; both types appear in the same Favorites tab and do **not** use slots or remote requests from the aircraft watchlist.
- **METAR in Favorites:** displays a compact, color-coded flight category (VFR/MVFR/IFR/LIFR) and UTC observation time, or METAR when NOAA does not supply a flight category. Raw reports and full interpreted weather remain in the airport/station inspector. Clicking the location name/condition in Favorites opens its inspector; the separate map-center and remove actions are unchanged. The NOAA station ID is always ICAO, even when the airport badge is IATA.
- **METAR change notifications:** monitoring and notification switches are found under **Preferences → Monitor**. Automatic monitoring and notifications are enabled by default. Favorites are checked via NOAA batched requests every 15 minutes (when running, including tray mode), without being constrained by the visible map. Each valid station's first report establishes a baseline; repeated, missing or failed reports do not notify. Notifications describe bulletin changes, not necessarily severe weather.
- **Add favorites from the + button (0.3.54):** the add panel now searches current aircraft, the built-in IATA/ICAO airport catalog (including names), and NOAA stations loaded around the map. Select a result to favorite it. Enter a four-character station ICAO not currently on the map to perform an explicit NOAA METAR lookup and, if a valid location is returned, save it as a monitored station. Searches on typing are local (no repeated API calls). Airports and stations still do not use the 12-aircraft monitoring slots.
- **GTK context menu lifetime (0.3.54):** popovers are detached and marker-rebuilding actions invoked after the current GTK event, mitigating a `gtk_widget_is_ancestor` critical reported during interaction. A GTK desktop session is required to confirm the runtime warning has disappeared.
- **Refresh:** the Favorites refresh button also requests new METAR information, with a minimum one-minute gap to limit repeated network calls. Airport/station reports can also be viewed on demand.

Weather reports are provided by NOAA, are not guaranteed to exist for every ICAO identifier, and are **not** a substitute for official preflight meteorological information. A 15-minute poll may detect a change after it has been published.

The original source language is English (United States), with a Brazilian Portuguese catalog at `po/pt_BR.po`; all new user-facing text is translated using Gettext. See `po/README.md` for updating translations.

---

# AeroScope 0.3.49

### 0.3.49 — Painéis de aeroportos e estações METAR compactos

- Aeroportos e estações meteorológicas agora usam cabeçalho consistente com os detalhes de aeronaves: **título à esquerda, Centralizar e Fechar à direita**, ambos como ícones planos com dicas ao passar o mouse.
- O botão grande **Centralizar aeroporto** e o botão grande **Centralizar estação** foram removidos, liberando espaço vertical para relatórios METAR e ações complementares.
- **Fechar** funciona também no painel de aeroportos, usando o mesmo descarte da seleção dos demais tipos de detalhes.
- Centralizar usa a transição suave já existente do mapa, preservando o zoom, sem novas chamadas à NOAA nem ao ADSB.lol.
- Títulos longos não forçam crescimento da largura do painel; mostram o nome completo na dica ao passar o mouse.

### Histórico — 0.3.48

### 0.3.48 — SIGMET por fenômeno, preenchimento discreto e destaque da seleção

- **Paleta SIGMET por fenômeno**: contorno e borda do símbolo em laranja (tempestades), dourado (turbulência), azul (gelo), sépia (cinzas vulcânicas/poeira), roxo (ciclones), verde-água (ondas de montanha), vermelho discreto (nuvem radioativa) e cinza-azulado (genérico). Classificação compartilhada com a tradução NOAA para evitar cores contraditórias. Quando desativada, mantém contorno e símbolo laranja no estilo anterior.
- **Preenchimento translúcido** nos polígonos: 10% no SIGMET normal e 18% no selecionado. No modo Torre, a transparência é reduzida a 6,5% e 11,7%; as bordas permanecem visíveis. Quando selecionado, o contorno fica mais espesso e contínuo.
- **Duas preferências novas**, ativadas por padrão em Aparência → Meteorologia: Mostrar preenchimento das áreas SIGMET e Usar cores por tipo de fenômeno SIGMET. Podem ser desligadas separadamente e atualizam os mapas imediatamente, inclusive PiP, sem consultas extras à NOAA.
- **Renderizador preservado:** um único `Gtk.DrawingArea` Cairo por mapa, simplificação por zoom e seleção da geometria original; cores pré-calculadas por aviso a cada resposta NOAA, não a cada quadro. Desenhos são caminhos separados por aviso, sem linhas diagonais conectando polígonos distintos.
- O efeito de cor não implica classificação meteorológica quando o dado NOAA não identifica o fenômeno; avisos genéricos permanecem neutros.

---

## Histórico: versão 0.3.47

### 0.3.48 — SIGMET otimizado para navegação e zoom

- **Um único desenho Cairo de contornos SIGMET por mapa**, no lugar de até 195 camadas individuais Libshumate `PathLayer` (65 avisos × 3 anéis). Os polígonos desconexos são desenhados como subcaminhos separados, sem diagonais entre eles. Clique e seleção permanecem funcionais.
- **Apenas avisos visíveis** (com margem de 48 px) entram no desenho. As geometrias fora da tela são descartadas por caixas delimitadoras em Mercator, inclusive ao navegar por novas regiões. Todos os avisos retornados pela consulta NOAA são mantidos: o limite visual antigo de 65 avisos foi removido.
- **Contornos simplificados por zoom:** filtragem radial e Ramer–Douglas–Peucker, com cache de até quatro níveis por anel. Os originais NOAA são mantidos para selecionar a área exata e traduzir o SIGMET.
- **Atualizações incrementais:** respostas NOAA com a mesma geometria reutilizam os anéis e os caches; boletins idênticos reutilizam os próprios objetos. O mini-mapa e o mapa principal compartilham a preparação das geometrias, mas usam suas câmeras para desenhar somente suas áreas visíveis.
- **Ícones SIGMET controlados:** uma camada de marcadores por mapa, com até 36 símbolos visíveis sem sobreposições excessivas. Os ícones são atualizados após um curto debounce de 240 ms ao mover/alterar o zoom. As áreas continuam selecionáveis no mapa principal, mesmo sem símbolo visível.
- **METAR separado:** estações continuam em camada própria; reconstrução de seus widgets somente quando os dados/condições efetivamente mudam. Sem chamadas adicionais às APIs NOAA ou ADSB.lol.
- **Diagnósticos de desempenho:** logs DEBUG mostram avisos e vértices desenhados e custo do traçado (amostrados, nunca por quadro). Benchmark sintético reproduzível: `PYTHONPATH=. python3 benchmarks/bench_sigmet_geometry.py`.

**Benchmark sintético de geometria, não de FPS:** no cenário de 150 avisos/37.500 vértices, zoom 6, o novo desenho selecionou 71 polígonos (~1.175 vértices simplificados) e o processamento de visibilidade e cache consumiu ~0,1 ms em média por consulta, neste ambiente. O desempenho gráfico real precisa ser conferido no GTK/GNOME/KDE e depende dos mapas, da GPU e da NOAA.

---

## Histórico: versão 0.3.46

### 0.3.46 — Avisos SIGMET sem texto flutuante e geolocalização repetível

- Removido o texto branco flutuante **“SIGMET: N avisos na região”** (e outros avisos textuais da camada NOAA) do mapa principal e mini-mapa. As áreas SIGMET continuam destacadas por seus contornos e pictogramas; os detalhes completos ficam no painel lateral quando selecionados. Erros da NOAA continuam registrados nos logs, sem ocultar o mapa.
- **Agora não** encerra apenas o convite de localização por IP atual. Clicar novamente em Geolocalizar, tanto no mapa principal como no mini-mapa, volta a mostrar o mesmo aviso se GeoClue estiver indisponível/desativado.
- A oferta **automática** continua limitada a uma vez por sessão, e **Não sugerir novamente** continua respeitado. A consulta de localização por IP exige consentimento; não são introduzidas consultas ocultas.



### 0.3.46 — Painel de aeronaves compacto e localização por IP padronizada

- Nos detalhes de aeronaves, **Acompanhar** (botão com estado pressionado), **Centralizar** e **Favoritar** agora são ícones ao lado do nome/indicativo, junto ao botão de fechar. A antiga linha de botões grandes foi removida para liberar espaço vertical.
- O aviso de localização aproximada por IP é o **mesmo componente** tanto no mapa principal quanto no PiP, incluindo ordem fixa de botões em coluna, texto e largura. Continua exigindo consentimento antes de consultar serviço externo e preserva a opção de não sugerir novamente.
- Sem alterações na busca de aviões, dados NOAA ou intervalos do radar.


### 0.3.46 — Estações meteorológicas com inspetor único e geolocalização consistente

- Estações METAR regionais **sem aeroporto da base interna** agora possuem ícone de estação meteorológica (mastro/anemômetro), código ICAO e categoria NOAA quando existente, distintos dos ícones de aeroportos.
- Clicar na estação abre o mesmo inspetor lateral traduzido em português usado pelos aeroportos: temperatura, vento, visibilidade, nuvens, observação UTC e METAR técnico recolhido. Não abre mais um diálogo separado. A ação no PiP abre a janela principal para mostrar o mesmo inspetor.
- Estações cujo ICAO corresponde a um aeroporto cadastrado continuam usando os detalhes desse aeroporto. A consulta individual por ICAO reutiliza a observação regional já disponível, sem requisitá-la novamente.
- Avisos breves de geolocalização por GeoClue/IP aparecem na janela atualmente em uso: PiP quando aberto e janela principal caso contrário. Os mesmos pedidos de permissão e as mesmas mensagens se aplicam aos dois mapas.

### 0.3.43 — METAR regional e SIGMET compreensível

- Aeroportos locais com código ICAO conhecido agora recebem consulta METAR **em lote** na inicialização e nas mudanças de região. Ex.: CNF/SBCF e PLU/SBBH. A consulta geográfica continua cobrindo outras estações; dados ausentes não são inventados. Consultas por lote respeitam cache de 15 minutos, limites e erros da NOAA.
- Cada área SIGMET recebe uma etiqueta clicável dentro do polígono com pictograma de fenômeno quando identificável: tempestades, turbulência, gelo, cinzas vulcânicas, ciclone, poeira, ondas de montanha etc. Sem código reconhecido, permanece um aviso SIGMET genérico.
- Clicar na etiqueta SIGMET agora seleciona um **inspetor meteorológico no painel lateral**, com explicação simples em português, qualificações/validade quando presentes e o boletim original recolhido em um expansor. No mini-mapa, o clique traz a janela principal para exibir os detalhes.
- Avisos meteorológicos indicam **condições observadas ou previstas** conforme o boletim; não são radar de chuva ou previsão de superfície. As áreas representam aproximações publicadas pelo provedor.

### Novidade 0.3.43 — NOAA já na primeira consulta e ao mudar de região

- Com **METAR** ou **SIGMET** ativados, o AeroScope inicia a primeira consulta NOAA assim que chega a primeira resposta regional do ADSB.lol, inclusive durante o aquecimento. Não precisa selecionar aeroporto ou aguardar o temporizador de 30 segundos.
- Mover o mapa principal ou mini-mapa para uma nova área inicia nova consulta quando a mudança geográfica é significativa (a partir de 75 milhas náuticas do centro da consulta anterior), independentemente de o radar regional ainda estar usando a cobertura de 250 NM em cache.
- A consulta NOAA permanece em **15 minutos após a conclusão da consulta** para a região atual; deslocamentos para nova região podem antecipá-la, com intervalo mínimo de 15 segundos entre pedidos para evitar rajadas enquanto o mapa está sendo arrastado.
- Se o mapa mudar de região enquanto houver consulta em andamento, o AeroScope atualiza a nova região assim que possível. Favoritos, emergências, consultas ADS-B e cache de METARs individuais não são alterados.
- Consultas meteorológicas seguem opcionais e **não acontecem** quando o aplicativo está somente na bandeja, sem mapa visível.



### Novidades 0.3.43 — Largura estável do painel lateral

- O inspetor de aeroportos e aeronaves utiliza rótulos com largura natural limitada. Valores longos como **Nuvens**, vento e avisos meteorológicos ficam em parágrafo separado com quebra de linha, sem alargar a barra lateral.
- A mesma política se aplica à lista Visíveis, à busca, às páginas Favoritos e Emergências (incluindo históricos e mensagens de erro). Palavras e identificadores muito longos quebram dentro dos cartões.
- A largura do painel passa a ser definida pela divisória redimensionável. Alternar entre abas ou abrir detalhes não deve alterar a largura escolhida pelo usuário. O painel mantém largura mínima de 318 px.
- Nenhuma mudança de fontes de dados, monitoramento ou indicadores METAR.

## Histórico: versão 0.3.40

### Novidades 0.3.40 — Aeroportos e METAR visíveis

- Aeroportos da base interna aparecem no mapa com **ícone + código IATA**, no lugar de um losango genérico. Ex.: CNF, GRU, DIQ. Eles continuam visíveis mesmo quando o METAR está desligado ou sem dados.
- Ao ativar METAR, os ícones dos aeroportos recebem a classificação realmente fornecida pela NOAA (**VFR, MVFR, IFR ou LIFR**). Observações sem classificação não recebem uma categoria inventada.
- Estações adicionais da região aparecem com **ICAO + categoria** e podem ser clicadas para ler as condições meteorológicas traduzidas. O mapa principal evita desenhar uma estação duplicada sobre um aeroporto já identificado; no mini-mapa a camada METAR continua disponível.
- O mapa atualiza visualmente as categorias ao receber respostas NOAA e ao receber o METAR específico de um aeroporto, reutilizando resultados em cache; não faz consultas individuais para todos os aeroportos.
- A marca textual flutuante **METAR / SIGMET: NOAA** foi retirada do mapa e a fonte foi incluída em **Sobre o AeroScope**. A atribuição exigida pelo provedor do mapa (OpenStreetMap e outros) continua compacta no mapa por exigência de licença.
- Uma consulta válida sem METAR agora é informada como **nenhuma estação com observação na área consultada** em vez de aparentar uma camada que não funciona.


### Novidade 0.3.40 — METAR em português simples

- Ao selecionar aeroportos, o painel apresenta um resumo das condições de visibilidade e teto de nuvens, vento (direção e velocidade em km/h), temperatura, ponto de orvalho, visibilidade (km), nuvens (alturas aproximadas em metros) e pressão (hPa), conforme os dados disponíveis na resposta decodificada da NOAA.
- As categorias VFR/MVFR/IFR/LIFR são descritas em linguagem acessível, sem confundi-las com autorização operacional ou previsão meteorológica.
- A observação técnica original continua acessível no expansor **Ver METAR original**.
- Marcadores METAR no mapa também apresentam a tradução no diálogo, preservando o código técnico para consulta.
- Usa as mesmas consultas NOAA e cache existentes, sem requisições extras.


### Novidade 0.3.40 — Centralização de emergências sem trocar de aba

- O botão Centralizar de Emergências desloca o mapa até o avião e **mantém a aba Emergências ativa**. Os dados da ocorrência aparecem no painel de detalhes sem depender de a aeronave estar na consulta regional.
- Aeronaves detectadas apenas mundialmente ganham um **marcador temporário**, destacado no mapa, com aviso de que a posição é da última consulta global. Quando o radar regional encontra o mesmo ICAO24, o marcador temporário dá lugar ao normal.
- A lista Visíveis continua representando apenas as aeronaves realmente consultadas pelo radar regional, sem misturar dados da pesquisa mundial.



## Histórico — versão 0.3.37 — NOAA sem RainViewer

- RainViewer foi retirado integralmente da integração: nenhuma consulta, camada ou preferência de chuva é mantida.
- O METAR NOAA aparece no painel lateral ao selecionar qualquer aeroporto cadastrado, mesmo quando a camada global de estações está desligada. Consultas assíncronas por código ICAO com cache de 15 minutos.
- SIGMET NOAA informa quando não há avisos ativos na região, quando há avisos e quando o serviço falha. Erros METAR/SIGMET são isolados para não bloquear o outro produto; consultas sem dados são distintas de falhas.
- São preservados os zooms animados, o monitoramento de aviões, favoritos, emergências e os intervalos regionais.


## Histórico — 0.3.36: Meteorologia aeronáutica e zoom suave

- **Zoom animado:** os botões `+`/`−` e a rolagem do mouse usam `Shumate.Map.set_animate_zoom(True)` no mapa principal e no mini-mapa. Os botões chamam `zoom_in()`/`zoom_out()` em vez de alterar diretamente o nível de zoom.
- **Chuva (recurso removido):** a versão 0.3.36 utilizava RainViewer, mas a integração foi retirada na 0.3.37 devido às limitações de zoom do serviço gratuito.
- **METAR NOAA:** consultas regionais à API oficial de Aviation Weather (`/api/data/metar?bbox=...&format=geojson`) a cada 15 minutos; mostra marcadores de estações no mapa e informações brutas clicáveis. METARs têm horários próprios e **não são meteorologia em altitude de cruzeiro**.
- **SIGMET NOAA:** sobreposição opcional de contornos geográficos (`/api/data/sigmet?bbox=...&format=geojson`), com marcador para abrir o boletim; dados consultivos. Sujeito à cobertura da NOAA e ao GeoJSON oferecido pelo provedor.
- **Interface:** submenu `Visualização → Meteorologia` e controles equivalentes em `Preferências → Aparência → Meteorologia`. As opções NOAA são independentes, sincronizadas e começam **desligadas**.
- **Desempenho:** consultas assíncronas separadas do ADSB.lol, feitas somente quando há mapa visível e respectiva camada ativada. As duas janelas reutilizam o mesmo resultado de API, sem duplicar consultas; sem consultas meteorológicas quando só a bandeja do sistema está ativa. HTTP 429/erros de rede não interrompem o radar.
- **Limites:** consulta NOAA restrita à região do centro do mapa (janela geográfica de aproximadamente 7°×6°), sem tentar obter todas as estações/avisos do mundo. A API oficial limita a 400 resultados por consulta e 100 requisições por minuto; dados podem estar ausentes. SIGMETs não substituem briefing meteorológico oficial.

Fontes e termos: https://aviationweather.gov/data/api/

## Histórico — versão 0.3.35 — Posição do mini-mapa em várias telas

- **PiP no monitor correto:** ao mostrar o mini-mapa, identifica o monitor que contém a maior parte da janela principal **antes de ocultá-la**. Em sistemas com mais de uma tela, não utiliza automaticamente o monitor primário. Se for aberto novamente pela bandeja, reutiliza o último monitor registrado.
- **Canto inferior direito e margem de 24 px:** no X11, pede a posição ao gerenciador de janelas e respeita, quando disponível, a área útil EWMH (`_NET_WORKAREA`) para evitar o painel. A janela pode ser livremente movida/redimensionada depois, sem ficar voltando para o canto.
- **GNOME/KDE em Wayland:** mantém o monitor de origem registrado, mas o protocolo xdg-toplevel não permite ao próprio app impor uma posição absoluta. Nesses ambientes o compositor escolhe a posição; usar uma regra do KWin ou uma extensão/configuração do compositor é necessário para posicionamento garantido. Não há uso de shell, GTK3 ou utilitários externos para contornar isso.
- Não altera os intervalos, as consultas, o funcionamento do modo residente nem o monitoramento de favoritos e emergências.



## Novidades da versão 0.3.35 — Login automático e intervalos regionais independentes

- **Iniciar automaticamente ao fazer login:** opção em **Preferências → Monitor → Janela e segundo plano**. Cria/remove o arquivo `~/.config/autostart/io.github.ehstbr.Aeroscope.desktop` do próprio usuário. Não exige root, systemd ou instalação de um serviço.
- **Início silencioso:** `aeroscope --background` abre apenas o monitor de Favoritos/Emergências na bandeja, sem mapa visível, sem aquecimento regional e sem localização automática. Os alertas globais continuam usando as opções e intervalos existentes. No GNOME sem suporte à bandeja, abre a janela principal após uma verificação curta, para não ficar inacessível.
- **Dois intervalos de radar:** **Mapa aberto (janela/PiP)** e **Somente na bandeja**; ambos começam em 10 segundos e oferecem 10, 15, 20, 30, 45, 60, 120, 240, 480 e 600 segundos. O intervalo da bandeja aceita ainda **Desativado**: apenas Favoritos e Emergências continuam consultando.
- Se o usuário abriu a região no mapa e depois o ocultou, continua consultando **a última região visualizada** no intervalo de bandeja configurado. Na primeira abertura de mapa após o login silencioso, a consulta regional é iniciada imediatamente.
- As preferências antigas são migradas preservando o intervalo da janela (`refresh`) e aplicando 10 segundos por padrão em segundo plano. As consultas regionais nunca duplicam as verificações globais de alertas.
- **Importante:** intervalos muito longos reduzem a resolução temporal do rastro e não recuperam curvas não observadas. Limites de requisição (incluindo HTTP 429) continuam valendo.


### Novidades 0.3.33 — Posição virtual móvel e histórico dos Favoritos

- **Varredura realista:** a linha giratória agora testa o encontro com a posição **estimada em movimento** (interpolação temporal entre posições ADS-B já recebidas), e nunca com a posição antiga do marcador congelado. A geometria cruza os ângulos da linha e do avião em dois instantes consecutivos, inclusive na transição de 359° para 0°. Não faz consultas extras à API.
- **Sem salto brusco:** após a linha alcançar a posição virtual em que a aeronave está naquele momento, o ícone executa um deslocamento suavizado e limitado em duração (0,55 a 1,5 segundo) em vez da antiga corrida de 0,38 segundo para a frente. Desligar a varredura continua liberando imediatamente os pontos já recebidos e voltando à animação contínua.
- **Histórico de Favoritos:** novo botão de ícone ao lado de Atualizar, idêntico ao da aba Emergências. Exibe cartões cinza de observações anteriores, com o estado e os horários em que a observação começou e foi alterada. Entre os estados observáveis: possível voo, detectada no solo, rastreada sem estado definido, sem posição recente e sem sinal após **duas consultas globais** distintas.
- O histórico é apenas da sessão, continua sendo registrado enquanto AeroScope estiver em segundo plano e não confunde sair do raio de 250 NM com pouso. Falhas de API não criam eventos. Horários refletem observações do aplicativo, não eventos oficiais de voo.

### Novidades 0.3.33 — Legendas acessíveis pelo menu hambúrguer

- A seção **Visualização → Identificação dos aviões** agora tem um submenu com opções exclusivas: **Desativadas**, **Matrícula (ICAO24 se indisponível)** e **Somente ICAO24**.
- O submenu é um grupo de seleção nativo (`Gio.Menu` + `Gio.SimpleAction` de estado `string`); a opção ativa aparece marcada, sem permitir selecionar dois modos simultaneamente.
- Mudar a opção no menu atualiza imediatamente os ícones do mapa principal e do mini-mapa, salva o ajuste e sincroniza o seletor correspondente se as Preferências estiverem abertas. Também funciona no sentido inverso.
- O padrão permanece **Desativadas** para evitar poluição visual. Não há novas consultas à API nem alterações na movimentação das aeronaves.


### Novidades 0.3.33 — identificações e correção do cabeçalho

- **Etiquetas opcionais nos aviões:** Preferências → Aparência → Visualização no mapa → **Identificação junto aos ícones dos aviões**. Escolha **Desativadas** (padrão), **Matrícula (ICAO24 se indisponível)** ou **ICAO24**. A legenda escura fica abaixo da silhueta em orientações legíveis, acompanha cada marcador animado e também aparece no mini-mapa. Nenhuma consulta extra à API é necessária.
- **Cabeçalho corrigido:** removido o botão redundante de geolocalização do canto esquerdo. A geolocalização continua ao lado dos controles +/−; o comando explícito de localização por IP permanece no menu do aplicativo com a mesma confirmação de privacidade.
- **Atualizar aeronaves restaurado:** o comando manual foi removido por engano na 0.3.30 e voltou ao cabeçalho. Consultas automáticas e limitações da API permanecem iguais.



### Correções 0.3.33 — aros da Torre e barra superior

- Corrigido o desenho dos círculos no modo Torre: a API Cairo conserva o ponto final do texto após `show_text()`; `arc()` em seguida cria uma conexão diagonal se o caminho não for reiniciado. Agora cada círculo inicia um novo caminho e o texto também limpa o caminho anterior. Isso remove as diagonais espúrias sem alterar as distâncias, os círculos nem a varredura giratória.
- Removido o botão redundante **Atualizar aeronaves** da barra superior da janela principal. As consultas automáticas continuam e os botões de atualização das abas de monitoramento permanecem disponíveis.
- Nenhuma mudança de rede, intervalos, movimentação dos ícones ou preferências.


### Melhorias 0.3.29 — localização, botões e dependência da torre

- Geolocalização pode ser usada repetidamente: após um retorno válido do GeoClue ou uma localização por IP já autorizada, o botão reutiliza a última posição da sessão para recentralizar, sem abrir uma consulta extra. A precisão aproximada por IP é identificada como tal. No menu de localização da janela principal, **Atualizar localização do sistema** força nova verificação GeoClue.
- As câmeras do mapa principal e do mini-mapa fazem uma transição nativa de aproximadamente 750 ms até a localização, respeitando os limites de acesso ao serviço.
- O mapa principal possui controles compactos **+ / − / geolocalizar** no canto superior direito, semelhantes aos do mini-mapa, sem duplicar os botões nativos do Libshumate.
- Na aba Emergências, **Mostrar histórico** é um botão de ícone alternável, diretamente à direita de Atualizar. Seu estado pressionado indica histórico visível.
- Menu **Visualização**: Modo torre, logo abaixo Varredura giratória e em seguida Relógio. A opção de varredura fica insensível quando a torre está desligada, sem perder a preferência anterior. Também fica inativa nas Preferências enquanto a torre não está ligada.


## Novidades da versão 0.3.29 — PiP, fotografias e histórico de emergências

- **Mini-mapa mais fino:** a barra superior foi substituída por uma faixa compacta com arrasto nativo (`Gtk.WindowHandle`), menu, botão diagonal **Abrir janela principal** e fechar. Sem minimizar ou maximizar; as bordas continuam redimensionáveis. Em versões antigas do GTK4 há uma alternativa visual sem arrasto.
- **Geolocalização no PiP:** terceiro botão junto ao zoom para pedir localização GeoClue; quando desabilitada, a mesma opção de localização aproximada por IP do AeroScope exige consentimento. O mini-mapa se centraliza na resposta sem consultas ADS-B extras.
- **Acompanhar no PiP:** a câmera segue a posição *visual* do avião selecionado durante a transição. Mudanças programáticas de câmera não retornam ao radar como movimento manual, evitando requisições duplicadas.
- **Contexto de fotografia:** ao clicar com o botão direito num avião, se ainda não existe resultado em cache, o menu mostra **Buscando fotografia…** e inicia uma única consulta assíncrona. Se chegar miniatura, habilita **Ver fotografia** no mesmo menu; não faz consultas repetidas para fotos ausentes nem baixa a cada consulta ao vivo.
- **Sobreposição X11 vs. Wayland:** preferência `pip_always_on_top` continua ativada por padrão; no menu do PiP há checkbox só se a solicitação X11 for suportada. No Wayland é substituído por **Como ativar sobreposição** com orientações para GNOME (menu da janela) e KDE Plasma (Alt+F3/regras KWin). Não existe diálogo de permissão genérico no protocolo Wayland.
- **Histórico de emergências da sessão:** checkbox **Mostrar histórico desta sessão** na aba Emergências. Cartões cinza mostram quando o AeroScope viu o código pela primeira vez e quando deixou de recebê-lo. Erros ou respostas parciais não encerram alertas. Os dados são mantidos só na memória, durante a sessão; horários **não** são os instantes oficiais da emergência.
- **Sem serviços externos adicionais**, sem extensão GTK3, sem rotas fictícias e sem alteração dos intervalos de API.

## Histórico — 0.3.27: Mini-mapa compacto e ações contextuais

- **Barra superior anterior:** removidos subtítulo, botão de alternar maximização e botão de minimizar. A 0.3.29 traz um controle diagonal para voltar à janela principal. A janela continua redimensionável puxando as bordas; pelo menu é possível voltar à janela principal.
- **Sempre acima de outras janelas:** preferência `pip_always_on_top` ativada por padrão. No **X11** solicita o estado `_NET_WM_STATE_ABOVE` ao gerenciador (que pode recusar). No **Wayland** não há API GTK4 portátil para impor sobreposição: é necessário configurar a janela pelo gerenciador/compositor; o aplicativo não afirma que conseguiu se não houver suporte. Opção também em Preferências → Monitor → Janela e segundo plano.
- **Zoom e escala compactos:** substituídos os botões grandes do Libshumate por controles menores e criada régua de escala em uma única unidade, escolhida conforme a preferência existente (km, mi ou NM). Créditos cartográficos permanecem visíveis.
- **Clique simples na aeronave do mini-mapa:** seleciona e mantém o mini-mapa aberto. **Clique duplo:** seleciona e volta para o AeroScope completo.
- **Clique direito no avião (no mapa principal e no mini-mapa):** menu Acompanhar, Favoritar/Desfavoritar e Ver fotografia. A partir da 0.3.29, fotos ainda não consultadas são buscadas ao abrir o menu, em uma tarefa assíncrona. O mini-mapa utiliza os mesmos dados do radar, sem duplicar requisições.
- O recurso de sempre-acima é um pedido ao sistema, não um truque para contornar controles de segurança do Wayland.


## Histórico — 0.3.26: Bandeja, segundo plano e mini-mapa

- **Relógio mais legível no mapa claro:** o aro tem uma borda escura com destaque claro por cima; a escala horária continua centrada no avião selecionado, mesmo fora do modo Torre.
- **Menu hambúrguer dividido em quatro grupos separados:** Monitoramento, Visualização, Janela e Aplicativo. Em Janela ficam os comandos **Mostrar mini-mapa** e **Ocultar e continuar monitorando**.
- **Continuidade ao fechar:** ativada por padrão nas Preferências → Monitor → Janela e segundo plano. O botão X oculta a janela e mantém o processo Python com seu radar regional (intervalo configurado), favoritos, emergências globais e notificações. **Encerrar AeroScope** no menu fecha de verdade.
- **Ícone de bandeja com menu contextual:** via protocolo aberto StatusNotifierItem/DBusMenu, sem misturar GTK3 com o GTK4. Clique para abrir, menu para abrir, mini-mapa ou encerrar. KDE costuma aceitar diretamente; GNOME Shell pode exigir a extensão AppIndicator/StatusNotifier. **A presença do ícone não é garantida em todo desktop.** Se a bandeja não estiver disponível ao fechar, o app oferece uma confirmação antes de ficar oculto.
- **Mini-mapa opcional:** nova janela nativa GTK4/Libshumate com aeronaves já disponíveis no radar e sem chamadas extras à API. Há controles para **ampliar/reduzir** a janela e **voltar à janela principal**. Arrastar o mini-mapa muda a área de cobertura do radar regional. Em Preferências é possível escolher abrir o mini-mapa automaticamente ao clicar no X.
- **Limitação do PiP:** a janela é pequena, independente e redimensionável, mas GTK4 e Wayland não permitem garantir posicionamento em um canto nem permanecer sempre sobre outras janelas. O compositor pode oferecer uma opção manual de "manter acima".
- **Sem daemon extra:** o AeroScope permanece no mesmo processo e para de executar ao escolher Encerrar. O monitoramento e as notificações param quando o processo for encerrado ou a sessão do usuário terminar.

## Histórico — versão 0.3.25

- **Menu hambúrguer → Visualização:** três atalhos com estado (marcação): Modo torre, Relógio da aeronave e Varredura giratória. As escolhas ficam sincronizadas com a página Visualização das Preferências e são persistidas.
- **Relógio independente:** não depende mais de ativar a torre; aparece em volta do avião selecionado quando sua opção estiver ligada, mesmo no mapa normal. O raio é constante em pixels.
- **Retomar mapa:** salva latitude, longitude e zoom do mapa em `~/.config/aeroscope/last-map-view.json` ao fechar; restaura na abertura. Isso registra a área visualizada, não é consulta de localização por IP nem armazenamento de GPS. Um mapa previamente salvo não será sobrescrito automaticamente pela tentativa de localização na abertura.
- **Emergências nos marcadores:** cruza a resposta mundial de códigos 7500/7600/7700 com os aviões regionais por **ICAO24 exato**; atualiza imediatamente o símbolo do mapa, a lista de visíveis e os detalhes. Não atribui a emergência de um avião a outro. Resultados mundiais expiram para evitar marcadores permanentemente em alerta.



## Alterações da versão 0.3.24 — relógio e varredura corrigidos

- **Relógio preso ao avião, com tamanho fixo:** raio nominal de 168 pixels no modo Torre, independentemente de zoom, movimento do mapa ou aproximação da aeronave às bordas. Se necessário, o relógio fica parcialmente fora da tela; não encolhe para caber. Apenas o redimensionamento da janela para dimensões pequenas reduz o tamanho.
- **Distâncias diretamente nos círculos:** remoção das linhas radiais que atravessavam as legendas. Etiquetas ficam nas circunferências visíveis; se o círculo não tiver ponto de rótulo visível, sua etiqueta é omitida em vez de ser deslocada para o lugar errado.
- **Desligar varredura retoma o radar sem nova consulta:** o destino confirmado e a linha temporal interna de cada avião são reaproveitados imediatamente pela animação normal. Isso vale tanto para aviões aguardando passagem do feixe quanto para os já liberados pela varredura. Não há novo pedido ao ADSB.lol.

## Melhorias da versão 0.3.23 — escala horária e correções da torre

- **Escala de horas relativa ao avião selecionado:** no modo Torre, a escala `12/0` até `11` é desenhada em torno da **posição visível** da aeronave selecionada; `12/0` fica alinhado ao nariz do avião (seu rumo mostrado na tela), e `2` corresponde a **60° à direita** desse rumo. A escala desaparece ao desselecionar ou sair do modo Torre. Não é uma indicação absoluta de rumo Norte e não substitui navegação aeronáutica.
- **Radares realmente cobrindo o mapa inteiro:** raio de círculos e do feixe giratório calculado até a quina mais distante do retângulo visível, mesmo em janela panorâmica. A linha varre os quatro cantos.
- **Posições apenas quando a varredura passa:** os novos pontos recebidos ficam em memória; a movimentação entre duas posições realmente recebidas é calculada internamente, e o feixe libera a posição interpolada naquele instante com uma transição visual de ~0,38 s (ou imediata se a animação estiver desativada). O símbolo fica parado entre passagens. Não existe extrapolação além da última posição observada. Uma animação pré-existente é congelada ao habilitar a varredura. **Sem consultas extras à API.**
- **Aros sempre com legendas:** distâncias calculadas diretamente pela escala Web Mercator para zoom e latitude, sem depender de conversões GTK não inicializadas. A posição das legendas busca um ponto visível de cada arco, inclusive em janelas largas. Unidade conforme a configuração existente (km, NM ou mi).
- **Botão de localizar emergências com margem interna:** corrigido no próprio botão do cartão, não apenas no contêiner externo.

## Melhorias da versão 0.3.22

- Monitoramento global de emergências habilitado para instalações novas; notificações ativadas e som desligado por padrão. Configurações já salvas continuam respeitadas.
- Aba Emergências recebe marcação vermelha e um ponto visível quando a última consulta detectou algum código 7500, 7600 ou 7700.
- Varredura de torre opcional nas Preferências → Mapas; o mapa normal mantém a animação contínua.

## Melhorias anteriores — 0.3.21: Monitores durante o aquecimento

- **Favoritos sem atraso:** ao favoritar uma aeronave já detectada pelo radar de 250 NM, a aba de Favoritos e sua contagem são atualizadas imediatamente, sem exigir nova consulta global. Os resultados recentes do radar continuam atualizando seu estado enquanto estiver na área. Sair do raio **não** significa que o avião aterrissou ou ficou offline.
- **Emergências desde a abertura:** a primeira consulta aos códigos 7500, 7600 e 7700 começa automaticamente durante o splash, sem precisar abrir a aba nem ativar o monitoramento periódico. Mesmo com o splash desabilitado, a verificação inicial ocorre. As próximas consultas automáticas globais continuam dependendo da preferência **Monitorar emergências** ou de abrir a aba.
- **Consultas escalonadas:** a verificação de emergência ocorre primeiro; favoritos ainda não cobertos pelo radar são consultados depois, para diminuir rajadas de requisições. Ambas são assíncronas, com proteção contra HTTP 429. O splash desaparece após as três leituras do radar, não aguarda os monitores.
- A primeira leitura dos monitores estabelece uma referência, sem notificação ou alarme de emergência antiga. Em caso de erro, a aba informa que a verificação está incompleta; não mostra zero indevidamente.

## Melhorias anteriores — 0.3.20 (câmera) e 0.3.19 (lateral)

- Ao selecionar outra aeronave, o mapa se desloca com animação nativa Libshumate em cerca de 400 a 800 ms, preservando o zoom.
- Cliques rápidos interrompem a animação anterior; o acompanhamento automático não compete com a transição.
- O botão **Centralizar** nos detalhes também usa a animação.
- A cobertura em cache de 250 NM e os limites de requisição continuam valendo; a animação da câmera não aumenta a frequência de consulta.

- Contagens diretamente nas abas **Visíveis (N)**, **Favoritos (N)** e **Emergências (N)**, atualizadas após cada resposta. Visíveis reflete a tela do mapa; Favoritos conta apenas aeronaves distintas com sinais compatíveis com voo; Emergências conta aeronaves detectadas globalmente com códigos 7500, 7600 ou 7700.
- Antes da primeira consulta, **Favoritos (—)** e **Emergências (—)** deixam claro que não foi possível verificar a contagem. Se não houver favoritos cadastrados, aparece **Favoritos (0)**.
- Retirados o título duplicado **Aeronaves visíveis**, o título **Minhas aeronaves** e o texto **Monitor global de matrículas**. O botão **+** para cadastrar favoritos permanece no início da aba, junto do comando atualizar.
- Botão de remover favorito ganhou margem interna à direita, evitando que a lixeira encoste na borda do cartão.
- As contagens são indicativas do último retorno da API e nunca significam confirmação operacional de decolagem, pouso ou chamadas MAYDAY.

## Histórico — versão 0.3.18

- Três abas nativas na lateral: **Visíveis**, **Favoritos**, **Emergências**, sem janelas de monitor separadas.
- **Favoritos:** botão `+` na aba para adicionar matrícula ou ICAO24; estrela amarela nos aviões favoritados na lista e no mapa, sem misturá-la à seleção.
- Monitoramento de matrículas favoritas de qualquer região, com intervalo independente de **1, 2, 5, 10 ou 15 minutos** (padrão: 2 minutos). Cada matrícula acarreta uma consulta própria à API pública.
- **Notificação nativa** quando uma aeronave favorita reaparece em condições compatíveis com voo, depois de duas consultas sem sinal ou depois de indicação explícita de solo. A primeira verificação é só uma referência inicial. Isso **não confirma decolagem**: velocidade e altitude são usadas apenas como indícios de voo.
- **Emergências mundiais:** códigos de transponder 7700, 7600 e 7500; intervalo independente de **1, 2, 5, 10 ou 15 minutos**. Existe **uma consulta inicial durante o aquecimento**; o monitoramento periódico mundial é **ativado por padrão desde a 0.3.25**, mas pode ser desligado nas Preferências.
- Notificação para **novos** códigos de emergência, com **alarme sonoro opcional** (desativado por padrão), emitido uma vez por lote. O som usa o tema de eventos via `canberra-gtk-play`, quando disponível, ou um aviso sonoro do ambiente gráfico. O volume, o modo silencioso e a opção Não Perturbe variam conforme o desktop; nenhum som é garantido.
- Nova página **Monitor** nas Preferências com controles independentes de atualização, notificações e áudio. As consultas continuam com o AeroScope em segundo plano, caso a opção de residência esteja ativada; o encerramento definitivo interrompe os monitores.
- A primeira consulta de emergência estabelece uma referência sem gerar uma enxurrada de notificações; resultados repetidos, perdas breves da rede e falhas temporárias não devem disparar alertas repetidos. Erros HTTP 429 continuam acionando recuo automático.

Aplicativo de radar aéreo para Linux, escrito em Python, GTK4, Libadwaita e Libshumate. **Sem PHP, servidor próprio, banco de dados, cadastro ou chave de API.**


## Implementação anterior — Monitor de aeronaves (0.3.17)

- **Monitor de favoritas** no menu hambúrguer e estrela no painel do avião. Cadastre até 12 matrículas (ex.: PT-MUJ) ou endereços ICAO24. A lista é persistida em `~/.config/aeroscope/favorites.json`, separada das preferências e dos rastros. As coordenadas e trajetórias continuam apenas em memória.
- **Estado correto de rastreamento**: “Rastreado agora”, “Detectado, sem posição recente”, “Sem sinal recente” e “Não foi possível verificar”. **Sem sinal recente não implica que a aeronave está em terra**.
- **Consulta fora da região do mapa**: endpoints globais `GET /v2/reg/{registration}` e `GET /v2/icao/{hex}` do ADSB.lol. A janela tem atualização manual e consulta automática a cada **2 minutos enquanto visível**; há espera após HTTP 429. Clicar no localizador de um favorito com posição centraliza o radar na aeronave.
- **Emergências globais**: aba separada consultando `GET /v2/squawk/7700`, `/7600` e `/7500`, sem varrer o planeta por círculos. Resultados são distinguidos por códigos e apresentam botão para localizar aeronaves com GPS disponível.
- **Critério aeronáutico**: 7700 = emergência geral, 7600 = falha de rádio, 7500 = interferência ilícita. **Não afirmar que houve chamada vocal MAYDAY**. Se um código não responder, a consulta é marcada como incompleta. Os resultados são tão atuais quanto a última resposta; veja o horário na tela.
- **Controle de requisições**: o monitor é opcional, só consulta enquanto a janela ou o modo residente estão ativos; consultas manuais têm intervalo mínimo e o backoff de HTTP 429 interrompe consultas adicionais. Não é um serviço de alerta em segundo plano.

### Versão anterior — 0.3.16

- **Busca global por indicativo:** reconhece callsigns longos, como `ARCANJO9` (antes confundido com nome de cidade).
- **Busca histórica sob demanda:** ao confirmar uma pesquisa, consulta o ADSB.aero por callsign, matrícula ou ICAO24. O autocomplete não consulta o arquivo a cada tecla.
- Históricos aparecem em categoria separada com data UTC e podem abrir o player mesmo que o avião não esteja sendo rastreado no momento.
- A busca inicial limita páginas e período, e pode não encontrar registros fora da cobertura.

## Histórico de alterações — versão 0.3.15

- **Replay de voos históricos:** ao escolher um registro do ADSB.aero, o AeroScope abre um player contextual sobre o mapa, com reprodução, pausa, barra de progresso e velocidades **1×, 2×, 4× e 8×**. O tempo do replay corresponde aos timestamps UTC do arquivo, sem gerar posições em áreas sem cobertura. Nos intervalos sem sinal, o marcador permanece na última posição observada, e o rastro não liga segmentos separados.
- **Visual diferente no histórico:** avião histórico em violeta identificado como `REPLAY`, rastro progressivo violeta pontilhado e opção **Ocultar aviões ao vivo**. Ao fechar o reprodutor, os aviões ao vivo reaparecem e o radar retoma suas consultas.
- **Origem e destino:** parser de rotas mais tolerante aos formatos retornados pelo ADSB.lol (lista, resposta codificada como string, resultado com códigos), fallback geográfico apenas para aeroportos com coordenadas conhecidas, indicação quando há somente os códigos e opção manual de tentar novamente. Logs de consultas disponíveis com `aeroscope --debug`. **Não é garantido que a API possua uma associação para cada callsign.**
- **Mais espaço na barra lateral:** os rótulos de cobertura e coordenadas deixam de ocupar linhas abaixo da busca. O status e o centro consultado aparecem no subtítulo da janela.
- **Localização por IP:** o aviso de compartilhamento do IP é exibido somente na primeira autorização. A permissão é guardada nas Preferências e pode ser revogada; o AeroScope continua sem consultar o IP automaticamente sem o pedido do usuário ou autorização específica.
- A reprodução depende dos timestamps reais fornecidos pelo ADSB.aero e é indisponível quando um registro não tem a série de horários necessária. Os arquivos históricos não são gravados em disco.

### Testar a nova versão

```bash
sudo apt install ./aeroscope_0.3.27_all.deb
aeroscope --debug
```

Selecione uma aeronave, escolha um voo na seção **Histórico ADSB.aero** e use o player exibido no mapa. Para origem/destino sem resultado, verifique no terminal as linhas `aeroscope.routes`; elas diferenciam ausência de rota de erro HTTP ou rede. Não utilizamos endpoints de histórico para inferir artificialmente a rota atual.

### Limitações de teste

Os testes executados sem interface cobrem o parser de trajetórias, timestamps, lacunas de cobertura, busca de origem/destino, configuração de localização e empacotamento. O ambiente de criação não tem PyGObject/Libadwaita instalados e a interface precisa ser validada numa sessão gráfica real antes de publicar uma release estável.

## Novidades da versão 0.3.12

- Origem e destino prováveis para voos reconhecidos pelo ADSB.lol (`routeset`), consultados sob demanda ao selecionar uma aeronave.
- Linha geográfica ortodrômica estimada e opcional, em âmbar tracejado, sem confundir com os rastros reais da sessão ou do ADSB.aero.
- Botão **Ver rota completa** com enquadramento automático de origem, destino e aeronave, e **Voltar ao radar ao vivo**.
- Cache em memória por aeronave e callsign, tratamento de consultas sem resultado e limites HTTP 429.
- A rota desenhada **não** representa os waypoints do voo nem confirma a origem/destino efetivamente utilizados.

### Melhorias anteriores — 0.3.11

- **Mapa em tela cheia até a borda inferior**: o status fica no subtítulo da barra de título do Libadwaita, sem barra inferior ocupando o mapa.
- **Apoiar provedores de mapas**: link de doação opcional no menu hambúrguer (sem remover as atribuições exigidas pelos tiles).
- **Autocomplete corrigido**: resultados de aeronaves, aeroportos e cidades são exibidos dentro da barra lateral, sem `Gtk.Popover` em uma superfície independente do gerenciador de janelas. Isso evita que as sugestões permaneçam visíveis por cima de outros aplicativos.
- Após selecionar resultado, pressionar Esc, clicar no mapa ou trocar de aplicativo, sugestões fecham e não reabrem por uma resposta de geocodificação atrasada; volte a digitar para obter resultados novos.
- **Não houve alteração** nos intervalos de consulta ao ADSB.lol, no splash, nas fotos, nas trajetórias ou no armazenamento de dados.

### Verificação

Os testes automatizados de código são executáveis com `python3 -m unittest discover -s tests`.
A interface GTK deve ser testada numa sessão gráfica real; o ambiente de construção não oferece bibliotecas GTK4/Libadwaita para executar a janela.

## Instalar no Ubuntu / Debian

```bash
sudo apt install ./aeroscope_0.3.27_all.deb
```

A instalação substitui o pacote anterior `aeroscope-gtk` (quando instalado pelo APT). O executável **agora é apenas `aeroscope`** e o menu do GNOME mostra **AeroScope**. Teste com posições simuladas:

```bash
aeroscope --demo
```

## Funcionalidades

- **Radar ao vivo:** ADSB.lol, atualização configurável de 10 a 120 segundos (padrão/mínimo: 10 s); três consultas iniciais de aquecimento: imediata, 2,5 s depois da resposta e 5 s após a segunda resposta, somente se o serviço permitir; animação visual entre posições confirmadas com duração adaptada ao intervalo e à média das últimas cinco respostas HTTP. Sem extrapolar coordenadas, sem atraso de buffer e sem novas consultas para animar. Cada busca regional usa **uma consulta com raio fixo de 250 milhas náuticas**. O centro de consulta é mantido ao movimentar o mapa; novas buscas só ocorrem quando a área visível ultrapassa a cobertura existente, com limite mínimo entre requisições, tolerância a HTTP 429 e aviso de cobertura parcial em zoom afastado. Atualização manual disponível.
- **Localização:** GeoClue respeita as permissões do GNOME. Quando desativado, o aplicativo não tenta contornar essa escolha automaticamente. O menu de localização e Preferências → Radar oferecem **localização aproximada por IP**, com autorização explícita lembrada até a revogação, via ipwho.is por HTTPS, sem chave e sem gravar o IP ou a posição. Não é GPS; VPN/provedor podem deslocar a cidade. Sem consentimento, permanece o centro do mapa selecionado ou o padrão em Divinópolis/MG.
- **Aeroportos:** catálogo local limitado, marcadores clicáveis e tooltips; pesquisa por códigos IATA/ICAO; cidades via Open-Meteo. Em detalhes do aeroporto, **Consultar chegadas e partidas** abre a página pública correspondente do Flightradar24 no navegador interno, quando WebKitGTK 6 está instalado, ou no navegador padrão. Nenhuma API de horários ou dados de movimentos é coletada pelo AeroScope.
- **Lista e mapa:** a lista encolhe ao selecionar uma aeronave ou aeroporto; passar o ponteiro pela aeronave na lista realça temporariamente seu marcador. Aviões usam contorno e sombra discretos. A orientação usa rumo entre duas posições consecutivas plausíveis, e o `track` da API quando não houver dados suficientes.
- **Trajetória arquivada:** ao exibir uma rota histórica, o mapa ajusta automaticamente centro e zoom para incluir seus segmentos, mantendo as lacunas desconectadas. A consulta ao vivo não dispara no meio do enquadramento.
- **Sobrevoar o avião:** tooltip do GNOME com voo, matrícula, altitude, rumo e velocidade. Clique abre os detalhes na lateral.
- **Fotografias:** consulta opcional sob demanda ao Planespotters.net por ICAO24, seguida de tentativa por matrícula; valida os domínios CDN autorizados (inclusive `cdn.plnspttrs.net`), informa quando não existe foto ou ocorre falha, e permite tentar novamente. A miniatura fica apenas em RAM, com crédito e link para a página original. A imagem é clicável e abre uma prévia maior, sem baixar o original; o componente GTK decodificado é reaproveitado durante atualizações. A galeria oficial por matrícula pode ser aberta no WebKitGTK; o código não copia fotografias da galeria. WebKitGTK 6.0 (se disponível) abre a página dentro do aplicativo; caso contrário utiliza o navegador padrão.
- **Origem/destino provável:** consulta sob demanda ao endpoint `routeset` do ADSB.lol. Exibe os aeroportos associados e, opcionalmente, uma linha geográfica estimada (não é plano de voo real).
- **Histórico ADSB.aero:** ao selecionar um avião, busca até oito registros arquivados na janela mais recente de até 7 dias do arquivo; clique em um registro abre um reprodutor por timestamps com rastro violeta pontilhado e controle de velocidade. Lacunas entre segmentos não são ligadas. Isso não garante o histórico do voo atual.
- **Movimento suave opcional:** em Preferências → Radar, a opção “Animar movimentação das aeronaves” fica ativada por padrão e pode ser desligada a qualquer momento. A animação linear considera o intervalo até a próxima consulta somado ao tempo médio recente de resposta da API, com pequena margem de segurança (sem extrapolar além da última posição recebida). O primeiro par de posições é necessário para animar. As posições recebidas continuam sendo os únicos pontos registrados no rastro. Se um salto for grande, uma posição estiver velha, ou for a primeira leitura, o ícone é reposicionado diretamente. O movimento é apenas uma transição visual, não a posição em tempo real durante a animação.
- **Rastro da sessão:** registra até 45 posições de cada aeronave durante o uso, sem salvar em disco. Traçado verde-azulado separado do histórico arquivado. Limpa-se nas Preferências.
- **Mapas:** OpenStreetMap padrão; OpenTopoMap-R e OpenHikingMap de openmaps.fr. Todos sem chave de API. Os tiles são obtidos por libshumate conforme necessidade, sem pré-carregar áreas inteiras.
- **Modo torre de controle:** grade radial e filtro visual opcionais, **apenas estéticos**; os círculos não são escalas de distância aeronáutica.
- **Visual GNOME:** menu hambúrguer com Preferências, Sobre e Sair; janela de Preferências com navegação por ícones na parte inferior, tema Automático/Claro/Escuro, mapas, radar, unidades e memória; Sobre nativo com créditos e link do projeto.
- **Velocidade:** km/h, nós ou mph como unidade principal, com as três no painel de detalhes.

## Cache / privacidade

Preferências em `~/.config/aeroscope/settings.json`. O aplicativo mantém o rastro e os registros históricos carregados em RAM (não persistem após fechar). O Libshumate administra o cache de tiles próprio conforme os provedores. Para não apagar informações usadas por outras aplicações GNOME, o botão "Limpar cache" **não apaga o cache compartilhado de mapas**; ele limpa arquivos temporários próprios do AeroScope e os metadados de fotos/históricos em RAM. A opção "Limpar rastros" limpa as coordenadas da sessão.

## Mapas e licenças

- OpenStreetMap: https://operations.osmfoundation.org/policies/tiles/ — atribuição obrigatória, User-Agent identificável, cache e **sem pré-busca massiva**. Tiles públicos são best-effort e não dão garantia de disponibilidade.
- OpenTopoMap-R e OpenHikingMap: https://openmaps.fr/tile-usage-policy.html — uso não comercial razoável, sem chave; cotas compartilhadas e atribuição ao provedor, autores do estilo e OSM. Consulte os termos antes de distribuir amplamente.
- **Não inclui satélite:** não foi selecionado um provedor de imagens por satélite com licença, quota e acesso anônimo adequados para distribuição aberta. Não substituímos isso por serviços fechados sem autorização.

## Serviços de aeronaves

- ADSB.lol: https://api.adsb.lol/docs — licença ODbL e serviço comunitário. Respeitar limites e termos para produção/distribuição.
- ADSB.aero: https://adsb.aero/llms.txt — gratuito, não exige autenticação; consultar apenas ao selecionar, sem polling de histórico. Pode haver lacunas, não confundir arquivo com voo atual.
- Planespotters.net: https://www.planespotters.net/ — imagens de seus autores, créditos e link visíveis, não re-hospedar ou salvar fotos em disco.
- Geocodificação de cidades: https://open-meteo.com/en/docs/geocoding-api .

**Nunca utilize o AeroScope como ferramenta para navegação, controle aéreo ou segurança operacional.**

## Desenvolvimento

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-shumate-1.0 gir1.2-geoclue-2.0 geoclue-2.0
./run.sh --demo
python3 -m unittest discover -s tests -v
```

Para navegador interno opcional, instale `gir1.2-webkit-6.0` caso disponível no Ubuntu.

Repositório futuro: https://github.com/ehstbr/Aeroscope

Licença do código próprio: MIT (`LICENSE`). Licenças das APIs, dados, fotografias e tiles são **independentes** da licença MIT do código.

**Limitação da validação:** testes de sintaxe, lógica, instalação e estrutura foram executados, mas a janela GTK/Libadwaita não pôde ser aberta neste ambiente sem bibliotecas GI/sessão GNOME. Teste real em Ubuntu ainda é necessário.

**Fora do escopo:** malha de aerovias, waypoints e geração de rotas aeronáuticas. Nada foi adicionado como preparação para isso.

## Localização alternativa sem GeoClue (0.3.9)

O usuário pode clicar no ícone de localização do cabeçalho e escolher **Localização aproximada por IP**, ou usar Preferências → Radar → Localização → Localizar agora. Um diálogo de confirmação explica que o endereço IP público será visto pelo provedor externo `https://ipwho.is/`. A consulta ocorre somente após confirmação. Quando o serviço do sistema falha ou está desativado, o AeroScope pode sugerir a alternativa, mas jamais consulta o IP automaticamente; a resposta geográfica é usada para centralizar o mapa e desenhar o marcador **aproximado**. O aplicativo não guarda o IP nem a localização em disco e não envia IP a outros serviços de geolocalização. A API gratuita é destinada ao uso não comercial e pode ter limites; consulte https://ipwhois.io/documentation. Em caso de erro, a região anterior é preservada. Use a busca de cidades para escolher manualmente uma área, se necessário.

## Consulta externa de voos por aeroporto

As páginas públicas do Flightradar24 (por ex. `https://www.flightradar24.com/data/airports/gru`) são um serviço **terceiro**. A disponibilidade, anúncios, cookies, páginas que requerem login e restrições de acesso são definidos pelo site. O AeroScope não reproduz nem extrai os dados e não garante que todos os aeroportos tenham painel de movimentos. O visualizador WebKitGTK não contorna restrições do provedor.

## Aparência e atualizações na versão 0.3.8

- **Perspectiva sutil por altitude:** silhuetas no solo têm 90% do tamanho de referência; em cruzeiro podem chegar a 108%. É um recurso gráfico, não representação física exata de distâncias ou envergaduras. Pode ser desativado em Preferências → Radar.
- **Hover vs. seleção:** ao passar o cursor pela lista, a aeronave ganha um realce translúcido na forma da silhueta; somente a aeronave selecionada recebe um anel.
- **Animação longa:** a aeronave desliza linearmente até o ponto confirmado recebido pela API durante aproximadamente o intervalo da próxima consulta mais a média recente de latência da API. A posição exibida pode estar atrasada em relação à posição real; o app não extrapola para o futuro.
- **Partida progressiva controlada:** após carregar o mapa, as duas próximas consultas usam 2,5 s e 5 s entre respostas, mesmo com intervalo normal de 10 s, depois passam à cadência configurada. HTTP 429 suspende as consultas pelo período apropriado; intervalos mínimos se aplicam também à atualização manual. Não há promessa de dados em tempo real absoluto.

## Preparação ao iniciar (0.3.8)

- Novo diálogo nativo **Preparando o radar**, ativado por padrão em Preferências → Radar. O aplicativo inteiro fica visível, escurecido ao fundo, enquanto as três primeiras leituras são concluídas.
- Primeira consulta logo após abrir; segunda 2,5 segundos depois da conclusão da primeira; terceira 5 segundos após a segunda. A tela desaparece ao concluir a terceira resposta válida. Pode ser dispensada a qualquer momento por **Ver o mapa agora** ou Esc, sem interromper as consultas.
- Depois, a cadência normal segue a escolha do usuário: 10, 15, 20, 30, 45, 60 ou 120 segundos. O mínimo normal é **10 segundos**.
- **Aquecimento é experimental e mais intensivo:** não há garantia de posições novas a cada consulta; o provedor pode rejeitar o tráfego. Ao receber HTTP 429, respeita `Retry-After` e cancela o aquecimento. Erro de conexão também encerra a preparação e evita tentativas rápidas. Por segurança, o diálogo desaparece após 22 s se uma resposta atrasar.
- A animação continua apenas **entre coordenadas já confirmadas**; não representa a posição real em cada instante. O intervalo curto pode consumir cotas rapidamente. Para uso frequente, escolha 30 s ou mais.
- GNOME com Libadwaita anterior a 1.5 não apresenta o diálogo opcional, mas continua funcionando.


## Diagnóstico de fotografias — versão 0.3.8

Abra o AeroScope **pelo terminal** com:

```bash
aeroscope --debug
```

Clique em uma aeronave real, aguarde a resposta e procure linhas com `aeroscope.photos`:

- `Iniciando pesquisa` e `Consultando ... ICAO24`: solicitação de metadados ao Planespotters.
- `HTTP 200`, `HTTP 403`, `HTTP 429` etc.: resposta do serviço para cada tentativa.
- `Nenhuma miniatura compatível`: nenhuma imagem fornecida, ou URL não reconhecida; se houver matrícula, será consultada também.
- `Baixando miniatura` e `Miniatura: HTTP ...`: consulta à CDN de imagens, tipo do arquivo e tamanho.
- `Imagem ... decodificada uma vez`: decodificação e montagem do componente GTK concluídas.
- `Falha ao renderizar`: erro de decodificação ou integração com GTK (traceback no terminal).

O AeroScope também mostra logs essenciais em `aeroscope` sem `--debug`; o parâmetro ativa mensagens extras, como os domínios rejeitados.

Os dados recebidos da API são usados somente em memória e o aplicativo não guarda fotografias em disco. Nem toda matrícula ou transponder tem foto cadastrada. Por respeito aos autores, exibimos apenas miniaturas com créditos e link para a imagem na página original.

A integração com o serviço externo precisa ser validada em um computador conectado à internet: neste ambiente de compilação não foi possível realizar requisições externas ao Planespotters.net.


### Novidades da 0.3.8
- Clique em área vazia do mapa desmarca avião ou aeroporto selecionado, mas arrastar o mapa ou clicar em marcador/controle não desmarca.
- Miniaturas Planespotters decodificadas uma só vez na sessão e widget GTK reaproveitado a cada atualização; sem downloads repetidos.
- Clique na miniatura para ampliar em janela GNOME com crédito; galeria oficial por matrícula no navegador interno quando existir.
- Ícone externo discreto nos detalhes para abrir a página original da fotografia no navegador interno.
- Para salvar e reutilizar fotos, respeitar as condições do Planespotters: apenas miniaturas públicas, crédito e link à página do fotógrafo; a galeria oficial é aberta no site, não reproduzida por scraping.

## Movimento adaptativo ao tempo de resposta (0.3.8)

- Após cada consulta bem-sucedida, o AeroScope mede o tempo total da requisição e guarda até cinco medições. Um pico muito elevado é limitado para não causar deslocamentos exageradamente lentos.
- A duração da transição usa **tempo configurado até a próxima consulta + latência média recente - margem discreta**. Isso reduz as pausas entre o fim de uma animação e a próxima resposta, sobretudo quando a API demora 1–2 segundos.
- A medida não provoca requisições extras; no aquecimento permanece a sequência 0 s, +2,5 s e +5 s; depois aplica-se a cadência escolhida (mínimo 10 s).
- Se a API não trouxer uma nova coordenada, a aeronave fica corretamente no último ponto conhecido; não são inventadas posições futuras. Uma variação excepcional na latência ainda pode causar uma pequena pausa.
- Use `aeroscope --debug` para ver `aeroscope.motion` (latência observada, média e duração calculada).


## Localização portátil — 0.3.11

- A interface usa GTK4/Libadwaita em qualquer ambiente gráfico Linux compatível (GNOME, KDE Plasma, XFCE, LXQt etc.), não apenas Ubuntu/GNOME. O serviço GeoClue é baseado em freedesktop.org e sua utilização é opcional.
- Em desktops GNOME, se o esquema de preferências existir e a localização estiver explicitamente desligada, o AeroScope não inicia a solicitação ao GeoClue. Em outros ambientes, tenta o GeoClue quando estiver instalado, sem pressupor configurações do GNOME.
- Se o GeoClue estiver indisponível, recusado, falhar ou não responder em até 18 segundos, oferece **uma vez por sessão** a opção **Localizar por IP**, com esclarecimento de que o serviço externo receberá o IP público. Não há geolocalização por IP automática.
- No diálogo, **Agora não** dispensa a oferta na sessão; **Não sugerir novamente** desativa as ofertas futuras, mas a localização manual continua disponível. Pode reativar em **Preferências → Radar → Localização**.
- A localização manual por cidade ou aeroporto permanece disponível sem depender de GeoClue/IP. O modo de demonstração não faz localização automática.
- A localização IP não deve ser entendida como GPS; pode indicar o endereço do ISP ou da VPN. Nenhum IP nem coordenadas de localização são persistidos pelo aplicativo.
- Pacotes GeoClue agora são recomendações do `.deb`, não dependências obrigatórias; sem eles o mapa e o radar continuam funcionando.

Não existe autoatualização nesta versão.

## Novidades da versão 0.3.12 — Origem, destino e rota geográfica estimada

- **ADSB.lol**: ao selecionar uma aeronave real com `callsign`, o AeroScope consulta o endpoint oficial `POST /api/0/routeset` com o identificador e sua posição atual. A requisição só ocorre quando necessária, nunca a cada atualização dos aviões. O serviço pode não reconhecer alguns callsigns.
- **Origem e destino prováveis** no painel lateral, com IATA/ICAO, nome e distância geográfica entre os aeroportos (não é distância restante do voo).
- **Mostrar rota estimada**: desenha uma referência geográfica ortodrômica entre os aeroportos, em **âmbar tracejado**, separada do **rastro observado desta sessão (azul/verde conforme o estilo)** e do **histórico ADSB.aero (azul)**. Os pontos interpolados são exclusivamente geográficos, não waypoints de plano de voo ou posições registradas.
- **Ver rota completa**: enquadra aeroporto de origem, aeroporto de destino e posição atual, com margem. As atualizações do radar ficam pausadas enquanto você examina a rota completa; **Voltar ao radar ao vivo** restaura centro e zoom anteriores e retoma a consulta normal.
- **Confiabilidade**: os dados por callsign são associações de base de dados, não uma confirmação oficial do plano de voo. Se o provedor retornar `plausible=false`, a interface indica a incerteza. Se não houver dados, não inventa rota nem aeroportos.
- **Uso responsável**: cache em memória por ICAO24 + callsign durante 30 minutos para associações existentes e 2 minutos para consultas sem resultado/falha. Respeita HTTP 429, com pausa separada para a busca de rotas. Nenhum dado pessoal ou histórico de posições é salvo por essa função.
- **Sem nova dependência**: a visualização continua nativa com Libshumate, sem WebKit, API key ou biblioteca de rotas adicional.

A visualização da rota estimada não deve ser utilizada para navegação aérea, operação, controle de tráfego ou decisões de segurança. É uma referência visual recreativa.


### 0.3.14 — player histórico e telemetria

- Replay centraliza o primeiro ponto do avião; o botão de enquadramento mostra a trajetória completa, e o de localização recentraliza o avião a qualquer momento.
- Marcador do histórico usa a mesma silhueta da categoria da aeronave em violeta, girada pelo rumo entre posições consecutivas do mesmo segmento. Sem placa quadrada.
- Player com voo/matrícula, modelo, origem/destino arquivados quando fornecidos, relógio UTC, velocidade 1–8×, saltos de 30 segundos e opção de ocultar aviões ao vivo.
- Painel de gráfico recolhível, com as linhas de altitude (pés) e velocidade sobre o solo (nós) independentes, eixos por hora UTC, tempo decorrido ou distância observada, e cursor vertical sincronizado. Clique no gráfico para avançar para o ponto correspondente.
- A série de velocidade só é desenhada se `path_gs` estiver presente no ADSB.aero; dados não transmitidos permanecem indisponíveis. Lacunas do arquivo histórico não são conectadas artificialmente.
- As linhas do gráfico mostram toda a história disponível, enquanto o marcador e o rastro animado progridem conforme o relógio.
- Sem dependências adicionais: gráfico GTK4 DrawingArea/Cairo.

### 0.3.65 — Fades dos widgets flutuantes

- Ao adicionar uma aeronave, aeroporto ou estação ao painel, o cartão aparece com fade suave de 150 ms.
- Ao fechar o cartão pelo X ou menu de contexto, ele desaparece com fade de 130 ms antes de ser removido do Gtk.Overlay.
- A escolha de respeitar a preferência GTK para animações evita efeitos indesejados em acessibilidade.
- As posições e tamanhos não mudam durante o fade; recolher/expandir continua com o Gtk.Revealer de 220 ms.
- Widgets restaurados na inicialização aparecem diretamente, sem animação simultânea de vários cartões.


## Navigation shortcuts (0.3.65)

The map supports `+`/`−` (including numpad) to zoom, `.` or `L` for GeoClue
location, `F` or `Ctrl+F` to focus the search, `T` for Control Tower, `S`
for its sweep, `M` for METAR, `A` for SIGMET advisories, `P` for the mini-map,
`B` for bookmarks/favorites, `V` for visible aircraft and `E` for emergencies.
`F11` toggles the full-screen dashboard, `Esc` exits it, and `?` or `F1` opens
the Keyboard Shortcuts window from the application menu. Single-letter and
symbol bindings do not intercept text entry. Shortcuts follow English action
names regardless of the interface translation.

The airport and METAR-station floating cards now have the same compact
center-on-map control as aircraft cards. Left-clicking either map marker
opens its details and smoothly centers the main map. A distinct selection
outline appears without changing the METAR VFR/IFR color.
