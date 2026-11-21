# DX Rename — Android v1

Kotlin nativo + Jetpack Compose, offline, sem conta e sem nuvem.
Mesmo motor, regras e presets do Windows v1 (validado).

- Pacote: `br.com.dxlabs.dxrename`
- minSdk 26 / targetSdk 35, compileSdk 36
- Acesso a arquivos: só via seletor de pastas do sistema (SAF)
- Layout adaptável: celular (S24, 1 coluna, abas) / tablet (Tab S9+, 2 colunas)

## Como instalar e testar

1. No GitHub, crie o arquivo `.github/workflows/build-android.yml`
   e cole o conteúdo de `WORKFLOW-BUILD-ANDROID.yml.txt`.
2. Quando o build ficar verde, baixe o artefato `dx-rename-android`
   e instale o `app-debug.apk` no S24 e no Tab S9+.
3. Teste numa **pasta-cópia** primeiro, nunca numa pasta real.
4. No app: Escolher pasta → Regras (preset Casamento etc.) →
   Conferir (preview) → Renomear. Desfazer restaura o último lote.

## O que está dentro

- `app/src/main/java/br/com/dxlabs/dxrename/RenameEngine.kt` — motor puro
- `app/src/test/.../RenameEngineTest.kt` — os 14 testes do Windows, portados
- `MainActivity.kt` — telas Pasta / Regras / Conferir
- `SafFiles.kt` — SAF + EXIF + MediaStore
- `Presets.kt`, `UndoLog.kt` — presets e log de Desfazer

## Fora da v1

Regex, renomear pastas, Google Drive/nuvem, iOS, mover/copiar/apagar.
