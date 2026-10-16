import { useEffect, useState } from 'react'
import { api, type Escenario, type Sensibilidad } from './api'
import { Chips } from './Controles'
import { pct, soles } from './formato'

interface Props {
  esc: Escenario
  onError: (e: unknown) => void
}

const DELTAS = [
  { valor: 0.05, texto: '±5 %' },
  { valor: 0.1, texto: '±10 %' },
  { valor: 0.2, texto: '±20 %' },
  { valor: 0.3, texto: '±30 %' },
]

function Tornado({ filas, delta }: { filas: Sensibilidad['tornado']; delta: number }) {
  const base = filas[0]?.base ?? 0
  const extremos = filas.flatMap((f) => [f.abajo, f.arriba, base])
  const min = Math.min(...extremos)
  const max = Math.max(...extremos)
  const x = (v: number) => ((v - min) / (max - min || 1)) * 100
  return (
    <figure className="es-grafico">
      <figcaption>
        Utilidad del mes si cada número se mueve {pct(delta, 0)} (los demás quietos)
      </figcaption>
      <div className="es-leyenda">
        <span>
          <i className="es-muestra es-muestra-baja" /> Si baja {pct(delta, 0)}
        </span>
        <span>
          <i className="es-muestra es-muestra-sube" /> Si sube {pct(delta, 0)}
        </span>
      </div>
      <div className="es-tornado">
        {filas.map((f) => {
          const pares = [
            { v: f.abajo, clase: 'es-tor-baja', texto: `baja: ${soles(f.abajo)}` },
            { v: f.arriba, clase: 'es-tor-sube', texto: `sube: ${soles(f.arriba)}` },
          ]
          return (
            <div key={f.variable} className="es-tor-fila">
              <span className="es-tor-nombre">{f.nombre}</span>
              <div className="es-tor-pista">
                <span className="es-tor-base" style={{ left: `${x(base)}%` }} />
                {pares.map((p) => (
                  <span
                    key={p.clase}
                    className={`es-tor-barra ${p.clase}`}
                    title={p.texto}
                    style={{ left: `${Math.min(x(p.v), x(base))}%`, width: `${Math.abs(x(p.v) - x(base))}%` }}
                  />
                ))}
              </div>
              <span className="es-tor-rango">{soles(f.rango)}</span>
            </div>
          )
        })}
      </div>
      <p className="es-nota">
        La línea es tu utilidad de hoy: {soles(base)} al mes. A la derecha, la diferencia entre el mejor y el peor caso:
        arriba va lo que más te mueve el negocio.
      </p>
    </figure>
  )
}

function Matriz({ m, precio, q }: { m: Sensibilidad['matriz']; precio: number; q: number }) {
  const maximo = Math.max(1, ...m.utilidad.flat().map(Math.abs))
  return (
    <div className="es-tabla-caja">
      <table className="es-tabla es-matriz">
        <caption>Utilidad del mes según precio (columnas) y menús al día (filas)</caption>
        <thead>
          <tr>
            <th>Menús/día</th>
            {m.precios.map((p) => (
              <th key={p} className={Math.abs(p - precio) < 0.01 ? 'es-actual' : undefined}>
                {soles(p, 2)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {m.volumenes.map((v, i) => (
            <tr key={v}>
              <th className={v === Math.round(q) ? 'es-actual' : undefined}>{v}</th>
              {m.utilidad[i].map((u, j) => {
                const fuerza = Math.min(1, Math.abs(u) / maximo)
                return (
                  <td
                    key={j}
                    className={u >= 0 ? 'es-celda-pos' : 'es-celda-neg'}
                    style={{ ['--fuerza' as string]: `${Math.round(12 + fuerza * 48)}%` }}
                  >
                    {Math.abs(u) >= 1000 ? `${u < 0 ? '−' : ''}${(Math.abs(u) / 1000).toFixed(1)}k` : Math.round(u)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function PanelSensibilidad({ esc, onError }: Props) {
  const [delta, setDelta] = useState(0.1)
  const [datos, setDatos] = useState<Sensibilidad | null>(null)

  useEffect(() => {
    const t = setTimeout(() => api.sensibilidad(esc, delta).then(setDatos).catch(onError), 250)
    return () => clearTimeout(t)
  }, [esc, delta, onError])

  if (!datos) return <p className="es-nota">Calculando…</p>
  return (
    <div className="es-resultados es-solo">
      <p className="es-nota">
        Usa los números del simulador del mes ({esc.q} menús al día a {soles(esc.precio ?? 0, 2)}). Muévelos allá y
        vuelve aquí.
      </p>
      <Chips valor={delta} onChange={setDelta} opciones={DELTAS} />
      <Tornado filas={datos.tornado} delta={delta} />

      <div className="es-tabla-caja">
        <table className="es-tabla">
          <caption>Cuánto aguanta cada número antes de que pierdas</caption>
          <thead>
            <tr>
              <th>Número</th>
              <th>Cambio que te deja en cero</th>
            </tr>
          </thead>
          <tbody>
            {datos.quiebres.map((q) => {
              let texto: string
              if (q.cambio === null) texto = 'ni moviéndolo mucho cambia de signo'
              else if (Math.abs(q.cambio) < 0.0005) texto = 'ya estás en cero'
              else if (datos.tornado[0].base < 0)
                texto = `tendría que ${q.cambio > 0 ? 'subir' : 'bajar'} ${pct(Math.abs(q.cambio))} para no perder`
              else texto = `puede ${q.cambio > 0 ? 'subir' : 'bajar'} hasta ${pct(Math.abs(q.cambio))}`
              return (
                <tr key={q.variable}>
                  <th>{q.nombre}</th>
                  <td>{texto}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <Matriz m={datos.matriz} precio={esc.precio ?? 0} q={esc.q} />
    </div>
  )
}
