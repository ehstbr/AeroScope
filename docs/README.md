# Manual offline do AeroScope v0.3.70

Abra `index.html` diretamente no navegador. Não exige servidor, conexão ou bibliotecas externas.

## Estrutura

- `index.html`: todos os capítulos, conteúdo semântico e legendas.
- `css/style.css`: design responsivo e regras de impressão.
- `js/manual.js`: busca, tema, progresso, navegação e visualização de imagens.
- `assets/screenshots/`: capturas reais otimizadas em WebP e PNG; as duas imagens de emergências permanecem em PNG para facilitar futuras substituições.
- `screenshots-manifest.csv`: relação da origem de cada captura.

## Capturas de emergências (código 7600)

O capítulo **Emergências** utiliza duas capturas reais enviadas pelo autor, ambas da aeronave N6377T com indicação 7600:

- `assets/screenshots/emergencias-painel.png`: aba de emergências com a ocorrência listada e o mapa ainda centralizado em Minas Gerais (Figura 15).
- `assets/screenshots/emergencias-detalhes.png`: após centralizar a aeronave, seu painel com os detalhes disponíveis em Louisiana, EUA (Figura 16).

Para trocar imagens futuramente, substitua o PNG correspondente mantendo o mesmo nome e atualize o texto/alt/legenda em `index.html` se o conteúdo tiver mudado. Atualize também `screenshots-manifest.csv` para registrar a origem.

**Importante:** o código ADS-B publicado não comprova, isoladamente, uma emergência real. As capturas não são simulações criadas para o manual.

## Uso no AeroScope

A integração com o item **Manual** abre este `index.html` local no WebKitGTK, quando disponível; caso contrário, usa o navegador padrão. Não é necessário iniciar servidor HTTP. A instalação DEB inclui os arquivos em `/usr/share/doc/aeroscope/manual/`.

## Publicação

Para publicar no GitHub Pages depois, copie os arquivos preservando os caminhos relativos. O HTML/CSS/JS não usa CDN, cookies ou telemetria.

## Segurança

O material é educativo, não homologado para navegação aeronáutica. Créditos dos provedores constam do último capítulo. O manual nunca incorpora fotos externas das aeronaves; usa apenas as capturas fornecidas do aplicativo.
