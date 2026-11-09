# Contribuindo com o AeroScope / Contributing to AeroScope

Obrigado pelo interesse! O AeroScope é um aplicativo Linux em Python, GTK4/Libadwaita e Libshumate. Contribuições em código, tradução, documentação, testes e relatos de erros são bem-vindas.

## Antes de começar

1. Consulte o [README](README.md) e o [histórico](CHANGELOG.md) para conferir a versão e o comportamento esperado.
2. Em caso de erro, procure relatos existentes em **Issues**. Para um recurso novo, descreva a necessidade e como o usuário deve interagir com ele.
3. Mantenha a experiência GTK nativa e leve, com acessibilidade, tradução e boa resposta em máquinas modestas.
4. Evite novas dependências, chaves de API, coleta massiva de tiles ou chamadas agressivas aos serviços públicos sem uma justificativa técnica.

## Preparando o ambiente

```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-shumate-1.0
python3 -m pip install pytest
./run.sh
```

```bash
python3 -m pytest -q
```

Os testes automatizados não substituem testes visuais em uma sessão Linux com GTK4. Sempre que possível, verifique uso de mouse, teclado, foco, telas pequenas e preferências persistentes.

## Estrutura de um Pull Request

- Explique a mudança e o problema que ela resolve.
- Indique como reproduzir/testar e, para mudanças visuais, anexe capturas de tela.
- Inclua ou atualize testes quando houver lógica testável.
- Atualize o README, as traduções ou a documentação pertinente se o comportamento público mudar.
- Não altere números de versão ou históricos antigos sem uma razão definida na revisão.
- Evite incluir dados privados, tokens, históricos pessoais ou arquivos de cache.

## Idiomas e traduções

O idioma de origem do Gettext é **en_US**. Português brasileiro está disponível via `po/pt_BR.po`, com catálogo compilado em `aeroscope/locale/pt_BR/LC_MESSAGES/aeroscope.mo`.

Para atualizar os catálogos, veja [`po/README.md`](po/README.md). Preserve placeholders, siglas técnicas (ICAO, METAR, SIGMET) e mensagens de logs traduzíveis.

## Política de provedores e segurança

- As fontes ADS-B e NOAA podem limitar requisições. Use cache, controle de intervalos e respeite HTTP 429.
- Regras de atribuição e licenciamento de mapas/fotos continuam aplicáveis.
- Não apresente interpolação visual, rota estimada ou códigos squawk como confirmação operacional.
- Não registre coordenadas sensíveis ou dados pessoais em relatórios públicos sem consentimento.

## English quick notes

Please open an issue describing expected and actual behavior before substantial UI changes. Keep the Linux-native UI responsive, add tests where appropriate, respect API rate limits and third-party licenses, and update Gettext strings for user-visible text. Run `python3 -m pytest -q`; verify GTK rendering on a real graphical Linux desktop.

Obrigado por ajudar a construir o AeroScope! ✈️
