import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { DatosLocal, OrdenOut } from '../api'
import { Ticket } from '../components/Ticket'

/**
 * Estación de impresión: se abre en la PC/laptop que tiene la impresora
 * conectada (idealmente en Chrome con --kiosk-printing para imprimir sin
 * diálogo). Cuando el sistema está en modo de impresión "estacion", las
 * terminales (tablets) solo toman el pedido y esta página imprime los
 * tickets automáticamente.
 */
export function Ticketera() {
  const [ticket, setTicket] = useState<{ orden: OrdenOut; local: DatosLocal } | null>(null)
  const [enCola, setEnCola] = useState(0)
  const [impresos, setImpresos] = useState(0)
  const [conectado, setConectado] = useState(true)
  const procesando = useRef(false)

  // Polling cada 3 segundos: toma la orden más antigua sin imprimir
  useEffect(() => {
    const revisar = async () => {
      if (procesando.current) return
      try {
        const data = await api.pendientesImpresion()
        setConectado(true)
        setEnCola(data.ordenes.length)
        if (data.ordenes.length > 0) {
          procesando.current = true
          setTicket({ orden: data.ordenes[0], local: data.local })
        }
      } catch {
        setConectado(false)
      }
    }
    revisar()
    const intervalo = window.setInterval(revisar, 3_000)
    return () => window.clearInterval(intervalo)
  }, [])

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
      <div className={`ticketera-estado ${conectado ? '' : 'sin-conexion'}`}>
        {!conectado
          ? 'Sin conexión con el sistema…'
          : ticket
            ? `Imprimiendo orden #${String(ticket.orden.numero_orden_dia).padStart(3, '0')}…`
            : 'Esperando pedidos…'}
      </div>
      <div className="ticketera-datos">
        <span>En cola: <strong>{enCola}</strong></span>
        <span>Impresos en esta sesión: <strong>{impresos}</strong></span>
      </div>
      <p className="nota-admin">
        Deja esta ventana abierta en la computadora que tiene la impresora conectada.
        Para imprimir sin diálogo, abre Chrome con <code>--kiosk-printing</code>.
      </p>
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
    </div>
  )
}
