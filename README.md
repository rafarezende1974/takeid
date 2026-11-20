# TakeID by DX Labs

Renomeação de arquivos em lote para fotografias, arquivos RAW e vídeos — Windows e Android.

## Windows v1

Código em `windows/` (Python + Tkinter, `.exe` portátil via GitHub Actions):

- `app.py` — interface
- `rename_engine.py` — motor de renomeação (pareamento JPG+RAW, contadores foto/vídeo, EXIF, conflitos, Desfazer)
- `test_engine.py` — 14 testes do motor
- `generate_assets.py` — gera o ícone
- `WORKFLOW-BUILD-WINDOWS.yml.txt` — conteúdo do workflow `.github/workflows/build-windows.yml`
- `LEIA-ME.md` — como testar e como gerar o build

Teste primeiro numa pasta-cópia pequena (20–50 arquivos), nunca direto na pasta original.
