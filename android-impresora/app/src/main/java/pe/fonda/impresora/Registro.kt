package pe.fonda.impresora

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Bitácora en memoria que la pantalla muestra: las últimas líneas de lo
 *  que el servicio va haciendo ("✔ Ticket #012 impreso", errores, etc.). */
object Registro {
    private const val MAXIMO = 120
    private val lineas = ArrayDeque<String>()
    private val hora = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    @Volatile
    var estado: String = "Detenido"
        private set

    @Synchronized
    fun anotar(mensaje: String) {
        lineas.addFirst("${hora.format(Date())}  $mensaje")
        while (lineas.size > MAXIMO) lineas.removeLast()
    }

    @Synchronized
    fun cambiarEstado(nuevo: String) {
        estado = nuevo
    }

    @Synchronized
    fun texto(): String = lineas.joinToString("\n")
}
