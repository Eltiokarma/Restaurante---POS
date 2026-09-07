package pe.fonda.impresora

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.Socket
import java.net.URL

/**
 * El corazón de la app: el mismo trabajo que hacía el puente de PC
 * (scripts/puente_impresion.py), pero como servicio de Android que sigue
 * corriendo con la pantalla apagada y la tablet bloqueada.
 *
 * Cada 3 segundos pide GET /api/print/cola al POS, manda los bytes
 * ESC/POS de cada trabajo a la impresora de red (IP y puerto vienen en la
 * misma respuesta, configurados en Admin → Configuración) y confirma cada
 * ticket en su endpoint. Si la impresora falla, el trabajo queda en cola
 * y se reintenta al siguiente ciclo — nada se pierde.
 */
class ServicioImpresion : Service() {

    companion object {
        const val CANAL = "impresora"
        const val NOTIFICACION_ID = 1
        private const val INTERVALO_MS = 3_000L
        private const val TIMEOUT_HTTP_MS = 15_000
        private const val TIMEOUT_IMPRESORA_MS = 10_000

        fun iniciar(c: Context) {
            val intent = Intent(c, ServicioImpresion::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                c.startForegroundService(intent)
            } else {
                c.startService(intent)
            }
        }
    }

    @Volatile
    private var corriendo = false
    private var hilo: Thread? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null

    // Impresos cuya confirmación al POS falló: no se reimprimen, solo se
    // reintenta confirmar (evita tickets dobles si la nube parpadea)
    private val impresosSinConfirmar = mutableSetOf<String>()

    // Para avisar UNA vez por trabajo de tipo desconocido, sin llenar la bitácora
    private val desconocidosAvisados = mutableSetOf<String>()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        crearCanal()
        val notificacion = construirNotificacion("Esperando tickets…")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICACION_ID, notificacion, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIFICACION_ID, notificacion)
        }

        if (!corriendo) {
            corriendo = true
            tomarLocks()
            Ajustes.marcarActivo(this, true)
            Registro.cambiarEstado("Atendiendo la cola")
            Registro.anotar("🖨 Servicio iniciado — conectado a ${Ajustes.url(this)}")
            hilo = Thread { ciclo() }.also { it.start() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        corriendo = false
        hilo?.interrupt()
        soltarLocks()
        Registro.cambiarEstado("Detenido")
        Registro.anotar("Servicio detenido")
        super.onDestroy()
    }

    // ---------- El ciclo (espejo del puente de PC) ----------

    private fun ciclo() {
        var avisoSinIp = false
        while (corriendo) {
            try {
                val urlBase = Ajustes.url(this)
                if (urlBase.isEmpty()) {
                    Registro.anotar("⚠ Falta la URL del POS: ábrela en la pantalla y guárdala")
                    dormir(); continue
                }

                val cola: JSONObject = try {
                    api(urlBase, "/api/print/cola", "GET")
                } catch (e: RespuestaHttp) {
                    if (e.codigo == 401) {
                        Registro.anotar("✖ El POS rechazó el PIN: revísalo en la pantalla")
                        notificar("PIN rechazado — revisa la configuración")
                    } else {
                        Registro.anotar("… el POS respondió ${e.codigo}; reintento")
                    }
                    dormir(); continue
                } catch (e: Exception) {
                    Registro.anotar("… sin conexión con el POS (${e.message ?: "error"}); reintento")
                    notificar("Sin conexión con el POS — reintentando")
                    dormir(); continue
                }

                val impresora = cola.optJSONObject("impresora") ?: JSONObject()
                val ip = impresora.optString("ip").trim()
                val puerto = if (impresora.optInt("puerto") > 0) impresora.optInt("puerto") else 9100
                val trabajos = cola.optJSONArray("trabajos") ?: JSONArray()

                if (trabajos.length() > 0 && ip.isEmpty()) {
                    if (!avisoSinIp) {
                        Registro.anotar("⚠ Hay tickets en cola pero falta la IP de la impresora (Admin → Configuración)")
                        notificar("Falta la IP de la impresora en el Admin")
                        avisoSinIp = true
                    }
                    dormir(); continue
                }
                avisoSinIp = false
                if (trabajos.length() == 0) notificar("Esperando tickets…")

                for (i in 0 until trabajos.length()) {
                    if (!corriendo) break
                    val trabajo = trabajos.getJSONObject(i)
                    val clave = claveDe(trabajo)
                    val numero = trabajo.optString("numero")

                    if (clave !in impresosSinConfirmar) {
                        val datos = Base64.decode(trabajo.getString("datos_b64"), Base64.DEFAULT)
                        try {
                            imprimir(ip, puerto, datos)
                        } catch (e: Exception) {
                            Registro.anotar("✖ No se pudo imprimir #$numero: ${e.message ?: "error"}")
                            Registro.anotar("  Revisa que la impresora esté prendida y sea $ip:$puerto")
                            notificar("Impresora sin responder ($ip:$puerto)")
                            break // sigue en cola; se reintenta al próximo ciclo
                        }
                        impresosSinConfirmar.add(clave)
                    }

                    // Confirmar en el POS: hasta que llegue, no se reimprime
                    // (la clave lo recuerda) pero se sigue intentando
                    try {
                        api(Ajustes.url(this), rutaDeConfirmacion(trabajo) ?: continue, "POST")
                        impresosSinConfirmar.remove(clave)
                        Registro.anotar("✔ Ticket #$numero impreso")
                        notificar("✔ Último: #$numero")
                    } catch (e: Exception) {
                        Registro.anotar("… #$numero impreso pero sin confirmar al POS; reintento")
                    }
                }
            } catch (e: InterruptedException) {
                break
            } catch (e: Exception) {
                Registro.anotar("✖ Error inesperado: ${e.message ?: e.javaClass.simpleName}")
            }
            if (!dormir()) break
        }
    }

    private fun claveDe(t: JSONObject): String =
        "${t.optString("tipo")}:${t.optInt("orden_id")}:${t.optInt("ticket_bebida_id")}:${t.optString("numero")}"

    /** Cada tipo de trabajo confirma en su endpoint; un tipo desconocido
     *  (de una versión futura del POS) no se imprime para no ciclar. */
    private fun rutaDeConfirmacion(t: JSONObject): String? = when (t.optString("tipo")) {
        "orden" -> "/api/orders/${t.getInt("orden_id")}/printed"
        "bebida" -> "/api/print/bebida/${t.getInt("ticket_bebida_id")}/impresa"
        "cierre" -> "/api/print/cierre/impresa"
        "prueba" -> "/api/print/prueba/impresa"
        else -> {
            if (desconocidosAvisados.add(claveDe(t))) {
                Registro.anotar("⚠ Trabajo de tipo desconocido '${t.optString("tipo")}': actualiza la app")
            }
            null
        }
    }

    private fun dormir(): Boolean = try {
        Thread.sleep(INTERVALO_MS); true
    } catch (e: InterruptedException) {
        false
    }

    // ---------- Red ----------

    private class RespuestaHttp(val codigo: Int) : Exception("HTTP $codigo")

    private fun api(urlBase: String, ruta: String, metodo: String): JSONObject {
        val conexion = URL(urlBase + ruta).openConnection() as HttpURLConnection
        try {
            conexion.requestMethod = metodo
            conexion.connectTimeout = TIMEOUT_HTTP_MS
            conexion.readTimeout = TIMEOUT_HTTP_MS
            val pin = Ajustes.pin(this)
            if (pin.isNotEmpty()) conexion.setRequestProperty("X-Pin-Local", pin)
            if (metodo == "POST") {
                conexion.doOutput = true
                conexion.setRequestProperty("Content-Type", "application/json")
                conexion.outputStream.use { it.write("{}".toByteArray()) }
            }
            val codigo = conexion.responseCode
            if (codigo >= 400) throw RespuestaHttp(codigo)
            val cuerpo = conexion.inputStream.bufferedReader().use { it.readText() }
            return if (cuerpo.isBlank()) JSONObject() else JSONObject(cuerpo)
        } finally {
            conexion.disconnect()
        }
    }

    private fun imprimir(ip: String, puerto: Int, datos: ByteArray) {
        Socket().use { socket ->
            socket.connect(java.net.InetSocketAddress(ip, puerto), TIMEOUT_IMPRESORA_MS)
            socket.soTimeout = TIMEOUT_IMPRESORA_MS
            socket.getOutputStream().apply {
                write(datos)
                flush()
            }
        }
    }

    // ---------- Locks y notificación ----------

    private fun tomarLocks() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "pos:impresora").apply { acquire() }
        val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "pos:impresora").apply { acquire() }
    }

    private fun soltarLocks() {
        wakeLock?.takeIf { it.isHeld }?.release()
        wifiLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
        wifiLock = null
    }

    private fun crearCanal() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val canal = NotificationChannel(
                CANAL, "Impresión de tickets", NotificationManager.IMPORTANCE_LOW
            ).apply { description = "El servicio que manda los tickets a la impresora" }
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                .createNotificationChannel(canal)
        }
    }

    private fun construirNotificacion(texto: String): Notification {
        val abrir = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or
                (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0)
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CANAL)
        } else {
            @Suppress("DEPRECATION") Notification.Builder(this)
        }
        return builder
            .setContentTitle("Impresora del POS")
            .setContentText(texto)
            .setSmallIcon(R.drawable.ic_impresora)
            .setContentIntent(abrir)
            .setOngoing(true)
            .build()
    }

    private fun notificar(texto: String) {
        (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .notify(NOTIFICACION_ID, construirNotificacion(texto))
    }
}
