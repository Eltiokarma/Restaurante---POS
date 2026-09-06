import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { DatosLocal, OrdenOut, TicketBebidaOut } from '../api'
import { Ticket, TicketBebidaImpreso } from '../components/Ticket'

interface TrabajoImpresion {
  tipo: 'orden' | 'prueba' | 'cierre' | 'bebida'
  orden_id: number | null
  ticket_bebida_id?: number
  numero: string
  datos_b64: string
}

/**
 * Estación de impresión. Dos formas de atender la cola:
 *
 * - Modo "estacion": se abre en la PC que tiene la impresora instalada
 *   (Chrome con --kiosk-printing para imprimir sin diálogo) y usa
 *   window.print() con el ticket HTML.
 * - Modo "puente": la cola viene en bytes ESC/POS. La puede atender el
 *   puente del local (scripts/puente_impresion.py en una PC) O ESTA MISMA
 *   PÁGINA abierta en una tablet Android con la app RawBT instalada:
 *   cada ticket se le pasa a RawBT (rawbt:base64,...) y RawBT lo manda a
 *   la impresora de red. Cero PC.
 */
export function Ticketera() {
  const [ticket, setTicket] = useState<{ orden: OrdenOut; local: DatosLocal } | null>(null)
  const [enCola, setEnCola] = useState(0)
  const [impresos, setImpresos] = useState(0)
  const [conectado, setConectado] = useState(true)
  // 'cargando' hasta saber el modo real: si la estación arrancara antes de
  // tiempo podría marcar tickets como impresos sin imprimirlos
  const [modo, setModo] = useState<'cargando' | 'estacion' | 'puente'>('cargando')
  const modoPuente = modo === 'puente'
  // Impresión por RawBT desde esta tablet (modo puente sin PC)
  const [rawbtActivo, setRawbtActivo] = useState(false)
  const [pendienteManual, setPendienteManual] = useState<TrabajoImpresion | null>(null)
  const procesando = useRef(false)

  useEffect(() => {
    api.config()
      .then((c) => setModo(c.modo_impresion === 'puente' ? 'puente' : 'estacion'))
      .catch(() => setModo('estacion')) // sin config: comportamiento clásico
  }, [])

  // ---------- Modo estación: window.print() de la orden más antigua ----------

  // Ticket chico de gaseosas pendiente (modo estación, HTML)
  const [ticketBebida, setTicketBebida] = useState<{ ticket: TicketBebidaOut; local: DatosLocal } | null>(null)

  useEffect(() => {
    const revisar = async () => {
      if (procesando.current || modo !== 'estacion') return
      try {
        const data = await api.pendientesImpresion()
        setConectado(true)
        const bebidasPendientes = data.tickets_bebida ?? []
        setEnCola(data.ordenes.length + bebidasPendientes.length)
        if (data.ordenes.length > 0) {
          procesando.current = true
          setTicket({ orden: data.ordenes[0], local: data.local })
        } else if (bebidasPendientes.length > 0) {
          procesando.current = true
          setTicketBebida({ ticket: bebidasPendientes[0], local: data.local })
        }
      } catch {
        setConectado(false)
      }
    }
    revisar()
    const intervalo = window.setInterval(revisar, 3_000)
    return () => window.clearInterval(intervalo)
  }, [modo])

  // Imprime el ticket de gaseosas montado y lo confirma (misma mecánica)
  useEffect(() => {
    if (!ticketBebida) return
    const timer = window.setTimeout(async () => {
      window.print()
      if (ticketBebida.ticket.id !== undefined) {
        try {
          await api.confirmarBebidaImpresa(ticketBebida.ticket.id)
          setImpresos((n) => n + 1)
          setEnCola((n) => Math.max(0, n - 1))
        } catch {
          // Si no se pudo confirmar, el siguiente ciclo lo reintenta
        }
      }
      setTicketBebida(null)
      procesando.current = false
    }, 200)
    return () => window.clearTimeout(timer)
  }, [ticketBebida])

  // Imprime cuando el ticket ya está montado y lo saca de la cola
  useEffect(() => {
    if (!ticket) return
    const timer = window.setTimeout(async () => {
      window.print()
      try {
        await api.marcarImpreso(ticket.orden.id)
        setImpresos((n) => n + 1)
        setEnCola((n) => Math.max(0, n - 1))
      } catch {
        // Si no se pudo marcar, el siguiente ciclo la reintenta
      }
      setTicket(null)
      procesando.current = false
    }, 200)
    return () => window.clearTimeout(timer)
  }, [ticket])

  // ---------- Modo puente: esta tablet imprime con RawBT ----------

  // Le pasa el ticket a la app RawBT y detecta si lo tomó: al abrirse
  // RawBT, esta página pasa a segundo plano (visibilitychange). Si en 4
  // segundos no pasó nada (navegador que bloquea el lanzamiento
  // automático), se ofrece el botón manual.
  // Lanza por un iframe oculto, NUNCA navegando la página: una navegación
  // a rawbt: que el navegador bloquea deja la pestaña "colgada" y se traga
  // los siguientes toques. El iframe falla inofensivo si RawBT no está.
  const marcoRawbt = useRef<HTMLIFrameElement | null>(null)
  const lanzarRawbt = (trabajo: TrabajoImpresion) => {
    if (!marcoRawbt.current) {
      const marco = document.createElement('iframe')
      marco.style.display = 'none'
      document.body.appendChild(marco)
      marcoRawbt.current = marco
    }
    marcoRawbt.current.src = `rawbt:base64,${trabajo.datos_b64}`
  }

  const lanzarYDetectar = (trabajo: TrabajoImpresion) =>
    new Promise<boolean>((resolver) => {
      let resuelto = false
      const terminar = (ok: boolean) => {
        if (resuelto) return
        resuelto = true
        document.removeEventListener('visibilitychange', alOcultarse)
        resolver(ok)
      }
      const alOcultarse = () => {
        if (document.hidden) terminar(true)
      }
      document.addEventListener('visibilitychange', alOcultarse)
      lanzarRawbt(trabajo)
      window.setTimeout(() => terminar(false), 4_000)
    })

  // Órdenes cuya confirmación está en camino: la cola del servidor las
  // seguiría devolviendo un ciclo más y se imprimirían doble
  const confirmando = useRef<Set<number>>(new Set())

  const confirmarImpreso = async (trabajo: TrabajoImpresion) => {
    if (trabajo.tipo === 'orden' && trabajo.orden_id !== null) {
      confirmando.current.add(trabajo.orden_id)
      try {
        await api.marcarImpreso(trabajo.orden_id)
      } catch {
        // No llegó la confirmación: se libera para que la cola lo reintente
        confirmando.current.delete(trabajo.orden_id)
      }
    } else if (trabajo.tipo === 'prueba') {
      // El ticket de prueba también espera en cola hasta confirmarse
      await api.confirmarPruebaImpresa().catch(() => {})
    } else if (trabajo.tipo === 'cierre') {
      // El resumen de cierre de caja: misma mecánica que la prueba
      await api.confirmarCierreImpreso().catch(() => {})
    } else if (trabajo.tipo === 'bebida' && trabajo.ticket_bebida_id !== undefined) {
      // El ticket chico de gaseosas también espera hasta confirmarse
      await api.confirmarBebidaImpresa(trabajo.ticket_bebida_id).catch(() => {})
    }
    setImpresos((n) => n + 1)
    setEnCola((n) => Math.max(0, n - 1))
  }

  const procesandoRawbt = useRef(false)
  useEffect(() => {
    if (!modoPuente || !rawbtActivo) return
    const revisar = async () => {
      if (procesandoRawbt.current || pendienteManual) return
      procesandoRawbt.current = true
      try {
        const cola = await api.colaImpresion()
        setConectado(true)
        setEnCola(cola.trabajos.length)
        // Olvidar los ids que el servidor ya dejó de ofrecer: si no, una
        // reimpresión desde caja quedaría filtrada para siempre
        const idsEnCola = new Set(cola.trabajos.map((t) => t.orden_id))
        for (const id of [...confirmando.current]) {
          if (!idsEnCola.has(id)) confirmando.current.delete(id)
        }
        const trabajo = cola.trabajos.find(
          (t) => t.orden_id === null || !confirmando.current.has(t.orden_id),
        )
        if (trabajo) {
          const ok = await lanzarYDetectar(trabajo)
          if (ok) {
            await confirmarImpreso(trabajo)
          } else {
            // El navegador pidió un toque: botón manual (y se pausa la cola)
            setPendienteManual(trabajo)
          }
        }
      } catch {
        setConectado(false)
      } finally {
        procesandoRawbt.current = false
      }
    }
    revisar()
    const intervalo = window.setInterval(revisar, 3_000)
    return () => window.clearInterval(intervalo)
  }, [modoPuente, rawbtActivo, pendienteManual])

  // El botón manual es un ENLACE real a rawbt: — un toque de verdad es la
  // forma más confiable de que Android abra la app; el estado se actualiza
  // en el onClick sin frenar la navegación del enlace
  const imprimirManual = () => {
    if (!pendienteManual) return
    const trabajo = pendienteManual
    setPendienteManual(null)
    void confirmarImpreso(trabajo)
  }

  const descartar = async () => {
    try {
      const { descartadas } = await api.descartarPendientes()
      setEnCola(0)
      alert(`${descartadas} ticket(s) descartados sin imprimir.`)
    } catch {
      alert('No se pudo descartar la cola, revisa la conexión.')
    }
  }

  return (
    <div className="pantalla-ticketera">
      <h1>🖨️ Estación de impresión</h1>

      {modoPuente && (
        <div className="rawbt-panel">
          <h2>Imprimir desde esta tablet (sin PC)</h2>
          <p className="nota-admin">
            Instala la app gratuita <strong>RawBT</strong> (Play Store) en esta tablet y
            configúrale tu impresora una sola vez: en RawBT → Ajustes → Conexión elige
            <strong> Ethernet/Wi-Fi</strong>, pon la IP de la impresora y prueba desde la
            propia app. Después activa aquí abajo y deja esta pestaña abierta. Si el
            navegador pregunta con qué abrir, elige RawBT y marca <strong>"recordar"</strong>;
            si pide un toque por ticket, aparece un botón grande — tócalo y sale.
          </p>
          {!rawbtActivo ? (
            <button className="boton-grande boton-confirmar" onClick={() => setRawbtActivo(true)}>
              ▶ ACTIVAR IMPRESIÓN EN ESTA TABLET
            </button>
          ) : (
            <button className="boton-grande boton-secundario" onClick={() => setRawbtActivo(false)}>
              ⏸ Pausar impresión en esta tablet
            </button>
          )}
          {pendienteManual && (
            <a
              className="boton-grande boton-confirmar boton-imprimir-manual"
              href={`rawbt:base64,${pendienteManual.datos_b64}`}
              onClick={imprimirManual}
            >
              🖨 TOCA PARA IMPRIMIR #{pendienteManual.numero}
            </a>
          )}
          <p className="nota-admin">
            Si el sistema corre también el puente en una PC, no actives esto a la vez: los
            tickets saldrían por los dos lados. ¿No sale nada al tocar? Revisa que RawBT
            esté instalada y su impresión de prueba interna funcione.
          </p>
        </div>
      )}

      <div className={`ticketera-estado ${conectado ? '' : 'sin-conexion'}`}>
        {!conectado
          ? 'Sin conexión con el sistema…'
          : modoPuente
            ? rawbtActivo
              ? enCola > 0
                ? `Imprimiendo… (${enCola} en cola)`
                : 'Esperando pedidos…'
              : 'Cola en modo puente: actívala arriba o usa el puente de la PC'
            : ticket
              ? `Imprimiendo orden #${String(ticket.orden.numero_orden_dia).padStart(3, '0')}…`
              : 'Esperando pedidos…'}
      </div>
      <div className="ticketera-datos">
        <span>En cola: <strong>{enCola}</strong></span>
        <span>Impresos en esta sesión: <strong>{impresos}</strong></span>
      </div>
      {!modoPuente && (
        <p className="nota-admin">
          Deja esta ventana abierta en la computadora que tiene la impresora conectada.
          Para imprimir sin diálogo, abre Chrome con <code>--kiosk-printing</code>.
        </p>
      )}
      {enCola > 0 && (
        <button className="boton-grande boton-secundario" onClick={descartar}>
          Descartar {enCola} pendiente(s) sin imprimir
        </button>
      )}
      {ticket && (
        <div className="solo-impresion">
          <Ticket orden={ticket.orden} local={ticket.local} />
        </div>
      )}
      {ticketBebida && (
        <div className="solo-impresion">
          <TicketBebidaImpreso ticket={ticketBebida.ticket} local={ticketBebida.local} />
        </div>
      )}
    </div>
  )
}
