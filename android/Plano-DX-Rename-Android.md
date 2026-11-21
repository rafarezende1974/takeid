# DX Rename — Plano v1 Android (Kotlin)

**Data:** 2026-11-20
**Base:** `~/workspace/dx-rename/Plano-DX-Rename.md` (18/11) + Windows v1 já entregue e validado (repo `rafarezende1974/takeid`, branch `main`).
**Decisão dele (20/11):** os dois aparelhos, com layout adaptável — Galaxy S24 (celular) e Tab S9+ (tablet).

## O que é

A mesma v1 do Windows, em Kotlin nativo, offline, sem conta e sem nuvem. Mesmo motor de regras, mesmos tokens, mesmos presets, mesmo comportamento de segurança (preview obrigatório, conflitos bloqueiam, nunca sobrescreve, Desfazer com log). O que muda é só a plataforma: acesso a arquivos via SAF, layout por toque e telas adaptáveis.

## Regras — iguais às do Windows (sem divergência)

- **Classificação:** foto (JPG/RAW), vídeo, arquivo; pares JPG+RAW com o mesmo nome-base ganham o mesmo número sequencial.
- **Contadores separados** de foto e vídeo, com início configurável; vídeos usam o tipo **TAKE** por padrão (configurável por preset), como no Windows.
- **Tokens:** `{evento} {tipo} {nome} {original} {seq} {seq:0000} {data} {datafoto} {hora} {cliente} {ext} {pasta}`; maiúsculas e espaços→`_` opcionais.
- **Validação de conflitos bloqueia o lote:** duplicado, destino já existente, caracteres inválidos, nomes reservados, >240 caracteres, variável desconhecida. Arquivo já com o nome-alvo vira "Sem alteração" e é pulado, não bloqueia.
- **Nunca sobrescreve; renomeação em duas passadas** para trocas A↔B; log de→para (CSV + JSON) e Desfazer persistente do último lote.
- **Presets:** Padrão DX Rename, Casamento, Ensaio, Evento, Feira — os mesmos do Windows, editáveis, salvos no aparelho.
- **EXIF:** data da foto via `ExifInterface` / MediaStore `DATE_TAKEN`, com fallback para data de modificação e selo "sem EXIF".
- **Limite de nome:** 240 caracteres (mesmo do Windows).

## Android — o que é diferente (limites honestos)

- **Só renomeia dentro da pasta autorizada**, pelo seletor de pastas do sistema (SAF, `ACTION_OPEN_DOCUMENT_TREE`). A autorização é pedida uma vez por pasta e guardada (permissão persistente); se for revogada, o app pede de novo sem perder as regras montadas.
- **Pastas de mídia** podem pedir uma confirmação extra do sistema por lote (o Android pedindo, não o app). Confirmando, o lote continua.
- **Sem acesso** a pastas privadas de outros apps nem a áreas do sistema. Cartão SD e HD via OTG só funcionam se o usuário escolher a pasta por lá no seletor.
- **Após renomear, o app avisa o MediaStore** para a Galeria e outros apps verem os nomes novos sem reiniciar.
- **Sem arrastar e soltar** e sem seleção múltipla de arquivos avulsos fora da pasta — a entrada é sempre uma pasta autorizada (+ incluir subpastas, opcional).
- **Lotes grandes:** lista virtualizada (LazyColumn), motor fora da thread da interface, com progresso e cancelamento; o que já renomeou fica no log e pode ser desfeito.

## Layout adaptável — os dois aparelhos, um código

- **Celular (S24, ~360×800):** uma coluna, 3 etapas em abas na parte inferior (Pasta / Regras / Conferir). Botão Renomear grande e fixo no rodapé.
- **Tablet (Tab S9+, ≥600dp):** duas colunas — lista de arquivos à esquerda, painel Padrão/Regras à direita, como o Windows. Navegação lateral (rail) em vez de abas inferiores.
- **Visual:** o mesmo do Windows — fundo escuro roxo, acento roxo `#7B1FD0`, tabela clara, logo do DX Rename no topo, logo da DX Labs no rodapé. Material 3.
- **Toque:** regras em cards expansíveis, subir/descer por setas (sem arrastar fino); presets em chips; conflitos destacados em vermelho com o motivo.

## Stack

- **Linguagem:** Kotlin nativo, Jetpack Compose, Material 3, minSdk 26 (Android 8) / targetSdk 35.
- **Arquivos:** SAF (`DocumentFile`) + MediaStore; EXIF via `androidx.exifinterface`.
- **Dados locais:** DataStore (presets, configurações) + arquivos CSV/JSON de log em pasta do app; migração de presets do Windows não se aplica (aparelhos diferentes).
- **Pacote:** `br.com.dxlabs.dxrename`.
- **Build:** GitHub Actions (mesmo pipeline dos outros apps DX). **Build local nunca** — nesta VM o daemon do Gradle não conecta; só o GitHub Actions prova o build.
- **Distribuição v1:** APK direto do artefato do Actions (instalação manual, "fontes desconhecidas"). Play Store só depois, se ele quiser.

## Arquivos (repo `rafarezende1974/takeid`, pasta `android/`)

- `app/src/main/java/br/com/dxlabs/dxrename/` — `RenameEngine.kt` (motor puro, portado do `rename_engine.py`), `MainActivity.kt`, telas Compose, `Presets.kt`, `UndoLog.kt`, `SafFiles.kt`.
- `app/src/test/` — testes do motor (mesmos 14 casos do Windows, portados).
- `app/build.gradle.kts`, `settings.gradle.kts`, `gradle.properties`, `gradle/wrapper/`.
- `WORKFLOW-BUILD-ANDROID.yml.txt` — referência do workflow (o arquivo `.github/workflows/build-android.yml` ele cria na web, como no Windows).
- `LEIA-ME.md` — como instalar o APK e testar numa pasta-cópia.

## Ordem de construção

1. Plano + mockup (este documento + mockup navegável) — **aprovação dele**.
2. Motor Kotlin + testes (portar os 14 testes do Windows).
3. Telas Compose (Pasta / Regras / Conferir) com layout adaptável.
4. SAF + MediaStore + EXIF + presets + Desfazer.
5. Workflow do Actions → APK → ele testa no S24 e no Tab S9+ numa pasta-cópia.

## O que falta dele

1. Mockup aprovado (esta entrega).
2. Criar o workflow `.github/workflows/build-android.yml` na web quando o código subir (mesmo processo do Windows).
3. Testar o APK nos dois aparelhos, numa pasta-cópia, antes de qualquer pasta real.

## Fora da v1 (igual ao Windows)

Regex, renomear pastas, tags de música, metadados de câmera como token, Google Drive/nuvem, iOS, qualquer função que mova, copie ou apague arquivos.
