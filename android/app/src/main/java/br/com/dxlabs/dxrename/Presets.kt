package br.com.dxlabs.dxrename

/** Presets v1 — os mesmos do Windows (dxrename_dados/presets.json). */
data class Preset(val nome: String, val settings: RenameEngine.Settings)

object Presets {
    val ALL: List<Preset> = listOf(
        Preset(
            "Padrão DX Rename",
            RenameEngine.Settings(
                pattern = "{evento}_{tipo}_{seq:0000}", evento = "EXPO2026"
            )
        ),
        Preset(
            "Casamento",
            RenameEngine.Settings(
                pattern = "{datafoto}_{cliente}_{seq:03}",
                evento = "", cliente = "Karoline-Manuel"
            )
        ),
        Preset(
            "Ensaio",
            RenameEngine.Settings(
                pattern = "{cliente}_{tipo}_{datafoto}_{seq:02}",
                evento = "", cliente = "Mayara-Ewerton"
            )
        ),
        Preset(
            "Evento corporativo",
            RenameEngine.Settings(
                pattern = "{evento}_{datafoto}_{seq:03}",
                evento = "INDEX25"
            )
        ),
        Preset(
            "Feira / Estande",
            RenameEngine.Settings(
                pattern = "{cliente}_{evento}_{seq:03}",
                evento = "WindPower2026", cliente = "FairWind"
            )
        ),
        Preset(
            "Só numerar",
            RenameEngine.Settings(pattern = "{nome}_{seq:03}", evento = "")
        )
    )

    val TOKENS_HELP = "{evento} {tipo} {nome} {original} {seq} {seq:0000} " +
        "{data} {datafoto} {hora} {cliente} {ext} {pasta}"
}
