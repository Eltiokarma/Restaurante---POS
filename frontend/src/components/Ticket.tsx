import { Fragment } from 'react'
import type { CajaEstado, DatosLocal, EgresoOut, OrdenMenuOut, OrdenOut, TicketBebidaOut } from '../api'
import { decideEntrega, esperadoEnCaja, lineaEntrega, soles } from '../api'

/** La marca de entrega de una persona cuando no sale como lo normal (mesa
 *  por tiempos, para llevar todo junto). Igual que la comanda ESC/POS. */
function marcaEntrega(menu: OrdenMenuOut): string {
  const deMesa = menu.items.filter((i) => i.categoria !== 'bebida').every((i) => i.empaque === 'mesa')
  if (deMesa && menu.entrega === 'junto') return ' · JUNTO'
  if (!deMesa && menu.entrega === 'separado') return ' · POR TIEMPOS'
  return ''
}

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
      <div className="ticket-orden">{ticket.titulo ?? 'GASEOSAS'}</div>
      <div className="ticket-servicio">
        Orden #{ticket.numero}
        {ticket.mesas.length > 0 && ` — Mesa ${ticket.mesas.join(' + ')}`}
      </div>
      {ticket.hora && <div className="ticket-fecha">{ticket.hora}</div>}
      <div className="ticket-items">
        {ticket.items.map((item, i) => (
          <div className="ticket-item" key={i}>
            <span>{item.cantidad} × {item.nombre}</span>
            <span>{item.precio ? soles(item.precio * item.cantidad) : ''}</span>
          </div>
        ))}
      </div>
      {(ticket.titulo ?? 'GASEOSAS') === 'GASEOSAS' ? (
        <>
          <div className="ticket-total">
            <span>TOTAL GASEOSAS</span>
            <span>{soles(ticket.total)}</span>
          </div>
          <div className="ticket-pie">Se suma al ticket de la orden</div>
        </>
      ) : (
        <>
          <div className="ticket-total">
            <span>La cuenta cambia</span>
            <span>{ticket.total >= 0 ? '+' : '−'}{soles(Math.abs(ticket.total))}</span>
          </div>
          {ticket.total_orden !== undefined && (
            <div className="ticket-pie">Nuevo total: {soles(ticket.total_orden)}</div>
          )}
        </>
      )}
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
/** Ticket imprimible. Con `orden.copias` = 2 salen dos comandas iguales,
 *  cada una en su hoja (la segunda es para la guía/mozo). */
export function Ticket({ orden, local }: Props) {
  const copias = Math.max(1, orden.copias ?? 1)
  if (copias === 1) return <TicketCuerpo orden={orden} local={local} id="ticket-print" />
  return (
    <div id="ticket-print" className="ticket-copias">
      {Array.from({ length: copias }, (_, i) => (
        <TicketCuerpo key={i} orden={orden} local={local} />
      ))}
    </div>
  )
}

function TicketCuerpo({ orden, id }: Props & { id?: string }) {
  const numero = String(orden.numero_orden_dia).padStart(3, '0')
  return (
    <div id={id} className="ticket">
      {/* Comanda: sin nombre del local; la orden a la izquierda y la mesa
          a la derecha, en grande (pedido del dueño) */}
      <div className="ticket-orden-mesa">
        <span>ORDEN #{numero}</span>
        <span>
          {orden.mesas.length > 0 ? `MESA ${orden.mesas.join(' + ')}`
            : orden.tipo_servicio === 'llevar' ? 'LLEVAR' : 'SIN MESA'}
        </span>
      </div>
      {orden.pago_al_pedir && (
        <div className="ticket-pago">{orden.pago_al_pedir === 'pagado' ? 'PAGADO' : '** NO PAGÓ **'}</div>
      )}
      {orden.tipo_servicio === 'mixto' && (
        <div className="ticket-servicio">🥡 MIXTO — parte para llevar</div>
      )}
      {orden.items.length + orden.menus.length >= 2 || orden.menus.length > 0 ? (
        <div className="ticket-servicio">
          ENTREGA: {lineaEntrega(orden).texto}
        </div>
      ) : null}
      <hr />
      <table className="ticket-items">
        <tbody>
          {orden.menus.map((menu, m) => (
            <Fragment key={`menu-${m}`}>
              <tr>
                <td>
                  {menu.cantidad} × {menu.nombre}
                  {menu.nombre_persona && <strong> — {menu.nombre_persona.toUpperCase()}</strong>}
                  {/* Entregas mezcladas: solo la excepción (mesa todo junto o
                      llevar por tiempos); "SEPARADO" se leía como reservado */}
                  {decideEntrega(menu) && lineaEntrega(orden).texto.includes('/') && marcaEntrega(menu)}
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
              {/* Lo que falta elegir va en un recuadro grueso: en hora punta
                  una línea más se lee como un plato y se prepara */}
              {(menu.pendientes ?? []).map((rotulo, i) => (
                <tr key={`menu-${m}-pend-${i}`}>
                  <td colSpan={2}>
                    <div className="ticket-falta-elegir">
                      <strong>{menu.cantidad > 1 ? `${menu.cantidad} ` : ''}{rotulo.toUpperCase()}</strong>
                      <span>FALTA ELEGIR</span>
                      {menu.nombre_persona && <span>({menu.nombre_persona.toUpperCase()})</span>}
                    </div>
                  </td>
                </tr>
              ))}
              {/* El refresco del menú no pasa por cocina: no va en la comanda */}
              {menu.items.filter((item) => item.categoria !== 'bebida').map((item, i) => (
                <tr key={`menu-${m}-item-${i}`} className={`ticket-item-tiempo ${item.es_agregado ? 'ticket-item-agregado' : ''}`}>
                  <td>
                    {item.es_agregado ? `** +${item.cantidad} ${item.nombre.toUpperCase()} **`
                      : <>· {item.cantidad} × {item.nombre_corto || item.nombre}</>}
                    {item.es_extra && ' (EXTRA)'}
                    {item.espera && ' (ESPERA)'}
                    {item.empaque !== 'mesa' && (
                      <span className="ticket-item-empaque"> [{item.empaque.toUpperCase()}]</span>
                    )}
                    {item.detalle && <div className="ticket-item-nota">→ {item.detalle}</div>}
                  </td>
                  <td className="ticket-subtotal">{item.subtotal > 0 ? soles(item.subtotal) : ''}</td>
                </tr>
              ))}
            </Fragment>
          ))}
          {orden.items.map((item, i) => (
            <tr key={i}>
              <td>
                {item.cantidad} × {item.nombre_corto || item.nombre}
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
      {/* Sin "¡Gracias!" (es comanda): abajo la fecha y la hora */}
      <div className="ticket-fecha">
        {orden.fecha} — {orden.hora}
      </div>
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
