import { Fragment } from 'react'
import type { CajaEstado, DatosLocal, EgresoOut, OrdenOut, TicketBebidaOut } from '../api'
import { esperadoEnCaja, soles } from '../api'

/**
 * Ticket chico de SOLO las gaseosas agregadas a una orden desde caja:
 * no se reimprime la comanda completa, sale este comprobante aparte.
 */
export function TicketBebidaImpreso({ ticket, local }: {
  ticket: TicketBebidaOut
  local: DatosLocal
}) {
  return (
    <div id="ticket-print" className="ticket">
      <div className="ticket-cabecera">
        <div className="ticket-local">{local.nombre}</div>
      </div>
      <div className="ticket-orden">GASEOSAS</div>
      <div className="ticket-servicio">
        Orden #{ticket.numero}
        {ticket.mesas.length > 0 && ` — Mesa ${ticket.mesas.join(' + ')}`}
      </div>
      {ticket.hora && <div className="ticket-fecha">{ticket.hora}</div>}
      <div className="ticket-items">
        {ticket.items.map((item, i) => (
          <div className="ticket-item" key={i}>
            <span>{item.cantidad} × {item.nombre}</span>
            <span>{soles(item.precio * item.cantidad)}</span>
          </div>
        ))}
      </div>
      <div className="ticket-total">
        <span>TOTAL GASEOSAS</span>
        <span>{soles(ticket.total)}</span>
      </div>
      <div className="ticket-pie">Se suma al ticket de la orden</div>
    </div>
  )
}

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
      {orden.mesas.length > 0 ? (
        <div className="ticket-servicio">🪑 MESA: {orden.mesas.join(' + ')}</div>
      ) : orden.tipo_servicio !== 'llevar' ? (
        <div className="ticket-servicio">🪑 SIN MESA</div>
      ) : null}
      {orden.items.length + orden.menus.length >= 2 || orden.menus.length > 0 ? (
        <div className="ticket-servicio ticket-entrega">
          {orden.entrega === 'separado' ? 'ENTREGA: POR TIEMPOS' : 'ENTREGA: TODO JUNTO'}
        </div>
      ) : null}
      <div className="ticket-fecha">
        {orden.fecha} — {orden.hora}
      </div>
      <hr />
      <table className="ticket-items">
        <tbody>
          {orden.menus.map((menu, m) => (
            <Fragment key={`menu-${m}`}>
              <tr>
                <td>
                  {menu.cantidad} × {menu.nombre}
                  {menu.nota && <div className="ticket-item-nota">→ {menu.nota}</div>}
                </td>
                <td className="ticket-subtotal">
                  {soles((menu.precio - menu.omitidos.reduce((s, o) => s + o.descuento, 0)) * menu.cantidad)}
                </td>
              </tr>
              {menu.omitidos.map((o, i) => (
                <tr key={`menu-${m}-sin-${i}`} className="ticket-item-tiempo ticket-item-sin">
                  <td>** SIN {o.rotulo.toUpperCase()} **</td>
                  <td className="ticket-subtotal">
                    {o.descuento > 0 ? `−${soles(o.descuento * menu.cantidad)}` : ''}
                  </td>
                </tr>
              ))}
              {menu.items.map((item, i) => (
                <tr key={`menu-${m}-item-${i}`} className={`ticket-item-tiempo ${item.es_agregado ? 'ticket-item-agregado' : ''}`}>
                  <td>
                    {item.es_agregado ? `** +${item.cantidad} ${item.nombre.toUpperCase()} **`
                      : <>· {item.cantidad} × {item.nombre}</>}
                    {item.es_extra && ' (EXTRA)'}
                    {item.empaque !== 'mesa' && (
                      <span className="ticket-item-empaque"> [{item.empaque.toUpperCase()}]</span>
                    )}
                  </td>
                  <td className="ticket-subtotal">{item.subtotal > 0 ? soles(item.subtotal) : ''}</td>
                </tr>
              ))}
            </Fragment>
          ))}
          {orden.items.map((item, i) => (
            <tr key={i}>
              <td>
                {item.cantidad} × {item.nombre}
                {item.empaque !== 'mesa' && (
                  <span className="ticket-item-empaque"> [{item.empaque.toUpperCase()}]</span>
                )}
                {item.nota && <div className="ticket-item-nota">→ {item.nota}</div>}
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

/**
 * Resumen impreso del cierre de caja (modo terminal/estación: lo imprime
 * la propia pantalla de caja con window.print()).
 */
export function TicketCierre({ estado, egresos, local }: {
  estado: CajaEstado
  egresos: EgresoOut[]
  local: DatosLocal
}) {
  const esperado = esperadoEnCaja(estado)
  const dif = estado.diferencia ?? 0
  return (
    <div id="ticket-print" className="ticket">
      <div className="ticket-cabecera">
        <div className="ticket-local">{local.nombre}</div>
      </div>
      <div className="ticket-orden">CIERRE DE CAJA</div>
      <div className="ticket-fecha">
        {estado.fecha}
        {(estado.turno ?? 1) > 1 && ` — caja ${estado.turno} del día`}
      </div>
      <div className="ticket-fecha">
        Abierta {estado.hora_apertura?.slice(0, 5)} — Cerrada{' '}
        {estado.hora_cierre ? estado.hora_cierre.slice(0, 5) : 'ahora'}
      </div>
      <hr />
      <table className="ticket-items">
        <tbody>
          <tr><td>Fondo inicial</td><td className="ticket-subtotal">{soles(estado.monto_apertura ?? 0)}</td></tr>
          <tr><td>Ventas efectivo</td><td className="ticket-subtotal">{soles(estado.ventas_efectivo)}</td></tr>
          <tr><td>Ventas tarjeta</td><td className="ticket-subtotal">{soles(estado.ventas_tarjeta)}</td></tr>
          <tr><td>Ventas Yape</td><td className="ticket-subtotal">{soles(estado.ventas_yape)}</td></tr>
          <tr><td><strong>TOTAL VENDIDO</strong></td><td className="ticket-subtotal"><strong>{soles(estado.total_vendido)}</strong></td></tr>
        </tbody>
      </table>
      {egresos.length > 0 && (
        <>
          <hr />
          <table className="ticket-items">
            <tbody>
              <tr><td colSpan={2}>EGRESOS (salió del cajón):</td></tr>
              {egresos.map((e) => (
                <tr key={e.id}>
                  <td>· {e.concepto}</td>
                  <td className="ticket-subtotal">−{soles(e.monto)}</td>
                </tr>
              ))}
              <tr><td><strong>TOTAL EGRESOS</strong></td><td className="ticket-subtotal"><strong>−{soles(estado.egresos ?? 0)}</strong></td></tr>
            </tbody>
          </table>
        </>
      )}
      <hr />
      <table className="ticket-items">
        <tbody>
          {(estado.por_cobrar ?? 0) > 0 && (
            <tr><td>Falta pagar (no entró)</td><td className="ticket-subtotal">−{soles(estado.por_cobrar ?? 0)}</td></tr>
          )}
          {(estado.vueltos_pendientes ?? 0) > 0 && (
            <tr><td>Vueltos por dar (de más)</td><td className="ticket-subtotal">+{soles(estado.vueltos_pendientes ?? 0)}</td></tr>
          )}
          <tr><td>Esperado en caja</td><td className="ticket-subtotal">{soles(esperado)}</td></tr>
          <tr><td>Contado</td><td className="ticket-subtotal">{soles(estado.monto_contado ?? 0)}</td></tr>
        </tbody>
      </table>
      <div className="ticket-total">
        <span>{dif === 0 ? 'CUADRÓ' : dif > 0 ? 'SOBRAN' : 'FALTAN'}</span>
        <span>{dif === 0 ? 'EXACTO 🎯' : soles(Math.abs(dif))}</span>
      </div>
    </div>
  )
}
