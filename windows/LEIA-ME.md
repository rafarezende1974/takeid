# TakeID 1.0.0 by DX Labs — renomeação em lote (Windows)

Renomeia fotos, arquivos RAW e vídeos em lote, no padrão
`{evento}_{tipo}_{seq:0000}` — ex.: `EXPO2026_FOTO_0001.JPG`,
`EXPO2026_FOTO_0001.ARW` e `EXPO2026_TAKE_0001.MP4`.

Recomeço no padrão DX Labs (Python + Tkinter, `.exe` portátil via
GitHub Actions). Não é Flutter e não usa o código feito no ChatGPT
(série 0.3, sem build certificado, sem EXIF, sem presets e sem
Desfazer persistente). O nome, o visual roxo e o exemplo canônico
vêm do mockup do TakeID.

## O que faz na v1.0.0

- Adicionar arquivos ou pasta inteira (com opção de incluir
  subpastas); Limpar só esvazia a lista, não apaga arquivos
- Preview ao vivo Original → Novo, com miniatura 64 px para JPG
- Pareamento JPG + RAW: o mesmo clique ganha o mesmo número
  (`DSC001.JPG` + `DSC001.ARW` → `..._FOTO_0001.JPG` / `.ARW`)
- Contadores separados: fotos e vídeos começam cada um no seu
  início configurável (ex.: fotos em 125, vídeos em 20)
- Tipo configurável: FOTO para JPG/RAW, **TAKE para vídeos**
  (o manual do ChatGPT usava VIDEO; o mockup usa TAKE — o
  preset permite trocar para VIDEO se preferir)
- Tokens: `{evento} {tipo} {nome} {seq} {seq:0000} {data} {datafoto}
  {hora} {cliente} {ext} {pasta}` + `{original}` (alias de `{nome}`)
- Presets prontos e editáveis, salvos neste PC: Padrão TakeID,
  Casamento, Ensaio, Evento corporativo, Feira / Estande, Só numerar
- Data da foto via EXIF (JPG, `DateTimeOriginal`); sem EXIF, usa a
  data de modificação e mostra o selo "sem EXIF"
- Filtros Todos / JPG / RAW / Vídeos, "Selecionar somente filtro",
  "Marcar/Desmarcar visíveis", busca rápida, ordenação por nome,
  data da foto, data de modificação ou tamanho
- **Segurança:** conflitos bloqueiam o lote (nome duplicado,
  destino já existente, caractere inválido, nome reservado do
  Windows, nome com mais de 240 caracteres, variável desconhecida);
  nunca sobrescreve; trocas de nome (A→B e B→A) em duas passadas
  com nomes temporários; relatório final e **Desfazer do último
  lote** pelo log de → para (CSV + JSON), que funciona mesmo após
  fechar e reabrir o app
- Histórico de lotes aplicados, com o detalhe de/para de cada um

## O que NÃO faz (de propósito)

- Não move, copia ou apaga arquivos — só troca o nome, no mesmo lugar
- Não converte formato nem altera o conteúdo da mídia
- Não renomeia pastas, não lê subpastas sem a opção marcada,
  não usa regex (v1.1), nuvem, conta ou IA — tudo local, offline

## Como testar primeiro (recomendado)

1. **Copie uma pasta pequena (20 a 50 arquivos de um evento) para
   uma pasta de teste — nunca teste direto na pasta original.**
2. Abra o `TakeID.exe`, clique em "Adicionar Pasta" e escolha a
   pasta de teste.
3. Confira a prévia: pares JPG+RAW com o mesmo número, vídeos
   com TAKE e a sequência certa. Resolva qualquer linha vermelha.
4. Clique em "Renomear Arquivos", confirme e confira o relatório.
5. Clique em "Desfazer último lote" e confira que os nomes
   originais voltaram. Só depois use numa pasta real.

## Build (mesmo esquema do DX Select)

1. Criar o repositório no GitHub pela web: `rafarezende1974/takeid`.
2. Subir: `app.py`, `rename_engine.py`, `generate_assets.py`,
   `requirements.txt`, `test_engine.py`, `LEIA-ME.md`,
   `WORKFLOW-BUILD-WINDOWS.yml.txt`, `.gitignore`.
   Não subir `assets/` (o workflow gera o ícone no runner) nem
   `takeid_dados/` (presets, logs e histórico locais).
3. Criar pela web o arquivo `.github/workflows/build-windows.yml`
   colando o conteúdo de `WORKFLOW-BUILD-WINDOWS.yml.txt`.
4. O build gera o artefato `takeid` com `TakeID.exe`.
   Apagar o .exe antigo antes de baixar o novo — os artefatos
   têm o mesmo nome.

Sem certificado de assinatura, o Windows pode mostrar "editor
desconhecido" (SmartScreen) na primeira execução — é o aviso
padrão para .exe sem assinatura, igual ao dos outros apps DX.

## Arquivos

- `app.py` — interface Tkinter (janela "TakeID 1.0.0 by DX Labs")
- `rename_engine.py` — motor puro: classificação, pareamento,
  tokens, validação, aplicação em duas passadas, log e desfazer
- `generate_assets.py` — gera o ícone (claquete roxa, próprio
  da função, não a logo da DX Labs)
- `test_engine.py` — testes do motor com arquivos temporários
  (rode com `python test_engine.py`; não precisa de fotos reais
  nem de tela)
- `takeid_dados/` — criado na primeira execução, ao lado do .exe:
  `presets.json`, `ultimo_lote.json/.csv`, `historico.json`
