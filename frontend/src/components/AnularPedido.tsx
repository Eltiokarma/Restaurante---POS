import { useEffect, useState } from 'react'
import { api, soles } from '../api'
import type { DatosLocal, MotivoAnulacion, OrdenOut, TicketBebidaOut } from '../api'
import { TicketBebidaImpreso } from './Ticket'

/**
 * Anular un pedido YA confirmado (pedido del dueño): el cliente se
 * arrepiente justo después, incluso ya pagado, o el pedido salió dos
 * veces. Se elige el motivo, la orden queda ANULADA (no cuenta como venta,
 * cocina ve "no preparar") y sale un mini voucher "ANULADO" que dice si
 * hay que devolver la plata. En modo terminal lo imprime esta pantalla.
 */
export function AnularPedido({ orden, local, onCerrar, onAnulado }: {
  orden: OrdenOut
  local: DatosLocal
  onCerrar: () => void
  onAnulado: () => void
}) {
  const [ocupado, setOcupado] = useState(false)
  const [error, setError] = useState('')
  const [hecho, setHecho] = useState<{ devolver: number; voucher: TicketBebidaOut | null; imprimeAqui: boolean } | null>(null)
  const numero = String(orden.numero_orden_dia).padStart(3, '0')

  const anular = async (motivo: MotivoAnulacion) => {
    if (ocupado) return
    setOcupado(true)
    setError('')
    try {
      const r = await api.anularOrden(orden.id, motivo)
      // En "puente"/"estacion" el voucher sale por la cola de impresión
      setHecho({ devolver: r.devolver, voucher: r.ticket_cambio, imprimeAqui: r.modo_impresion === 'terminal' })
      onAnulado()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo anular, intenta de nuevo')
    } finally {
      setOcupado(false)
    }
  }

  // Modo terminal: el voucher lo imprime esta pantalla
  useEffect(() => {
    if (!hecho?.voucher || !hecho.imprimeAqui) return
    const t = window.setTimeout(() => window.print(), 300)
    return () => window.clearTimeout(t)
  }, [hecho])

  return (
    <div className="modal-fondo" onClick={(e) => { e.stopPropagation(); onCerrar() }}>
      <div className="modal modal-anular" onClick={(e) => e.stopPropagation()}>
        {hecho ? (
          <>
            <h2>🗑 Pedido #{numero} anulado</h2>
            {hecho.devolver > 0 ? (
              <p className="anular-devolver">Ya había pagado: <strong>devuelve {soles(hecho.devolver)}</strong></p>
            ) : (
              <p>No había pagado: no hay nada que devolver.</p>
            )}
            <p className="anular-ayuda">Salió el voucher "ANULADO" y cocina ya no lo prepara.</p>
            <button className="boton-grande boton-confirmar" onClick={onCerrar}>Listo</button>
            {hecho.voucher && hecho.imprimeAqui && (
              <div className="solo-impresion">
                <TicketBebidaImpreso ticket={hecho.voucher} local={local} />
              </div>
            )}
          </>
        ) : (
          <>
            <h2>¿Anular el pedido #{numero}?</h2>
            <p>
              {soles(orden.total)}
              {orden.pago_al_pedir === 'pagado' && ' · ya pagó: hay que devolverle la plata'}
            </p>
            {error && <div className="banner-error">{error}</div>}
            <div className="botones-anular">
              <button className="boton-grande boton-cancelar-rojo" disabled={ocupado} onClick={() => anular('arrepentido')}>
                😕 Se arrepintió
              </button>
              <button className="boton-grande boton-cancelar-rojo" disabled={ocupado} onClick={() => anular('duplicado')}>
                📋 Es duplicado
              </button>
            </div>
            <button className="boton-grande boton-secundario" disabled={ocupado} onClick={onCerrar}>
              No, dejarlo como está
            </button>
          </>
        )}
      </div>
    </div>
  )
}
