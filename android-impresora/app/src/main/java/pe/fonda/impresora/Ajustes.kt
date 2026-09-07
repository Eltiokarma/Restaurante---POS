package pe.fonda.impresora

import android.content.Context

/** Configuración persistente: URL del POS, PIN del local y si el
 *  servicio debe estar corriendo (para relanzarlo al prender la tablet). */
object Ajustes {
    private const val PREFS = "ajustes"

    fun url(c: Context): String =
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString("url", "") ?: ""

    fun pin(c: Context): String =
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString("pin", "") ?: ""

    fun activo(c: Context): Boolean =
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean("activo", false)

    fun guardar(c: Context, url: String, pin: String) {
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString("url", url.trim().trimEnd('/'))
            .putString("pin", pin.trim())
            .apply()
    }

    fun marcarActivo(c: Context, valor: Boolean) {
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putBoolean("activo", valor).apply()
    }
}
