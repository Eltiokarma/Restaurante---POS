import type { StockPlato } from '../api'

/** Cuántos quedan hoy de las entradas y segundos (los pone la caja).
 *  Chico y con la paleta de la terminal; en ámbar si quedan pocos y en
 *  rojo con ⚠ si ya no hay: es AVISO, la venta nunca se bloquea (el
 *  conteo puede estar mal). Sin platos contados no se muestra nada. */
export function StockHoy({ stock }: { stock: StockPlato[] }) {
  const contados = stock.filter((s) => s.quedan !== null)
  if (contados.length === 0) return null
  return (
    <div className="stock-hoy" aria-label="Cuántos quedan hoy">
      <span className="stock-hoy-titulo">Quedan</span>
      {contados.map((s) => {
        const quedan = s.quedan ?? 0
        const nivel = quedan <= 0 ? 'stock-agotado' : quedan <= 3 ? 'stock-poco' : ''
        return (
          <span key={s.plato_id} className={`stock-chip ${nivel}`}>
            {s.nombre} <strong>{quedan <= 0 ? `⚠ ${quedan}` : quedan}</strong>
          </span>
        )
      })}
    </div>
  )
}
