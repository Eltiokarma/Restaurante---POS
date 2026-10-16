import { useEffect, useMemo, useState } from 'react'
import { api, type Comparado, type Guardado } from './api'
import { anios, pct, soles } from './formato'

interface Props {
  onAbrir: (g: Guardado) => void
  onError: (e: unknown) => void
}

type Mejor = 'alto' | 'bajo' | null

interface Fila {
  titulo: string
  valor: (c: Comparado) => string
  num?: (c: Comparado) => number | null
  mejor?: Mejor
}

const FILAS: { grupo: string; filas: Fila[] }[] = [
  {
    grupo: 'El negocio',
    filas: [
      { titulo: 'Precio del menú', valor: (c) => soles(c.precio, 2) },
      { titulo: 'Menús al día', valor: (c) => String(c.menus_dia) + (c.noche ? ' + noche' : '') },
      { titulo: 'Trabajadores', valor: (c) => String(c.trabajadores) },
      { titulo: 'Formal', valor: (c) => (c.formal ? `Sí · ${c.regimen}` : 'No') },
      { titulo: 'Inversión', valor: (c) => soles(c.inversion) },
    ],
  },
  {
    grupo: 'El mes',
    filas: [
      { titulo: 'Ventas', valor: (c) => soles(c.ventas_mes), num: (c) => c.ventas_mes, mejor: 'alto' },
      { titulo: 'Utilidad', valor: (c) => soles(c.utilidad_mes), num: (c) => c.utilidad_mes, mejor: 'alto' },
      {
        titulo: 'Lo que se lleva el dueño (utilidad + su sueldo)',
        valor: (c) => soles(c.ingreso_dueno_mes),
        num: (c) => c.ingreso_dueno_mes,
        mejor: 'alto',
      },
      { titulo: 'Margen', valor: (c) => pct(c.margen), num: (c) => c.margen, mejor: 'alto' },
      {
        titulo: 'Equilibrio (menús/día)',
        valor: (c) => (c.equilibrio === null ? 'más de 600' : String(c.equilibrio)),
        num: (c) => c.equilibrio,
        mejor: 'bajo',
      },
      { titulo: 'Precio mínimo', valor: (c) => soles(c.precio_minimo, 2) },
      { titulo: 'Insumos / ventas sin IGV', valor: (c) => pct(c.insumos_pct, 0), num: (c) => c.insumos_pct, mejor: 'bajo' },
      { titulo: 'Personal / ventas sin IGV', valor: (c) => pct(c.personal_pct, 0), num: (c) => c.personal_pct, mejor: 'bajo' },
      { titulo: 'Alquiler / ventas sin IGV', valor: (c) => pct(c.alquiler_pct, 0), num: (c) => c.alquiler_pct, mejor: 'bajo' },
    ],
  },
  {
    grupo: 'Riesgo y largo plazo',
    filas: [
      { titulo: 'Probabilidad de perder en el año', valor: (c) => pct(c.prob_perdida, 0), num: (c) => c.prob_perdida, mejor: 'bajo' },
      { titulo: 'Año malo (1 de cada 10)', valor: (c) => soles(c.anio_malo), num: (c) => c.anio_malo, mejor: 'alto' },
      { titulo: 'VAN a 10 años', valor: (c) => soles(c.van), num: (c) => c.van, mejor: 'alto' },
      { titulo: 'TIR', valor: (c) => (c.tir === null ? '—' : pct(c.tir, 0)), num: (c) => c.tir, mejor: 'alto' },
      { titulo: 'Recupera la inversión en', valor: (c) => anios(c.recupero), num: (c) => c.recupero, mejor: 'bajo' },
    ],
  },
]

const VARIABLES: { id: string; nombre: string }[] = [
  { id: 'precio', nombre: 'Precio del menú' },
  { id: 'q', nombre: 'Menús al día' },
  { id: 'insumos', nombre: 'Insumos por menú' },
  { id: 'sueldos', nombre: 'Sueldos' },
  { id: 'alquiler_mes', nombre: 'Alquiler' },
  { id: 'dias', nombre: 'Días que abre' },
  { id: 'gas', nombre: 'Gas' },
  { id: 'servicios_mes', nombre: 'Luz, agua e internet' },
]

/** Cuánto aguanta cada número antes de que el negocio pase a pérdida (o
 *  cuánto le falta, si ya pierde). Mismo motor que la pestaña Sensibilidad. */
function Aguante({ casos }: { casos: Comparado[] }) {
  return (
    <div className="es-tabla-caja">
      <table className="es-tabla es-comparar">
        <caption>Sensibilidad de cada caso: cuánto puede moverse cada número antes de perder</caption>
        <thead>
          <tr>
            <th />
            {casos.map((c) => (
              <th key={c.id}>{c.nombre}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>Lo que más lo mueve (±10 %)</th>
            {casos.map((c) => (
              <td key={c.id}>
                {c.tornado[0]?.nombre ?? '—'}
                <span className="es-nota-celda"> ±{soles(c.tornado[0]?.rango ?? 0)}</span>
              </td>
            ))}
          </tr>
          {VARIABLES.map((v) => (
            <tr key={v.id}>
              <th>{v.nombre}</th>
              {casos.map((c) => {
                const x = c.quiebres[v.id]
                const pierde = c.utilidad_mes < 0
                if (x === null || x === undefined)
                  return (
                    <td key={c.id} className="es-nota-celda">
                      {pierde ? 'ni así alcanza' : 'aguanta de sobra'}
                    </td>
                  )
                const flecha = x > 0 ? '↑' : '↓'
                const ajustado = Math.abs(x) < 0.1
                return (
                  <td key={c.id} className={pierde ? 'es-mal' : ajustado ? 'es-ajustado' : 'es-holgado'}>
                    {pierde ? 'falta ' : ''}
                    {flecha} {pct(Math.abs(x), 0)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="es-nota">
        “↓ 8 %” en precio: si el precio baja 8 %, el negocio queda en cero. En rojo, los que ya pierden: cuánto tendría
        que moverse ese número (solo) para no perder. Menos de 10 % (en ámbar) es poco margen de error.
      </p>
    </div>
  )
}

/** Barras horizontales con el cero marcado: una sola métrica, un solo eje. */
function Barras({ titulo, datos }: { titulo: string; datos: { nombre: string; v: number }[] }) {
  const max = Math.max(1, ...datos.map((d) => Math.abs(d.v)))
  const hayNeg = datos.some((d) => d.v < 0)
  const cero = hayNeg ? 50 : 0
  const escala = hayNeg ? 50 : 100
  return (
    <figure className="es-grafico">
      <figcaption>{titulo}</figcaption>
      <div className="es-barras-h">
        {datos.map((d) => {
          const ancho = (Math.abs(d.v) / max) * escala
          return (
            <div key={d.nombre} className="es-bh-fila">
              <span className="es-bh-nombre">{d.nombre}</span>
              <div className="es-bh-pista">
                {hayNeg && <span className="es-bh-cero" style={{ left: `${cero}%` }} />}
                <span
                  className={d.v < 0 ? 'es-bh-barra es-bh-neg' : 'es-bh-barra'}
                  style={{ left: `${d.v < 0 ? cero - ancho : cero}%`, width: `${Math.max(0.5, ancho)}%` }}
                />
              </div>
              <span className={d.v < 0 ? 'es-bh-valor es-mal' : 'es-bh-valor'}>{soles(d.v)}</span>
            </div>
          )
        })}
      </div>
    </figure>
  )
}

export function PanelComparar({ onAbrir, onError }: Props) {
  const [lista, setLista] = useState<Guardado[]>([])
  const [elegidos, setElegidos] = useState<number[]>([])
  const [datos, setDatos] = useState<Comparado[]>([])

  useEffect(() => {
    api
      .escenarios()
      .then((l) => {
        setLista(l)
        setElegidos(l.map((g) => g.id))
      })
      .catch(onError)
  }, [onError])

  useEffect(() => {
    if (!elegidos.length) return setDatos([])
    const t = setTimeout(() => api.comparar(elegidos).then(setDatos).catch(onError), 200)
    return () => clearTimeout(t)
  }, [elegidos, onError])

  const grupos = useMemo(() => {
    const g = new Map<string, Guardado[]>()
    for (const x of lista) {
      const cat = x.datos.ficha?.categoria ?? 'Mis escenarios'
      g.set(cat, [...(g.get(cat) ?? []), x])
    }
    return [...g.entries()]
  }, [lista])

  const validos = datos.filter((d) => !d.error)
  const mejores = (f: Fila) => {
    if (!f.num || !f.mejor || validos.length < 2) return new Set<number>()
    const vals = validos.map((c) => ({ id: c.id, v: f.num!(c) })).filter((x) => x.v !== null) as { id: number; v: number }[]
    if (!vals.length) return new Set<number>()
    const objetivo = f.mejor === 'alto' ? Math.max(...vals.map((x) => x.v)) : Math.min(...vals.map((x) => x.v))
    return new Set(vals.filter((x) => x.v === objetivo).map((x) => x.id))
  }
  const alternar = (id: number) =>
    setElegidos((e) => (e.includes(id) ? e.filter((x) => x !== id) : [...e, id]))

  return (
    <div className="es-resultados es-solo">
      <p className="es-nota">
        Elige qué negocios comparar. Todos usan el mismo motor; cada uno con sus números (abre uno en el simulador para
        moverlos y guárdalo con otro nombre para tener una variante).
      </p>
      {grupos.map(([cat, gs]) => (
        <section key={cat}>
          <h2>{cat}</h2>
          <div className="es-chips">
            {gs.map((g) => (
              <button
                key={g.id}
                type="button"
                aria-pressed={elegidos.includes(g.id)}
                className={elegidos.includes(g.id) ? 'es-chip es-chip-on' : 'es-chip'}
                onClick={() => alternar(g.id)}
              >
                {g.nombre}
              </button>
            ))}
          </div>
        </section>
      ))}

      {validos.length > 0 && (
        <>
          <Barras
            titulo="Lo que se lleva el dueño al mes (utilidad + su sueldo, si se paga uno)"
            datos={[...validos].sort((a, b) => b.ingreso_dueno_mes - a.ingreso_dueno_mes).map((c) => ({ nombre: c.nombre, v: c.ingreso_dueno_mes }))}
          />
          <Barras
            titulo="VAN a 10 años (lo que vale el negocio hoy, ya descontada la inversión)"
            datos={[...validos].sort((a, b) => b.van - a.van).map((c) => ({ nombre: c.nombre, v: c.van }))}
          />

          <div className="es-tabla-caja">
            <table className="es-tabla es-comparar">
              <caption>Métricas lado a lado (en negrita, el mejor de cada fila)</caption>
              <thead>
                <tr>
                  <th />
                  {validos.map((c) => (
                    <th key={c.id}>
                      {c.nombre}
                      <button
                        type="button"
                        className="es-abrir"
                        onClick={() => {
                          const g = lista.find((x) => x.id === c.id)
                          if (g) onAbrir(g)
                        }}
                      >
                        Abrir
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              {FILAS.map((grupo) => (
                <tbody key={grupo.grupo}>
                  <tr className="es-grupo">
                    <th colSpan={validos.length + 1}>{grupo.grupo}</th>
                  </tr>
                  {grupo.filas.map((f) => {
                    const top = mejores(f)
                    return (
                      <tr key={f.titulo}>
                        <th>{f.titulo}</th>
                        {validos.map((c) => (
                          <td key={c.id} className={top.has(c.id) ? 'es-mejor' : undefined}>
                            {f.valor(c)}
                          </td>
                        ))}
                      </tr>
                    )
                  })}
                </tbody>
              ))}
            </table>
          </div>

          <Aguante casos={validos} />

          <section>
            <h2>Cómo es cada uno</h2>
            <ul className="es-fichas">
              {validos.map((c) => (
                <li key={c.id}>
                  <strong>{c.nombre}.</strong> {c.ficha?.descripcion ?? 'Escenario propio.'}
                  {c.ficha?.supuestos?.length ? <span className="es-nota-celda"> ({c.ficha.supuestos.join(' · ')})</span> : null}
                  {c.alertas.map((a) => (
                    <span key={a} className="es-no-aplica">
                      {' '}
                      ⚠ {a}
                    </span>
                  ))}
                  {c.ficha?.fuente && <span className="es-nota-celda"> Fuente: {c.ficha.fuente}.</span>}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
      {datos
        .filter((d) => d.error)
        .map((d) => (
          <p key={d.id} className="es-error">
            {d.nombre}: no se pudo calcular ({d.error})
          </p>
        ))}
    </div>
  )
}
