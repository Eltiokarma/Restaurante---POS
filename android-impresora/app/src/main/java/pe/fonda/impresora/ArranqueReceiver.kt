package pe.fonda.impresora

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Si el servicio estaba corriendo cuando la tablet se apagó, vuelve a
 *  arrancar solo al prenderla: nadie tiene que acordarse de abrir la app. */
class ArranqueReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        if (Ajustes.activo(context) && Ajustes.url(context).isNotEmpty()) {
            ServicioImpresion.iniciar(context)
        }
    }
}
