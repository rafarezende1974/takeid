package br.com.dxlabs.dxrename

import android.content.Context
import android.net.Uri
import android.provider.MediaStore
import androidx.documentfile.provider.DocumentFile
import androidx.exifinterface.media.ExifInterface
import java.text.SimpleDateFormat
import java.util.Locale

/**
 * Acesso a arquivos via SAF (Storage Access Framework).
 * Só renomeia dentro da pasta autorizada pelo seletor do sistema.
 * Após renomear, avisa o MediaStore para a Galeria ver os nomes novos.
 */
object SafFiles {

    /** Lista os arquivos (não pastas) de uma pasta SAF, ordenados por nome. */
    fun listFiles(context: Context, treeUri: Uri): List<DocumentFile> {
        val root = DocumentFile.fromTreeUri(context, treeUri) ?: return emptyList()
        return root.listFiles()
            .filter { it.isFile && it.name != null }
            .sortedBy { it.name!!.lowercase(Locale.ROOT) }
    }

    /** Lê a data da foto (EXIF) de um arquivo SAF, se houver. */
    fun photoDateMillis(context: Context, file: DocumentFile): Pair<Long?, Boolean> {
        return try {
            context.contentResolver.openInputStream(file.uri)?.use { input ->
                val exif = ExifInterface(input)
                val raw = exif.getAttribute(ExifInterface.TAG_DATETIME_ORIGINAL)
                    ?: exif.getAttribute(ExifInterface.TAG_DATETIME)
                    ?: return null to false
                val fmt = SimpleDateFormat("yyyy:MM:dd HH:mm:ss", Locale.getDefault())
                val parsed = try { fmt.parse(raw)?.time } catch (_: Exception) { null }
                parsed to (parsed != null)
            } ?: (null to false)
        } catch (_: Exception) {
            null to false
        }
    }

    fun toInputFile(
        context: Context,
        file: DocumentFile,
        parentName: String
    ): RenameEngine.InputFile {
        val (photoDate, hasExif) = photoDateMillis(context, file)
        return RenameEngine.InputFile(
            name = file.name ?: "sem-nome",
            parentName = parentName,
            lastModifiedMillis = file.lastModified(),
            photoDateMillis = photoDate,
            hasExif = hasExif
        )
    }

    /** Renomeia um arquivo SAF para [newName] na mesma pasta. */
    fun renameTo(file: DocumentFile, newName: String): Boolean {
        return try { file.renameTo(newName) } catch (_: Exception) { false }
    }

    /** Avisa o MediaStore para a Galeria ver os nomes novos. */
    fun notifyMediaStore(context: Context) {
        try {
            context.contentResolver.notifyChange(
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI, null
            )
            context.contentResolver.notifyChange(
                MediaStore.Video.Media.EXTERNAL_CONTENT_URI, null
            )
        } catch (_: Exception) { }
    }
}
