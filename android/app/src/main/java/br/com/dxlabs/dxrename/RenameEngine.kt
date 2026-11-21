package br.com.dxlabs.dxrename

import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

/**
 * DX Rename 1.0.0 by DX Labs — motor de renomeação em lote (Android).
 * Porte direto do rename_engine.py do Windows (v1 validada).
 * Motor puro, sem Android e sem Compose: classifica, pareia JPG+RAW,
 * calcula sequências, monta nomes por tokens, valida conflitos e
 * aplica o lote em duas passadas. Nada é renomeado sem preview.
 *
 * Regras duras (iguais ao Windows):
 * - conflitos BLOQUEIAM o lote: duplicado, destino existente,
 *   caractere inválido, nome reservado, nome > 240 chars,
 *   variável desconhecida no padrão.
 * - nunca sobrescreve; trocas A<->B em duas passadas com temporários.
 * - arquivo já com o nome-alvo vira "Sem alteração" e é pulado.
 */
object RenameEngine {
    const val VERSION = "1.0.0"

    val JPG_EXTS = setOf(".jpg", ".jpeg")
    val RAW_EXTS = setOf(
        ".raw", ".arw", ".cr2", ".cr3", ".nef", ".nrw", ".dng",
        ".raf", ".rw2", ".orf", ".pef", ".srw", ".3fr", ".iiq"
    )
    val VIDEO_EXTS = setOf(
        ".mp4", ".mov", ".mxf", ".avi", ".mkv",
        ".mts", ".m2ts", ".m4v", ".webm"
    )

    const val KIND_PHOTO = "FOTO"
    const val KIND_VIDEO = "VIDEO"
    const val KIND_OTHER = "ARQUIVO"

    val INVALID_CHARS = setOf('<', '>', ':', '"', '/', '\\', '|', '?', '*')
    val RESERVED_NAMES = setOf(
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    )
    const val MAX_NAME_LEN = 240

    private val TOKEN_RE = Regex("\\{([^{}]+)\\}")
    private val SIMPLE_TOKENS = setOf(
        "evento", "tipo", "nome", "original", "data", "datafoto",
        "hora", "cliente", "ext", "pasta"
    )

    fun classify(name: String): String {
        val ext = "." + name.substringAfterLast('.', "").lowercase(Locale.ROOT)
        return when {
            ext in JPG_EXTS -> "JPG"
            ext in RAW_EXTS -> "RAW"
            ext in VIDEO_EXTS -> "VIDEO"
            else -> "ARQUIVO"
        }
    }

    fun kindOf(classification: String): String = when (classification) {
        "JPG", "RAW" -> KIND_PHOTO
        "VIDEO" -> KIND_VIDEO
        else -> KIND_OTHER
    }

    fun stemOf(name: String): String {
        val dot = name.lastIndexOf('.')
        return if (dot > 0) name.substring(0, dot) else name
    }

    fun extOf(name: String): String {
        val dot = name.lastIndexOf('.')
        return if (dot >= 0) name.substring(dot) else ""
    }

    /** Converte um formato estilo Python ("%Y-%m-%d") para SimpleDateFormat. */
    fun formatDate(millis: Long, strftimePattern: String): String {
        val javaPattern = strftimePattern
            .replace("%Y", "yyyy")
            .replace("%m", "MM")
            .replace("%d", "dd")
            .replace("%H", "HH")
            .replace("%M", "mm")
            .replace("%S", "ss")
        return try {
            SimpleDateFormat(javaPattern, Locale.getDefault()).format(Date(millis))
        } catch (_: Exception) {
            SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date(millis))
        }
    }

    data class Settings(
        val pattern: String = "{evento}_{tipo}_{seq:0000}",
        val evento: String = "EXPO2026",
        val cliente: String = "",
        val tipoFoto: String = "FOTO",
        val tipoVideo: String = "TAKE",
        val tipoArquivo: String = "ARQUIVO",
        val inicioFotos: Int = 1,
        val inicioVideos: Int = 1,
        val inicioArquivos: Int? = null,
        val formatoData: String = "%Y-%m-%d",
        val maiusculas: Boolean = false,
        val substituirEspacos: Boolean = false,
        val usarDataArquivo: Boolean = true,
        val parearRawJpg: Boolean = true
    )

    /** Entrada do motor: um arquivo já listado (SAF ou File). */
    data class InputFile(
        val name: String,
        val parentName: String = "",
        /** millis da data de modificação do arquivo. */
        val lastModifiedMillis: Long = System.currentTimeMillis(),
        /** millis da data da foto (EXIF DateTimeOriginal), se houver. */
        val photoDateMillis: Long? = null,
        val hasExif: Boolean = false
    )

    data class PlanEntry(
        val originalName: String,
        val parentName: String = "",
        val newName: String = "",
        val kind: String = "ARQUIVO",
        val tipo: String = "ARQUIVO",
        val seq: Int = 0,
        val error: String? = null,
        val noChange: Boolean = false,
        val hasExif: Boolean = false,
        val photoDateMillis: Long? = null
    ) {
        val ok: Boolean get() = error == null
    }

    private fun seqWidth(spec: String): Int? {
        if (spec.isEmpty()) return null
        if (spec.all { it == '0' }) return spec.length
        if (spec.all { it.isDigit() }) return spec.toIntOrNull()
        return null
    }

    /** Monta o nome-base. Retorna Pair(nome, erro?). */
    fun renderPattern(pattern: String, values: Map<String, String>, seq: Int): Pair<String, String?> {
        val out = StringBuilder()
        var last = 0
        for (m in TOKEN_RE.findAll(pattern)) {
            out.append(pattern.substring(last, m.range.first))
            val token = m.groupValues[1]
            when {
                token == "seq" -> out.append("%04d".format(seq))
                token.startsWith("seq:") -> {
                    val width = seqWidth(token.substring(4))
                    if (width == null) return "" to "Sequência inválida: {$token}"
                    out.append(seq.toString().padStart(width, '0'))
                }
                token in SIMPLE_TOKENS -> out.append(values[token] ?: "")
                else -> return "" to "Variável desconhecida: {$token}"
            }
            last = m.range.last + 1
        }
        out.append(pattern.substring(last))
        return out.toString() to null
    }

    /**
     * Calcula o preview Original -> Novo, na ordem recebida.
     * [existingNames] = nomes (lowercase) já presentes na pasta, para
     * detectar "Destino já existe" fora do lote. Passe vazio nos testes
     * que não precisam dessa checagem — o Windows usa o disco.
     */
    fun buildPlan(
        files: List<InputFile>,
        settings: Settings,
        existingNames: Set<String> = emptySet()
    ): List<PlanEntry> {
        var photoNext = settings.inicioFotos
        var videoNext = settings.inicioVideos
        var otherNext = settings.inicioArquivos ?: settings.inicioFotos
        val photoGroups = mutableMapOf<Pair<String, String>, Int>()
        val groupFirstName = mutableMapOf<Pair<String, String>, String>()
        val now = System.currentTimeMillis()

        val entries = files.map { file ->
            val classification = classify(file.name)
            val kind = kindOf(classification)
            val base = stemOf(file.name)
            val ext = extOf(file.name)
            val dt = file.photoDateMillis ?: file.lastModifiedMillis
            val refDt = if (settings.usarDataArquivo) dt else now
            val datafotoDt = if (file.hasExif) dt else refDt

            val seq: Int
            val tipo: String
            val nomeToken: String
            when (kind) {
                KIND_PHOTO -> {
                    tipo = settings.tipoFoto
                    if (settings.parearRawJpg) {
                        val key = file.parentName.lowercase(Locale.ROOT) to base.lowercase(Locale.ROOT)
                        if (key !in photoGroups) {
                            photoGroups[key] = photoNext
                            groupFirstName[key] = base
                            photoNext++
                        }
                        seq = photoGroups.getValue(key)
                        nomeToken = groupFirstName.getValue(key)
                    } else {
                        seq = photoNext; photoNext++
                        nomeToken = base
                    }
                }
                KIND_VIDEO -> {
                    tipo = settings.tipoVideo
                    seq = videoNext; videoNext++
                    nomeToken = base
                }
                else -> {
                    tipo = settings.tipoArquivo
                    seq = otherNext; otherNext++
                    nomeToken = base
                }
            }

            val values = mapOf(
                "evento" to settings.evento,
                "tipo" to tipo,
                "nome" to nomeToken,
                "original" to nomeToken,
                "data" to formatDate(refDt, settings.formatoData),
                "datafoto" to formatDate(datafotoDt, settings.formatoData),
                "hora" to formatDate(refDt, "%H%M%S"),
                "cliente" to settings.cliente,
                "ext" to ext.trimStart('.'),
                "pasta" to file.parentName
            )
            var (newBase, error) = renderPattern(settings.pattern, values, seq)
            if (error == null) {
                if (settings.substituirEspacos) newBase = newBase.replace(Regex("\\s+"), "_")
                if (settings.maiusculas) newBase = newBase.uppercase(Locale.ROOT)
            }
            val newName = if (error == null) newBase + ext else ""
            PlanEntry(
                originalName = file.name, parentName = file.parentName,
                newName = newName, kind = classification, tipo = tipo,
                seq = seq, error = error, hasExif = file.hasExif,
                photoDateMillis = file.photoDateMillis
            )
        }
        return validate(entries, existingNames)
    }

    private fun validate(entries: List<PlanEntry>, existingNames: Set<String>): List<PlanEntry> {
        val originals = entries.map { it.originalName.lowercase(Locale.ROOT) }.toSet()
        val destCount = mutableMapOf<String, Int>()
        for (e in entries) {
            if (e.newName.isNotEmpty() && e.error == null) {
                val key = e.newName.lowercase(Locale.ROOT)
                destCount[key] = (destCount[key] ?: 0) + 1
            }
        }
        return entries.map { e ->
            if (e.error != null) return@map e
            var error: String? = null
            var noChange = false
            when {
                e.newName.isEmpty() -> error = "Nome vazio"
                e.newName == e.originalName -> noChange = true
                e.newName.any { it in INVALID_CHARS } ->
                    error = "Caractere inválido no Windows (< > : \" / \\ | ? *)"
                stemOf(e.newName).uppercase(Locale.ROOT) in RESERVED_NAMES ->
                    error = "Nome reservado do Windows: ${stemOf(e.newName)}"
                e.newName.length > MAX_NAME_LEN ->
                    error = "Nome com mais de $MAX_NAME_LEN caracteres"
                (destCount[e.newName.lowercase(Locale.ROOT)] ?: 0) > 1 ->
                    error = "Nome duplicado no lote"
                e.newName.lowercase(Locale.ROOT) in existingNames &&
                    e.newName.lowercase(Locale.ROOT) !in originals ->
                    error = "Destino já existe"
                else -> { /* ok */ }
            }
            e.copy(error = error, noChange = noChange)
        }
    }

    fun hasConflicts(plan: List<PlanEntry>): Boolean = plan.any { it.error != null }
    fun countConflicts(plan: List<PlanEntry>): Int = plan.count { it.error != null }

    // ------------------------------------------------------------------
    // Aplicação em arquivos java.io.File (usada nos testes unitários;
    // no aparelho a aplicação é via SAF, em SafFiles.kt).
    // ------------------------------------------------------------------

    /**
     * Duas passadas: origem -> temporário único, temporário -> destino.
     * Retorna Pair(concluídos, erros). Em erro, restaura o que foi feito.
     */
    fun renameTwoPass(pairs: List<Pair<File, File>>): Pair<List<Pair<File, File>>, List<String>> {
        val done = mutableListOf<Pair<File, File>>()
        val errors = mutableListOf<String>()
        val temps = mutableListOf<Triple<File, File, File>>()
        for ((i, pair) in pairs.withIndex()) {
            val (src, dst) = pair
            val tmp = File(src.parentFile, ".dxrename-${UUID.randomUUID().toString().take(10)}-$i${src.extension.let { if (it.isEmpty()) "" else ".$it" }}")
            try {
                if (!src.renameTo(tmp)) throw IllegalStateException("renameTo retornou false")
                temps.add(Triple(src, tmp, dst))
            } catch (ex: Exception) {
                errors.add("${src.name}: não foi possível renomear ($ex)")
                break
            }
        }
        if (errors.isNotEmpty()) {
            for ((src, tmp, _) in temps) {
                try { tmp.renameTo(src) } catch (_: Exception) {
                    errors.add("${src.name}: falha ao restaurar após erro")
                }
            }
            return emptyList<Pair<File, File>>() to errors
        }
        for ((src, tmp, dst) in temps) {
            try {
                if (!tmp.renameTo(dst)) throw IllegalStateException("renameTo retornou false")
                done.add(src to dst)
            } catch (ex: Exception) {
                errors.add("${src.name} -> ${dst.name}: falhou ($ex)")
                break
            }
        }
        if (errors.isNotEmpty()) {
            for ((src, dst) in done) {
                try { dst.renameTo(src) } catch (_: Exception) {
                    errors.add("${src.name}: falha ao restaurar após erro")
                }
            }
            for ((src, tmp, dst) in temps) {
                if (tmp.exists() && (src to dst) !in done) {
                    try { tmp.renameTo(src) } catch (_: Exception) {
                        errors.add("${src.name}: falha ao restaurar após erro")
                    }
                }
            }
            return emptyList<Pair<File, File>>() to errors
        }
        return done to errors
    }
}
