package br.com.dxlabs.dxrename

import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.documentfile.provider.DocumentFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.Locale
import java.util.UUID

private val Purple = Color(0xFF7B1FD0)
private val Bg = Color(0xFF12101A)

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { DxRenameApp() }
    }

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    fun DxRenameApp() {
        var step by remember { mutableIntStateOf(0) }
        var folderUri by remember { mutableStateOf<Uri?>(null) }
        var folderName by remember { mutableStateOf("") }
        var files by remember { mutableStateOf<List<DocumentFile>>(emptyList()) }
        var settings by remember { mutableStateOf(RenameEngine.Settings()) }
        var presetIndex by remember { mutableIntStateOf(0) }
        // true quando o usuário digitou o próprio padrão no campo Padrão.
        // Nesse caso, tocar num preset pede confirmação antes de apagar
        // o padrão dele (o Windows mostra "Preset aplicado"; aqui antes
        // a troca era silenciosa e o padrão sumia sem aviso).
        var patternCustom by remember { mutableStateOf(false) }
        var pendingPreset by remember { mutableStateOf<Int?>(null) }
        var status by remember { mutableStateOf("") }
        var renaming by remember { mutableStateOf(false) }
        var undoAvailable by remember {
            mutableStateOf(UndoLog.loadLastLog(File(filesDir, "dxrename_dados")).isNotEmpty())
        }
        val scope = rememberCoroutineScope()

        val pickFolder = androidx.activity.compose.rememberLauncherForActivityResult(
            ActivityResultContracts.OpenDocumentTree()
        ) { uri ->
            if (uri == null) return@rememberLauncherForActivityResult
            try {
                contentResolver.takePersistableUriPermission(
                    uri,
                    android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION or
                        android.content.Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                )
            } catch (_: Exception) { }
            folderUri = uri
            val root = DocumentFile.fromTreeUri(this, uri)
            folderName = root?.name ?: "Pasta escolhida"
            files = SafFiles.listFiles(this, uri)
            status = "${files.size} arquivo(s) na pasta."
        }

        fun refreshFiles() {
            val uri = folderUri ?: return
            files = SafFiles.listFiles(this, uri)
        }

        fun buildPlan(): List<RenameEngine.PlanEntry> {
            if (files.isEmpty()) return emptyList()
            val inputs = files.map { SafFiles.toInputFile(this, it, folderName) }
            val existing = files.map { it.name!!.lowercase(Locale.ROOT) }.toSet()
            return RenameEngine.buildPlan(inputs, settings, existing)
        }

        val plan = buildPlan()
        val conflicts = RenameEngine.countConflicts(plan)

        fun doRename() {
            val uri = folderUri ?: return
            val toRename = plan.filter { it.ok && !it.noChange }
            if (toRename.isEmpty()) {
                status = "Nada para renomear."
                return
            }
            renaming = true
            status = "Renomeando ${toRename.size} arquivo(s)…"
            scope.launch(Dispatchers.IO) {
                val byName = files.associateBy { it.name }
                // Passada 1: original -> temporário. Indexado pelo nome
                // original (não pela posição): se algum arquivo não for
                // achado e for pulado, a passada 2 não casa o arquivo
                // errado com o nome errado.
                val temps = mutableMapOf<String, Triple<DocumentFile, String, String>>()
                var error: String? = null
                for ((i, entry) in toRename.withIndex()) {
                    val doc = byName[entry.originalName] ?: continue
                    val ext = RenameEngine.extOf(entry.originalName)
                    val temp = ".dxrename-${UUID.randomUUID().toString().take(8)}-$i$ext"
                    if (!SafFiles.renameTo(doc, temp)) {
                        error = "${entry.originalName}: não foi possível renomear"
                        break
                    }
                    temps[entry.originalName] = Triple(doc, entry.originalName, temp)
                }
                if (error != null) {
                    for ((doc, original, _) in temps.values) {
                        SafFiles.renameTo(doc, original)
                    }
                    withContext(Dispatchers.Main) {
                        renaming = false; status = "Erro: $error. Nada foi alterado."
                    }
                    return@launch
                }
                // Passada 2: temporário -> final.
                val done = mutableListOf<Pair<String, String>>()
                for (entry in toRename) {
                    val triple = temps[entry.originalName] ?: continue
                    val (doc, original, _) = triple
                    if (!SafFiles.renameTo(doc, entry.newName)) {
                        error = "$original -> ${entry.newName}: falhou"
                        break
                    }
                    done.add(original to entry.newName)
                }
                if (error != null) {
                    for ((original, newName) in done) {
                        val doc = SafFiles.listFiles(this@MainActivity, uri)
                            .firstOrNull { it.name == newName }
                        if (doc != null) SafFiles.renameTo(doc, original)
                    }
                    for ((doc, original, _) in temps.values) {
                        if (doc.name?.startsWith(".dxrename-") == true) {
                            SafFiles.renameTo(doc, original)
                        }
                    }
                    withContext(Dispatchers.Main) {
                        renaming = false; status = "Erro: $error. Lote restaurado."
                    }
                    return@launch
                }
                UndoLog.saveLastLog(File(filesDir, "dxrename_dados"), done)
                SafFiles.notifyMediaStore(this@MainActivity)
                withContext(Dispatchers.Main) {
                    renaming = false
                    undoAvailable = true
                    status = "${done.size} arquivo(s) renomeado(s). Desfazer disponível."
                    refreshFiles()
                }
            }
        }

        fun doUndo() {
            val uri = folderUri
            val log = UndoLog.loadLastLog(File(filesDir, "dxrename_dados"))
            if (log.isEmpty()) {
                status = "Não há lote para desfazer."
                return
            }
            renaming = true
            scope.launch(Dispatchers.IO) {
                var restored = 0
                val errors = mutableListOf<String>()
                if (uri != null) {
                    val current = SafFiles.listFiles(this@MainActivity, uri)
                        .associateBy { it.name }
                    for ((original, novo) in log) {
                        val doc = current[novo]
                        if (doc == null) {
                            errors.add("$novo: arquivo renomeado não encontrado")
                            continue
                        }
                        if (current[original] != null) {
                            errors.add("$original: o nome original já está ocupado")
                            continue
                        }
                        if (SafFiles.renameTo(doc, original)) restored++ else {
                            errors.add("$novo: falhou ao restaurar")
                        }
                    }
                }
                if (errors.isEmpty()) UndoLog.clearLastLog(File(filesDir, "dxrename_dados"))
                SafFiles.notifyMediaStore(this@MainActivity)
                withContext(Dispatchers.Main) {
                    renaming = false
                    undoAvailable = UndoLog.loadLastLog(File(filesDir, "dxrename_dados")).isNotEmpty()
                    status = if (errors.isEmpty()) {
                        "$restored arquivo(s) restaurado(s)."
                    } else {
                        "$restored restaurado(s). Erros: ${errors.joinToString("; ")}"
                    }
                    refreshFiles()
                }
            }
        }

        pendingPreset?.let { i ->
            val preset = Presets.ALL[i]
            AlertDialog(
                onDismissRequest = { pendingPreset = null },
                title = { Text("Aplicar preset “${preset.nome}”?") },
                text = {
                    Text(
                        "Seu padrão atual é ${settings.pattern}.\n" +
                            "O preset usa ${preset.settings.pattern} e vai substituir o seu padrão. " +
                            "Evento, cliente e tipos também passam a ser os do preset."
                    )
                },
                confirmButton = {
                    TextButton(onClick = {
                        presetIndex = i
                        settings = preset.settings
                        patternCustom = false
                        pendingPreset = null
                        status = "Preset “${preset.nome}” aplicado."
                    }) { Text("Aplicar preset") }
                },
                dismissButton = {
                    TextButton(onClick = { pendingPreset = null }) { Text("Manter meu padrão") }
                }
            )
        }

        MaterialTheme(colorScheme = darkColorScheme(primary = Purple, background = Bg, surface = Color(0xFF1E1A2E))) {
            Scaffold(
                topBar = {
                    TopAppBar(
                        title = { Text("DX Rename 1.0.0 by DX Labs", fontWeight = FontWeight.Bold) },
                        colors = TopAppBarDefaults.topAppBarColors(containerColor = Purple)
                    )
                }
            ) { pad ->
                BoxWithConstraints(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Bg)
                        .padding(pad)
                        .padding(12.dp)
                ) {
                    val isTablet = maxWidth >= 600.dp
                    Column(modifier = Modifier.fillMaxSize()) {
                        // Abas / passos
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf("1 · Pasta", "2 · Regras", "3 · Conferir").forEachIndexed { i, label ->
                                OutlinedButton(
                                    onClick = { step = i },
                                    colors = ButtonDefaults.outlinedButtonColors(
                                        containerColor = if (step == i) Purple else Color.Transparent,
                                        contentColor = Color.White
                                    )
                                ) { Text(label) }
                            }
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                        if (isTablet && step != 1) {
                            // Tablet: lista + conferência lado a lado.
                            Row(modifier = Modifier.weight(1f)) {
                                Column(modifier = Modifier.weight(1f).padding(end = 8.dp)) {
                                    PastaPane(
                                        folderName = folderName, files = files,
                                        onPick = { pickFolder.launch(null) }
                                    )
                                }
                                Column(modifier = Modifier.weight(1f)) {
                                    ConferirPane(
                                        plan = plan, conflicts = conflicts,
                                        renaming = renaming, undoAvailable = undoAvailable,
                                        status = status,
                                        onRename = { doRename() }, onUndo = { doUndo() }
                                    )
                                }
                            }
                        } else {
                            Column(modifier = Modifier.weight(1f)) {
                                when (step) {
                                    0 -> PastaPane(
                                        folderName = folderName, files = files,
                                        onPick = { pickFolder.launch(null) }
                                    )
                                    1 -> RegrasPane(
                                        settings = settings,
                                        presetIndex = presetIndex,
                                        onPreset = { i ->
                                            val preset = Presets.ALL[i]
                                            if (patternCustom && settings.pattern != preset.settings.pattern) {
                                                // O usuário digitou o próprio padrão: não apaga
                                                // sem ele confirmar, como o Windows faz.
                                                pendingPreset = i
                                            } else {
                                                presetIndex = i
                                                settings = preset.settings
                                                status = "Preset “${preset.nome}” aplicado."
                                            }
                                        },
                                        onSettings = { new ->
                                            if (new.pattern != settings.pattern) patternCustom = true
                                            settings = new
                                        }
                                    )
                                    else -> ConferirPane(
                                        plan = plan, conflicts = conflicts,
                                        renaming = renaming, undoAvailable = undoAvailable,
                                        status = status,
                                        onRename = { doRename() }, onUndo = { doUndo() }
                                    )
                                }
                            }
                        }
                        if (status.isNotEmpty()) {
                            Text(status, modifier = Modifier.padding(top = 8.dp))
                        }
                    }
                }
            }
        }
    }

    @Composable
    fun PastaPane(folderName: String, files: List<DocumentFile>, onPick: () -> Unit) {
        Column(modifier = Modifier.fillMaxSize()) {
            Button(onClick = onPick, colors = ButtonDefaults.buttonColors(containerColor = Purple)) {
                Text("Escolher pasta")
            }
            Spacer(modifier = Modifier.height(8.dp))
            Text(if (folderName.isEmpty()) "Nenhuma pasta escolhida. O app só renomeia dentro da pasta autorizada." else "Pasta: $folderName — ${files.size} arquivo(s)")
            Spacer(modifier = Modifier.height(8.dp))
            LazyColumn(modifier = Modifier.weight(1f)) {
                items(files) { f ->
                    val kind = RenameEngine.classify(f.name ?: "")
                    Text(
                        "${f.name}  ·  $kind",
                        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
                    )
                }
            }
        }
    }

    @Composable
    fun RegrasPane(
        settings: RenameEngine.Settings,
        presetIndex: Int,
        onPreset: (Int) -> Unit,
        onSettings: (RenameEngine.Settings) -> Unit
    ) {
        val scroll = rememberScrollState()
        Column(modifier = Modifier.fillMaxSize().verticalScroll(scroll)) {
            Text("Preset", fontWeight = FontWeight.Bold)
            // Botão único que abre as opções: a fileira de chips ocupava
            // muita altura no celular e deixava um vão vazio até o campo
            // Padrão. Agora só o preset atual aparece; tocar abre a lista.
            var presetMenuOpen by remember { mutableStateOf(false) }
            OutlinedButton(
                onClick = { presetMenuOpen = true },
                modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp)
            ) {
                Text(Presets.ALL[presetIndex].nome, modifier = Modifier.weight(1f))
                Text("▾")
            }
            if (presetMenuOpen) {
                AlertDialog(
                    onDismissRequest = { presetMenuOpen = false },
                    title = { Text("Escolher preset") },
                    text = {
                        Column {
                            Presets.ALL.forEachIndexed { i, p ->
                                TextButton(
                                    onClick = { presetMenuOpen = false; onPreset(i) },
                                    modifier = Modifier.fillMaxWidth()
                                ) { Text(p.nome, modifier = Modifier.fillMaxWidth()) }
                            }
                        }
                    },
                    confirmButton = {},
                    dismissButton = { TextButton(onClick = { presetMenuOpen = false }) { Text("Cancelar") } }
                )
            }
            OutlinedTextField(
                value = settings.pattern, onValueChange = { onSettings(settings.copy(pattern = it)) },
                label = { Text("Padrão") }, modifier = Modifier.fillMaxWidth()
            )
            Text(Presets.TOKENS_HELP, modifier = Modifier.padding(vertical = 4.dp))
            OutlinedTextField(
                value = settings.evento, onValueChange = { onSettings(settings.copy(evento = it)) },
                label = { Text("Evento") }, modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = settings.cliente, onValueChange = { onSettings(settings.copy(cliente = it)) },
                label = { Text("Cliente") }, modifier = Modifier.fillMaxWidth()
            )
            Row {
                OutlinedTextField(
                    value = settings.tipoFoto, onValueChange = { onSettings(settings.copy(tipoFoto = it)) },
                    label = { Text("Tipo foto") }, modifier = Modifier.weight(1f)
                )
                Spacer(modifier = Modifier.width(8.dp))
                OutlinedTextField(
                    value = settings.tipoVideo, onValueChange = { onSettings(settings.copy(tipoVideo = it)) },
                    label = { Text("Tipo vídeo") }, modifier = Modifier.weight(1f)
                )
            }
            Row {
                OutlinedTextField(
                    value = settings.inicioFotos.toString(),
                    onValueChange = { onSettings(settings.copy(inicioFotos = it.toIntOrNull() ?: 1)) },
                    label = { Text("Início fotos") }, modifier = Modifier.weight(1f)
                )
                Spacer(modifier = Modifier.width(8.dp))
                OutlinedTextField(
                    value = settings.inicioVideos.toString(),
                    onValueChange = { onSettings(settings.copy(inicioVideos = it.toIntOrNull() ?: 1)) },
                    label = { Text("Início vídeos") }, modifier = Modifier.weight(1f)
                )
            }
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Checkbox(checked = settings.maiusculas, onCheckedChange = { onSettings(settings.copy(maiusculas = it)) })
                Text("MAIÚSCULAS")
                Spacer(modifier = Modifier.width(16.dp))
                Checkbox(checked = settings.substituirEspacos, onCheckedChange = { onSettings(settings.copy(substituirEspacos = it)) })
                Text("Espaços → _")
            }
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Checkbox(checked = settings.parearRawJpg, onCheckedChange = { onSettings(settings.copy(parearRawJpg = it)) })
                Text("Parear JPG+RAW (mesmo número)")
            }
            Text("Preview obrigatório: nada renomeia sem você conferir na etapa 3. Conflitos bloqueiam o lote. Nunca sobrescreve.", modifier = Modifier.padding(top = 8.dp))
        }
    }

    @Composable
    fun ConferirPane(
        plan: List<RenameEngine.PlanEntry>,
        conflicts: Int,
        renaming: Boolean,
        undoAvailable: Boolean,
        status: String,
        onRename: () -> Unit,
        onUndo: () -> Unit
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            if (plan.isEmpty()) {
                Text("Escolha uma pasta na etapa 1 para ver o preview aqui.")
                return@Column
            }
            Text(
                if (conflicts > 0) "$conflicts conflito(s) — resolva ou retire os arquivos antes de renomear."
                else "${plan.size} arquivo(s), sem conflitos. Pronto para renomear.",
                color = if (conflicts > 0) Color(0xFFFF6B6B) else Color(0xFF7CFC9A),
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(8.dp))
            LazyColumn(modifier = Modifier.weight(1f)) {
                items(plan) { e ->
                    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                        Text(e.originalName)
                        Text(
                            "→ " + if (e.error != null) "ERRO: ${e.error}"
                            else if (e.noChange) "Sem alteração"
                            else e.newName,
                            color = when {
                                e.error != null -> Color(0xFFFF6B6B)
                                e.noChange -> Color.Gray
                                else -> Color.White
                            }
                        )
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = onRename,
                    enabled = !renaming && conflicts == 0,
                    colors = ButtonDefaults.buttonColors(containerColor = Purple),
                    modifier = Modifier.weight(1f)
                ) { Text(if (renaming) "Renomeando…" else "Renomear") }
                OutlinedButton(
                    onClick = onUndo,
                    enabled = !renaming && undoAvailable
                ) { Text("Desfazer") }
            }
        }
    }
}
