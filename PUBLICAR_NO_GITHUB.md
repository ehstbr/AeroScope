# Publicando o AeroScope no GitHub

Este pacote foi preparado a partir do **código-fonte original 0.3.70**, sem incorporar o manual HTML ao aplicativo. Os novos arquivos são de **documentação, imagens e colaboração**.

## O que publicar onde?

- **Repositório (código-fonte):** conteúdo desta pasta, incluindo `README.md`, `README.en.md`, `CHANGELOG.md`, `aeroscope/`, `assets/`, `po/`, testes e imagens de apresentação.
- **Releases:** o `.deb` original da versão 0.3.70, oferecido separadamente aos usuários. Não é necessário colocar instaladores dentro da árvore do código.
- **Manual HTML:** hospedagem externa em URL ainda a definir. Ela poderá ser indicada posteriormente no README e no menu do aplicativo, sem incorporar os arquivos ao `.deb`.

## Se o repositório ainda estiver vazio

1. Crie um repositório no GitHub, idealmente com o mesmo nome usado no código: **Aeroscope**.
2. **Não** solicite ao GitHub a geração automática de um README ou LICENSE, pois eles já existem aqui.
3. Extraia o ZIP deste pacote, entre na pasta que contém `README.md` e execute:

```bash
git init
git branch -M main
git add .
git commit -m "Publica AeroScope 0.3.70 com README e imagens"
git remote add origin https://github.com/ehstbr/Aeroscope.git
git push -u origin main
```

Se o repositório já possui commits, prefira **cloná-lo e copiar os arquivos para o clone**, para preservar o histórico. Não use `git push --force` para substituir trabalho existente.

## Se o repositório já existe

```bash
git clone https://github.com/ehstbr/Aeroscope.git
cd Aeroscope
# Copie o conteúdo do pacote extraído para esta pasta, preservando .git/
git status
git add .
git commit -m "Atualiza documentação e apresentação para 0.3.70"
git push
```

> O upload de um ZIP na interface do GitHub **não descompacta** automaticamente seu conteúdo. Extraia primeiro e envie os arquivos ou use Git.

## Publicando o .deb na aba Releases

1. Abra **Releases → Draft a new release**.
2. Crie a tag `v0.3.70`, apontando para o commit correspondente.
3. Título sugerido: **AeroScope 0.3.70 — Smooth map navigation**.
4. Resuma as novidades (atalhos Alt, navegação suave pelas setas, recursos de radar e meteorologia).
5. Anexe o **instalador `.deb` original**, sem as revisões `+manual1` e `+manual2`.
6. Publique a release. O link no README para **Releases** ficará útil após a publicação.

## Aparência do repositório

**Descrição sugerida:**

> Native Linux aircraft radar with GTK4/Libadwaita, ADS-B live tracking, aviation weather, historical playback and monitoring.

**Topics sugeridos:** `linux`, `gtk4`, `libadwaita`, `python`, `aviation`, `ads-b`, `flight-tracker`, `radar`, `metar`, `sigmet`, `open-source`.

**Website:** deixe em branco até escolher a URL pública do manual ou da página do projeto.

## Conferência após publicar

- A página inicial mostra a imagem principal e todas as imagens da galeria.
- Os links `README.en.md`, `CHANGELOG.md`, `CONTRIBUTING.md` e `LICENSE` funcionam.
- O workflow **Python tests** em **Actions** passa sem falhas.
- O release oferece a versão original 0.3.70 (sem manual embutido).
- A licença MIT aparece no GitHub.
