package pe.fonda.impresora

import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast

/**
 * Pantalla única de configuración: URL del POS + PIN del local, botón
 * grande INICIAR/DETENER y la bitácora de lo que va saliendo. Pensada
 * para tocarse una vez y no volver: el servicio queda corriendo solo.
 */
class MainActivity : Activity() {

    private lateinit var campoUrl: EditText
    private lateinit var campoPin: EditText
    private lateinit var botonServicio: Button
    private lateinit var botonBateria: Button
    private lateinit var vistaEstado: TextView
    private lateinit var vistaBitacora: TextView

    private val reloj = Handler(Looper.getMainLooper())
    private val refrescar = object : Runnable {
        override fun run() {
            pintarEstado()
            reloj.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        campoUrl = findViewById(R.id.campo_url)
        campoPin = findViewById(R.id.campo_pin)
        botonServicio = findViewById(R.id.boton_servicio)
        botonBateria = findViewById(R.id.boton_bateria)
        vistaEstado = findViewById(R.id.vista_estado)
        vistaBitacora = findViewById(R.id.vista_bitacora)

        campoUrl.setText(Ajustes.url(this))
        campoPin.setText(Ajustes.pin(this))

        botonServicio.setOnClickListener { alternarServicio() }
        botonBateria.setOnClickListener { pedirIgnorarBateria() }
    }

    override fun onResume() {
        super.onResume()
        reloj.post(refrescar)
    }

    override fun onPause() {
        reloj.removeCallbacks(refrescar)
        super.onPause()
    }

    private fun alternarServicio() {
        if (Ajustes.activo(this)) {
            Ajustes.marcarActivo(this, false)
            stopService(Intent(this, ServicioImpresion::class.java))
            pintarEstado()
            return
        }
        val url = campoUrl.text.toString().trim()
        if (!url.startsWith("http")) {
            Toast.makeText(this, "Pon la dirección del POS (empieza con http)", Toast.LENGTH_LONG).show()
            return
        }
        Ajustes.guardar(this, url, campoPin.text.toString())
        pedirPermisoNotificaciones()
        ServicioImpresion.iniciar(this)
        Toast.makeText(this, "Listo: la tablet atiende la impresora aunque se bloquee", Toast.LENGTH_LONG).show()
        pintarEstado()
    }

    private fun pintarEstado() {
        val activo = Ajustes.activo(this)
        botonServicio.text = if (activo) "⏹ DETENER" else "▶ INICIAR"
        vistaEstado.text = "Estado: ${Registro.estado}"
        vistaBitacora.text = Registro.texto().ifEmpty { "Aquí se verá cada ticket que salga." }
        campoUrl.isEnabled = !activo
        campoPin.isEnabled = !activo

        val pm = getSystemService(POWER_SERVICE) as PowerManager
        val exento = Build.VERSION.SDK_INT < Build.VERSION_CODES.M ||
            pm.isIgnoringBatteryOptimizations(packageName)
        botonBateria.text = if (exento) "✔ La batería no la apagará" else "🔋 Permitir correr con pantalla apagada"
        botonBateria.isEnabled = !exento
    }

    /** Sin esto, algunos Android matan el servicio al rato de bloquear la
     *  tablet. Se pide UNA vez y queda. */
    private fun pedirIgnorarBateria() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return
        val intent = Intent(
            Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
            Uri.parse("package:$packageName")
        )
        try {
            startActivity(intent)
        } catch (e: Exception) {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }
    }

    private fun pedirPermisoNotificaciones() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 1)
        }
    }
}
