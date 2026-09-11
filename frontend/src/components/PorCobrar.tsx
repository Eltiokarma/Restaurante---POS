import { useCallback, useEffect, useState } from 'react'
import { api, soles } from '../api'
import type { OrdenPorCobrar, PorCobrar as PorCobrarDatos } from '../api'

/**
 * Lo que está debiendo, de cualquier día.
 *
 * El dueño lo explicó así: "sin cobrar suele ser un pago futuro que
 * necesita ser levantado desde el sistema". Un ticket puede quedar
 * debiendo el martes y pagarse el jueves; acá se cobra o se da por
 * perdido, y la plata cae en el día correcto sin contar la venta dos
 * veces.
 *
 * `soloOtrosDias` = en la caja del turno solo estorban las deudas
 * viejas: las de hoy ya se ven en su propio ticket.
 */
export function PorCobrar({ soloOtrosDias = false, alCambiar }: {
  soloOtrosDias?: boolean
  alCambiar?: () => void
}) {
  const [datos, setDatos] = useState<PorCobrarDatos | null>(null)
  const [error, setError] = useState('')
  const [ocupado, setOcupado] = useState<number | null>(null)
  const [confirmando, setConfirmando] = useState<number | null>(null)

  const cargar = useCallback(async () => {
    try {
      setDatos(await api.porCobrar())
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cargar lo que está debiendo')
    }
  }, [])

  useEffect(() => { cargar() }, [cargar])

  const hacer = async (id: number, accion: () => Promise<unknown>) => {
    setOcupado(id)
    try {
      await accion()
      await cargar()
      alCambiar?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo registrar')
    } finally {
      setOcupado(null)
      setConfirmando(null)
    }
  }

  if (!datos) return null

  const pendientes = soloOtrosDias
    ? datos.pendientes.filter((o) => o.dias > 0)
    : datos.pendientes
  const total = pendientes.reduce((s, o) => s + o.total, 0)
  if (pendientes.length === 0 && (soloOtrosDias || datos.sin_metodo.length === 0)) return null

  const cuando = (o: OrdenPorCobrar) =>
    o.dias === 0 ? 'hoy' : o.dias === 1 ? 'ayer' : `hace ${o.dias} días`

  return (
    <section className="pc-caja">
      <div className="pc-cabecera">
        <h3>Por cobrar</h3>
        {total > 0 && <span className="pc-total">{soles(total)}</span>}
      </div>
      {error && <p className="error-admin">{error}</p>}

      {pendientes.length > 0 && (
        <ul className="pc-lista">
          {pendientes.map((o) => (
            <li key={o.id} className="pc-fila">
              <div className="pc-quien">
                <strong>#{o.numero_orden_dia}</strong>
                <span className="pc-cuando">{cuando(o)}</span>
                {o.mesas.length > 0 && (
                  <span className="pc-mesa">Mesa {o.mesas.join(', ')}</span>
                )}
              </div>
              <span className="pc-monto">{soles(o.total)}</span>
              {confirmando === o.id ? (
                <div className="pc-acciones">
                  <span className="pc-pregunta">¿Se fue sin pagar?</span>
                  <button className="boton boton--sm boton--peligro" disabled={ocupado === o.id}
                          onClick={() => hacer(o.id, () => api.marcarIncobrable(o.id))}>
                    Sí, darlo por perdido
                  </button>
                  <button className="boton boton--sm" onClick={() => setConfirmando(null)}>
                    No
                  </button>
                </div>
              ) : (
                <div className="pc-acciones">
                  {(['efectivo', 'yape', 'tarjeta'] as const).map((m) => (
                    <button key={m} className="boton boton--sm boton--papel"
                            disabled={ocupado === o.id}
                            onClick={() => hacer(o.id, () => api.cobrarPendiente(o.id, m))}>
                      {m === 'efectivo' ? '💵 Efectivo' : m === 'yape' ? '📱 Yape' : '💳 Tarjeta'}
                    </button>
                  ))}
                  <button className="boton boton--sm pc-perdido"
                          onClick={() => setConfirmando(o.id)}>
                    🚶 No pagó
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {!soloOtrosDias && datos.sin_metodo.length > 0 && (
        <p className="nota-admin">
          Además hay {datos.sin_metodo.length} ticket{datos.sin_metodo.length === 1 ? '' : 's'} de
          días pasados por {soles(datos.total_sin_metodo)} donde nadie anotó con qué se pagó;
          la caja de ese día los cuadró como efectivo.
        </p>
      )}
    </section>
  )
}
