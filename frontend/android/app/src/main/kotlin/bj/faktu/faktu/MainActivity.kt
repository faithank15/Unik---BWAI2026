package bj.faktu.faktu

import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

// Le choix d un fichier CSV (l import du portefeuille), par le selecteur de fichiers d Android :
// aucune permission a demander, et pas de paquet en plus.
class MainActivity : FlutterActivity() {
    private var enAttente: MethodChannel.Result? = null

    override fun configureFlutterEngine(moteur: FlutterEngine) {
        super.configureFlutterEngine(moteur)
        MethodChannel(moteur.dartExecutor.binaryMessenger, "bj.faktu/fichiers").setMethodCallHandler { appel, resultat ->
            if (appel.method != "choisirCsv") return@setMethodCallHandler resultat.notImplemented()
            enAttente?.success(null)
            enAttente = resultat
            val intention = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "*/*"
                putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("text/csv", "text/comma-separated-values", "text/plain", "application/vnd.ms-excel"))
            }
            startActivityForResult(intention, CHOIX)
        }
    }

    @Deprecated("Remplace par l API Activity Result, inutile ici")
    override fun onActivityResult(code: Int, retour: Int, donnees: Intent?) {
        super.onActivityResult(code, retour, donnees)
        if (code != CHOIX) return
        val resultat = enAttente ?: return
        enAttente = null
        // Un ou plusieurs fichiers (un lot : clients.csv, factures.csv, echeances.csv…).
        val uris = mutableListOf<Uri>()
        donnees?.clipData?.let { c -> for (i in 0 until c.itemCount) uris.add(c.getItemAt(i).uri) }
        if (uris.isEmpty()) donnees?.data?.let { uris.add(it) }
        if (uris.isEmpty()) return resultat.success(null)
        try {
            val fichiers = uris.mapNotNull { uri ->
                contentResolver.openInputStream(uri)?.use { mapOf("nom" to nomDe(uri), "octets" to it.readBytes()) }
            }
            resultat.success(fichiers)
        } catch (e: Exception) {
            resultat.error("lecture", e.message, null)
        }
    }

    private fun nomDe(uri: Uri): String {
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) return c.getString(0) ?: "portefeuille.csv"
        }
        return "portefeuille.csv"
    }

    companion object {
        private const val CHOIX = 4207
    }
}
