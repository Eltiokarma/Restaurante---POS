import type { DatosLocal, OrdenOut } from '../api'
import { soles } from '../api'

interface Props {
  orden: OrdenOut
  local: DatosLocal
}

/**
 * Ticket imprimible (~80mm de ancho). El CSS @media print oculta el resto
 * de la UI y deja solo este bloque; window.print() se dispara desde la
 * página Cliente al confirmarse la orden.
 */
export function Ticket({ orden, local }: Props) {
  const numero = String(orden.numero_orden_dia).padStart(3, '0')
  return (
    <div id="ticket-print" className="ticket">
      <div className="ticket-cabecera">
        <div className="ticket-local">{local.nombre}</div>
        {local.direccion && <div>{local.direccion}</div>}
        {local.ruc && <div>RUC: {local.ruc}</div>}
      </div>
      <div className="ticket-orden">ORDEN #{numero}</div>
      {orden.tipo_servicio !== 'sala' && (
        <div className="ticket-servicio">
          {orden.tipo_servicio === 'llevar' ? '🛍 PARA LLEVAR' : '🥡 MIXTO — parte para llevar'}
        </div>
      )}
      <div className="ticket-fecha">
        {orden.fecha} — {orden.hora}
      </div>
      <hr />
      <table className="ticket-items">
        <tbody>
          {orden.items.map((item, i) => (
            <tr key={i}>
              <td>
                {item.cantidad} × {item.nombre}
                {item.empaque !== 'mesa' && (
                  <span className="ticket-item-empaque"> [{item.empaque.toUpperCase()}]</span>
                )}
              </td>
              <td className="ticket-subtotal">{soles(item.subtotal)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <hr />
      <div className="ticket-total">
        <span>TOTAL</span>
        <span>{soles(orden.total)}</span>
      </div>
      <div className="ticket-pie">Paga en caja con este ticket. ¡Gracias!</div>
    </div>
  )
}
