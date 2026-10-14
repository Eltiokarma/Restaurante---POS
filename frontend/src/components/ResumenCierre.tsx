import { soles } from '../api'
import type { ResumenCierre as Resumen } from '../api'

/**
 * Resumen de la venta al cerrar caja, en pantalla (pedido del dueño): lo
 * mismo que sale impreso — lo vendido con cuánto SOBRA de cada plato, la
 * plata por método y el cuadre del cajón.
 */
export function ResumenCierre({ resumen, onCerrar }: { resumen: Resumen; onCerrar: () => void }) {
  const r = resumen
  const conSobran = r.venta.platos.some((p) => p.sobran !== null)
  const esperado = r.monto_apertura + r.ventas_efectivo - r.egresos_total - r.por_cobrar
    + r.vueltos_pendientes + r.cobrado_de_otros_dias
  const dif = r.diferencia
  return (
    <div className="modal-fondo" onClick={onCerrar}>
      <div className="modal modal-resumen-cierre" onClick={(e) => e.stopPropagation()}>
        <h2>📊 Resumen de la venta</h2>
        <p className="resumen-cierre-sub">
          {r.turnos_del_dia > 1 ? `Caja ${r.turno} · ` : ''}
          {r.hora_apertura.slice(0, 5)} – {r.hora_cierre?.slice(0, 5)}
        </p>

        <div className="resumen-cierre-cifras">
          <div><span>Vendido</span><strong>{soles(r.total_sistema)}</strong></div>
          <div><span>Pedidos</span><strong>{r.venta.pedidos}</strong>
            {r.venta.anulados > 0 && <small>+{r.venta.anulados} anulados</small>}</div>
          <div><span>Menús</span><strong>{r.venta.menus}</strong></div>
        </div>

        {r.venta.platos.length > 0 && (
          <table className="resumen-cierre-platos">
            <thead>
              <tr>
                <th>Plato</th>
                <th>Vendidos</th>
                {conSobran && <th>Sobran</th>}
              </tr>
            </thead>
            <tbody>
              {r.venta.platos.map((p) => (
                <tr key={p.nombre}>
                  <td>{p.nombre}</td>
                  <td className="num">{p.cantidad}</td>
                  {conSobran && (
                    <td className={`num ${p.sobran !== null && p.sobran < 0 ? 'resumen-negativo' : ''}`}>
                      {p.sobran ?? '—'}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <table className="resumen-cierre-plata">
          <tbody>
            <tr><td>Fondo inicial</td><td className="num">{soles(r.monto_apertura)}</td></tr>
            <tr><td>Efectivo</td><td className="num">{soles(r.ventas_efectivo)}</td></tr>
            <tr><td>Yape</td><td className="num">{soles(r.ventas_yape)}</td></tr>
            <tr><td>Tarjeta</td><td className="num">{soles(r.ventas_tarjeta)}</td></tr>
            {r.egresos_total > 0 && <tr><td>Egresos</td><td className="num">−{soles(r.egresos_total)}</td></tr>}
            {r.por_cobrar > 0 && <tr><td>Falta pagar (no entró)</td><td className="num">−{soles(r.por_cobrar)}</td></tr>}
            {r.vueltos_pendientes > 0 && <tr><td>Vueltos por dar</td><td className="num">+{soles(r.vueltos_pendientes)}</td></tr>}
            {r.cobrado_de_otros_dias !== 0 && <tr><td>Cobrado de otros días</td><td className="num">{soles(r.cobrado_de_otros_dias)}</td></tr>}
            <tr className="fila-fuerte"><td>Esperado en caja</td><td className="num">{soles(esperado)}</td></tr>
            <tr className="fila-fuerte"><td>Contado</td><td className="num">{soles(r.monto_contado)}</td></tr>
          </tbody>
        </table>
        <p className={`resumen-cierre-dif ${dif === 0 ? 'exacto' : dif > 0 ? 'sobra' : 'falta'}`}>
          {dif === 0 ? '✔ Cuadró exacto' : dif > 0 ? `Sobran ${soles(dif)}` : `Faltan ${soles(-dif)}`}
        </p>

        <button className="boton-grande boton-confirmar" onClick={onCerrar}>Listo</button>
      </div>
    </div>
  )
}
