package br.com.dxlabs.dxrename

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files
import java.util.Calendar

/**
 * Testes do motor DX Rename Android — porte dos 14 testes do Windows.
 * O motor é puro (sem Android), então roda como teste unitário JVM.
 * Datas: EXIF simulado via photoDateMillis; sem EXIF usa lastModified.
 */
class RenameEngineTest {

    private fun input(
        name: String,
        parent: String = "",
        photoDate: Long? = null,
        hasExif: Boolean = false,
        lastModified: Long = System.currentTimeMillis()
    ) = RenameEngine.InputFile(name, parent, lastModified, photoDate, hasExif)

    private fun millis(y: Int, m: Int, d: Int): Long {
        val c = Calendar.getInstance()
        c.set(y, m - 1, d, 10, 20, 30)
        c.set(Calendar.MILLISECOND, 0)
        return c.timeInMillis
    }

    @Test
    fun pareamentoJpgRawMesmoNumero() {
        val files = listOf(
            input("DSC001.JPG"), input("DSC001.ARW"),
            input("DSC002.JPG"), input("DSC002.NEF")
        )
        val plan = RenameEngine.buildPlan(files, RenameEngine.Settings())
        assertFalse(RenameEngine.hasConflicts(plan))
        assertEquals(
            listOf(
                "EXPO2026_FOTO_0001.JPG", "EXPO2026_FOTO_0001.ARW",
                "EXPO2026_FOTO_0002.JPG", "EXPO2026_FOTO_0002.NEF"
            ),
            plan.map { it.newName }
        )
    }

    @Test
    fun contadoresSeparadosFotoVideo() {
        val files = listOf(
            input("DSC001.JPG"), input("C0001.MP4"),
            input("DSC002.JPG"), input("C0002.MP4")
        )
        val plan = RenameEngine.buildPlan(files, RenameEngine.Settings())
        assertEquals(
            listOf(
                "EXPO2026_FOTO_0001.JPG", "EXPO2026_TAKE_0001.MP4",
                "EXPO2026_FOTO_0002.JPG", "EXPO2026_TAKE_0002.MP4"
            ),
            plan.map { it.newName }
        )
    }

    @Test
    fun inicio125e20() {
        val files = listOf(input("DSC001.JPG"), input("C0001.MP4"))
        val plan = RenameEngine.buildPlan(
            files,
            RenameEngine.Settings(inicioFotos = 125, inicioVideos = 20)
        )
        assertEquals(
            listOf("EXPO2026_FOTO_0125.JPG", "EXPO2026_TAKE_0020.MP4"),
            plan.map { it.newName }
        )
    }

    @Test
    fun tipoVideoConfiguravel() {
        val plan = RenameEngine.buildPlan(
            listOf(input("C0001.MP4")),
            RenameEngine.Settings(tipoVideo = "VIDEO")
        )
        assertEquals("EXPO2026_VIDEO_0001.MP4", plan[0].newName)
    }

    @Test
    fun conflitoDuplicadoSemSeq() {
        val files = listOf(input("DSC001.JPG"), input("DSC002.JPG"))
        val plan = RenameEngine.buildPlan(
            files, RenameEngine.Settings(pattern = "{evento}_{tipo}")
        )
        assertTrue(RenameEngine.hasConflicts(plan))
        assertTrue(plan.all { it.error?.contains("duplicado") == true })
    }

    @Test
    fun destinoJaExisteForaDoLote() {
        val files = listOf(input("DSC001.JPG"))
        val existing = setOf("expo2026_foto_0001.jpg")
        val plan = RenameEngine.buildPlan(files, RenameEngine.Settings(), existing)
        assertTrue(RenameEngine.hasConflicts(plan))
        assertTrue(plan[0].error?.contains("já existe") == true)
    }

    @Test
    fun nomeInvalidoEReservado() {
        val files = listOf(input("DSC001.JPG"), input("DSC002.JPG"))
        val bad = RenameEngine.buildPlan(
            files, RenameEngine.Settings(pattern = "{evento}:FOTO_{seq:0000}")
        )
        assertTrue(bad[0].error?.contains("inválido") == true)
        val reserved = RenameEngine.buildPlan(
            files, RenameEngine.Settings(pattern = "CON", evento = "")
        )
        assertTrue(reserved[0].error?.contains("reservado") == true)
    }

    @Test
    fun variavelDesconhecidaENomeLongo() {
        val files = listOf(input("DSC001.JPG"))
        val unknown = RenameEngine.buildPlan(
            files, RenameEngine.Settings(pattern = "{evento}_{foo}")
        )
        assertTrue(unknown[0].error?.contains("desconhecida") == true)
        val longPlan = RenameEngine.buildPlan(
            files, RenameEngine.Settings(pattern = "A".repeat(250) + "_{seq:0000}")
        )
        assertTrue(longPlan[0].error?.contains("240") == true)
    }

    @Test
    fun trocaAParaBeBParaA() {
        val dir = Files.createTempDirectory("dxrename").toFile()
        try {
            val aaa = File(dir, "AAA.JPG").apply { writeText("x") }
            val bbb = File(dir, "BBB.JPG").apply { writeText("y") }
            val pairs = listOf(aaa to File(dir, "BBB.JPG"), bbb to File(dir, "AAA.JPG"))
            val (done, errors) = RenameEngine.renameTwoPass(pairs)
            assertEquals(emptyList<String>(), errors)
            assertEquals(2, done.size)
            assertTrue(File(dir, "AAA.JPG").exists())
            assertTrue(File(dir, "BBB.JPG").exists())
        } finally {
            dir.deleteRecursively()
        }
    }

    @Test
    fun aplicarEDesfazerViaTwoPass() {
        val dir = Files.createTempDirectory("dxrename").toFile()
        try {
            val f1 = File(dir, "DSC001.JPG").apply { writeText("x") }
            val f2 = File(dir, "DSC001.ARW").apply { writeText("x") }
            val f3 = File(dir, "C0001.MP4").apply { writeText("x") }
            val plan = RenameEngine.buildPlan(
                listOf(input("DSC001.JPG"), input("DSC001.ARW"), input("C0001.MP4")),
                RenameEngine.Settings()
            )
            val pairs = plan.map { entry ->
                val src = when (entry.originalName) {
                    "DSC001.JPG" -> f1; "DSC001.ARW" -> f2; else -> f3
                }
                src to File(dir, entry.newName)
            }
            val (done, errors) = RenameEngine.renameTwoPass(pairs)
            assertEquals(emptyList<String>(), errors)
            assertEquals(3, done.size)
            assertTrue(File(dir, "EXPO2026_FOTO_0001.JPG").exists())
            // Desfazer: volta os nomes originais.
            val back = done.map { (src, dst) -> dst to src }
            val (undone, errors2) = RenameEngine.renameTwoPass(back)
            assertEquals(emptyList<String>(), errors2)
            assertEquals(3, undone.size)
            assertTrue(File(dir, "DSC001.JPG").exists())
            assertFalse(File(dir, "EXPO2026_FOTO_0001.JPG").exists())
        } finally {
            dir.deleteRecursively()
        }
    }

    @Test
    fun exifLidoEFallbackDataModificacao() {
        val exifDate = millis(2021, 5, 2)
        val plan = RenameEngine.buildPlan(
            listOf(input("COM_EXIF.JPG", photoDate = exifDate, hasExif = true)),
            RenameEngine.Settings(pattern = "{datafoto}_{seq:03}")
        )
        assertEquals("2021-05-02_001.JPG", plan[0].newName)
        // Sem EXIF: usa a data de modificação.
        val modDate = millis(2023, 3, 4)
        val plan2 = RenameEngine.buildPlan(
            listOf(input("SEM_EXIF.JPG", lastModified = modDate)),
            RenameEngine.Settings(pattern = "{datafoto}_{seq:03}")
        )
        assertEquals("2023-03-04_001.JPG", plan2[0].newName)
    }

    @Test
    fun maiusculasEEspacosEOutrosTipos() {
        val files = listOf(input("foto teste.png"), input("DSC001.JPG"))
        val plan = RenameEngine.buildPlan(
            files,
            RenameEngine.Settings(
                pattern = "{evento} {nome} {seq:0000}",
                maiusculas = true, substituirEspacos = true
            )
        )
        assertEquals("EXPO2026_FOTO_TESTE_0001.png", plan[0].newName)
        assertEquals("ARQUIVO", plan[0].tipo)
        assertEquals("EXPO2026_DSC001_0001.JPG", plan[1].newName)
    }

    @Test
    fun semPareamentoCadaArquivoTemNumero() {
        val files = listOf(input("DSC001.JPG"), input("DSC001.ARW"))
        val plan = RenameEngine.buildPlan(
            files, RenameEngine.Settings(parearRawJpg = false)
        )
        assertEquals(
            listOf("EXPO2026_FOTO_0001.JPG", "EXPO2026_FOTO_0002.ARW"),
            plan.map { it.newName }
        )
    }

    @Test
    fun nomeIgualAoAtualNaoBloqueia() {
        val files = listOf(input("EXPO2026_FOTO_0001.JPG"), input("DSC001.JPG"))
        val existing = setOf("expo2026_foto_0001.jpg")
        val plan = RenameEngine.buildPlan(files, RenameEngine.Settings(), existing)
        assertFalse(RenameEngine.hasConflicts(plan))
        assertTrue(plan[0].noChange)
        // Só o segundo renomeia.
        val toRename = plan.filter { it.ok && !it.noChange }
        assertEquals(1, toRename.size)
    }
}
