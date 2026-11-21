package br.com.dxlabs.dxrename

import java.io.File

/**
 * Log do último lote (de -> para) para o Desfazer.
 * Grava ultimo_lote.json + ultimo_lote.csv + historico.json na pasta
 * de arquivos do app, no mesmo formato do Windows. JSON escrito e
 * lido à mão (sem dependência extra) — só "de" e "para".
 */
object UndoLog {
    private fun esc(s: String): String = s
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")

    private fun unesc(s: String): String = s
        .replace("\\\"", "\"")
        .replace("\\\\", "\\")

    fun saveLastLog(logDir: File, done: List<Pair<String, String>>) {
        logDir.mkdirs()
        val rows = done.joinToString(",\n") { (de, para) ->
            "    {\"de\": \"${esc(de)}\", \"para\": \"${esc(para)}\"}"
        }
        val json = "{\n  \"total\": ${done.size},\n  \"arquivos\": [\n$rows\n  ]\n}\n"
        File(logDir, "ultimo_lote.json").writeText(json)
        val csv = buildString {
            append("de,para\n")
            for ((de, para) in done) append("\"$de\",\"$para\"\n")
        }
        File(logDir, "ultimo_lote.csv").writeText(csv)
        // Histórico: acrescenta o lote.
        val histFile = File(logDir, "historico.json")
        val prev = if (histFile.exists()) histFile.readText().trimEnd().removeSuffix("]") else "["
        val entry = "  {\"total\": ${done.size}, \"arquivos\": [\n$rows\n  ]}"
        val newText = if (prev == "[") "[\n$entry\n]\n" else "$prev,\n$entry\n]\n"
        histFile.writeText(newText)
    }

    /** Retorna [(de, para)] do último lote, ou vazio. */
    fun loadLastLog(logDir: File): List<Pair<String, String>> {
        val f = File(logDir, "ultimo_lote.json")
        if (!f.exists()) return emptyList()
        val text = f.readText()
        val re = Regex("\"de\":\\s*\"((?:\\\\.|[^\"])*)\",\\s*\"para\":\\s*\"((?:\\\\.|[^\"])*)\"")
        return re.findAll(text).map { m ->
            unesc(m.groupValues[1]) to unesc(m.groupValues[2])
        }.toList()
    }

    fun clearLastLog(logDir: File) {
        File(logDir, "ultimo_lote.json").delete()
        File(logDir, "ultimo_lote.csv").delete()
    }
}
