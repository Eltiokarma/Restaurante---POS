import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type Corrida, type DecisionCorrida, type Guardado } from './api'
import { Dato } from './Controles'
import { pct, soles } from './formato'

interface Props {
  onError: (e: unknown) => void
}

const PORCION: Record<string, string> = { economica: 'Económica', estandar: 'Estándar', generosa: 'Generosa' }
const COLORES = ['var(--serie-1)', 'var(--serie-2)', '#1baf7a']
const ESTADO: Record<Corrida['estado'], string> = {
  pendiente: 'En cola',
  corriendo: 'Calculando…',
  lista: 'Lista',
  error: 'Falló',
  interrumpida: 'Interrumpida (se reinició el servicio)',
}

const mezclaTxt = (m: number | null) => (m === null ? 'actual' : `${Math.round(m * 100)} % res`)
const precioTxt = (d: { precio: number; delta_precio: number }) =>
  `${soles(d.precio, 2)}${d.delta_precio ? ` (${d.delta_precio > 0 ? '+' : '−'}${Math.abs(d.delta_precio).toFixed(1)})` : ''}`

function describir(d: DecisionCorrida) {
  return [
    `menú a ${soles(d.precio, 2)}`,
    `porción ${PORCION[d.calidad].toLowerCase()}`,
    d.mezcla === null ? null : `${Math.round(d.mezcla * 100)} % de segundos de res`,
    d.noche ? 'abriendo de noche' : 'solo de día',
  ]
    .filter(Boolean)
    .join(', ')
}

/** Utilidad del mes según el precio, una línea por elasticidad (lo demás como está). */
function CurvaPrecio({ c }: { c: Corrida }) {
  const r = c.resultado!
  const base = r.base
  if (!r.filas || !base) return null
  const els = r.factores!.elasticidad
  const series = els.map((el) =>
    r
      .filas!.filter(
        (f) => f.elasticidad === el && f.calidad === base.calidad && f.mezcla === base.mezcla && f.noche === base.noche,
      )
      .sort((a, b) => a.precio - b.precio),
  )
  const todos = series.flat()
  if (!todos.length) return null
  const AN = 640
  const AL = 240
  const M = { i: 60, d: 16, a: 14, b: 34 }
  const xs = todos.map((f) => f.precio)
  const ys = todos.map((f) => f.utilidad)
  const x0 = Math.min(...xs)
  const x1 = Math.max(...xs)
  const y0 = Math.min(0, ...ys)
  const y1 = Math.max(0, ...ys)
  const x = (v: number) => M.i + ((v - x0) / (x1 - x0 || 1)) * (AN - M.i - M.d)
  const y = (v: number) => M.a + ((y1 - v) / (y1 - y0 || 1)) * (AL - M.a - M.b)
  const ticksY = [y0, (y0 + y1) / 2, y1]
  return (
    <figure className="es-grafico">
      <figcaption>Utilidad del mes según el precio, si se pierden más o menos clientes al subirlo</figcaption>
      <div className="es-leyenda">
        {els.map((el, k) => (
          <span key={el}>
            <i className="es-muestra" style={{ width: 16, height: 3, background: COLORES[k % 3] }} /> elasticidad {el}
            {el <= 0.5 ? ' (clientela fiel)' : el >= 1.5 ? ' (mucha competencia)' : ''}
          </span>
        ))}
      </div>
      <div className="es-lienzo">
        <svg viewBox={`0 0 ${AN} ${AL}`} role="img" aria-label="Utilidad según precio">
          {ticksY.map((t) => (
            <g key={t}>
              <line x1={M.i} x2={AN - M.d} y1={y(t)} y2={y(t)} className="es-grilla" />
              <text x={M.i - 6} y={y(t)} dy="0.32em" textAnchor="end" className="es-eje">
                {soles(t)}
              </text>
            </g>
          ))}
          <line x1={M.i} x2={AN - M.d} y1={y(0)} y2={y(0)} className="es-cero" />
          {[...new Set(xs)].map((p) => (
            <text key={p} x={x(p)} y={AL - 12} textAnchor="middle" className="es-eje">
              {p.toFixed(1)}
            </text>
          ))}
          <line x1={x(base.precio)} x2={x(base.precio)} y1={M.a} y2={AL - M.b} className="es-guia" />
          {series.map((s, k) => (
            <g key={k}>
              <path
                d={s.map((f, i) => `${i ? 'L' : 'M'}${x(f.precio).toFixed(1)},${y(f.utilidad).toFixed(1)}`).join('')}
                fill="none"
                stroke={COLORES[k % 3]}
                strokeWidth={2.2}
              />
              {s.map((f) => (
                <circle key={f.precio} cx={x(f.precio)} cy={y(f.utilidad)} r={3.5} fill={COLORES[k % 3]}>
                  <title>
                    {soles(f.precio, 2)}: {Math.round(f.q)} menús/día, {soles(f.utilidad)} al mes
                  </title>
                </circle>
              ))}
            </g>
          ))}
        </svg>
      </div>
      <p className="es-nota">
        La línea punteada es el precio de hoy. Con la porción, la mezcla y el turno actuales; solo cambia el precio.
      </p>
    </figure>
  )
}

function VistaDecisiones({ c }: { c: Corrida }) {
  const r = c.resultado!
  const ds = r.decisiones ?? []
  const mejor = ds[0]
  const base = r.base
  // Mejor peor-caso por precio y porción (lo mejor de mezcla y noche)
  const precios = [...new Set(ds.map((d) => d.precio))].sort((a, b) => a - b)
  const porciones = r.factores?.calidad ?? []
  const celda = (p: number, cal: string) =>
    ds.filter((d) => d.precio === p && d.calidad === cal).sort((a, b) => b.utilidad_peor - a.utilidad_peor)[0]
  const maximo = Math.max(1, ...ds.map((d) => Math.abs(d.utilidad_peor)))
  if (!mejor) return null
  return (
    <>
      <div className="es-datos">
        <Dato
          titulo="Hoy (con la demanda como está)"
          valor={soles(base?.utilidad_media ?? 0)}
          nota={`al mes · ${r.base_nombre}`}
          tono={(base?.utilidad_media ?? 0) >= 0 ? 'bien' : 'mal'}
        />
        <Dato
          titulo="Mejor decisión, en su peor caso"
          valor={soles(mejor.utilidad_peor)}
          nota={`al mes · en promedio ${soles(mejor.utilidad_media)}`}
          tono={mejor.utilidad_peor >= 0 ? 'bien' : 'mal'}
        />
        <Dato titulo="Riesgo de perder en el año" valor={pct(mejor.prob_perdida_max, 0)} nota="en el peor caso de demanda" />
        <Dato titulo="Combinaciones calculadas" valor={String(r.filas?.length ?? 0)} nota={`${ds.length} decisiones × ${r.factores?.elasticidad.length} demandas`} />
      </div>
      <p className="es-recomendacion">
        <strong>Lo más sólido:</strong> {describir(mejor)}. Vendería entre {Math.round(mejor.q_min)} y {Math.round(mejor.q_max)} menús
        al día según cuántos clientes se pierdan con el precio.
      </p>

      <CurvaPrecio c={c} />

      <div className="es-tabla-caja">
        <table className="es-tabla es-matriz">
          <caption>Peor caso del mes según precio y porción (con la mejor mezcla y turno para cada uno)</caption>
          <thead>
            <tr>
              <th>Precio</th>
              {porciones.map((p) => (
                <th key={p}>{PORCION[p]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {precios.map((p) => (
              <tr key={p}>
                <th className={p === r.precio0 ? 'es-actual' : undefined}>{soles(p, 2)}</th>
                {porciones.map((cal) => {
                  const d = celda(p, cal)
                  if (!d) return <td key={cal}>—</td>
                  const fuerza = Math.min(1, Math.abs(d.utilidad_peor) / maximo)
                  return (
                    <td
                      key={cal}
                      className={d.utilidad_peor >= 0 ? 'es-celda-pos' : 'es-celda-neg'}
                      style={{ ['--fuerza' as string]: `${Math.round(12 + fuerza * 48)}%` }}
                      title={describir(d)}
                    >
                      {soles(d.utilidad_peor)}
                      <span className="es-nota-celda">
                        {' '}
                        {d.noche ? '· noche' : ''} {d.mezcla !== null ? `· ${Math.round(d.mezcla * 100)} % res` : ''}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="es-tabla-caja">
        <table className="es-tabla">
          <caption>Las 15 decisiones más sólidas (ordenadas por su peor caso)</caption>
          <thead>
            <tr>
              <th>#</th>
              <th>Precio</th>
              <th>Porción</th>
              <th>Mezcla</th>
              <th>Noche</th>
              <th>Peor caso</th>
              <th>Promedio</th>
              <th>Mejor caso</th>
              <th>P(pérdida)</th>
              <th>VAN medio</th>
              <th>Menús/día</th>
            </tr>
          </thead>
          <tbody>
            {ds.slice(0, 15).map((d, k) => (
              <tr key={k}>
                <th>{k + 1}</th>
                <td>{precioTxt(d)}</td>
                <td>{PORCION[d.calidad]}</td>
                <td>{mezclaTxt(d.mezcla)}</td>
                <td>{d.noche ? 'sí' : 'no'}</td>
                <td className={d.utilidad_peor < 0 ? 'es-mal' : 'es-mejor'}>{soles(d.utilidad_peor)}</td>
                <td>{soles(d.utilidad_media)}</td>
                <td>{soles(d.utilidad_mejor)}</td>
                <td>{pct(d.prob_perdida_max, 0)}</td>
                <td>{soles(d.van_medio)}</td>
                <td>
                  {Math.round(d.q_min)}–{Math.round(d.q_max)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {r.mezcla && (
        <p className="es-nota">
          Mezcla desde tus recetas: un segundo de res cuesta {soles(r.mezcla.costo_res, 2)} y uno de pollo, pasta u otros{' '}
          {soles(r.mezcla.costo_otros, 2)}; hoy el {Math.round(r.mezcla.parte_actual * 100)} % de los segundos vendidos son de
          res.
        </p>
      )}
      <details className="es-supuestos">
        <summary>Supuestos de la corrida</summary>
        <ul>
          {Object.values(r.supuestos ?? {}).map((t) => (
            <li key={t}>{t}</li>
          ))}
          <li>
            Con la planilla automática, menos clientes puede significar un mozo menos: por eso a veces subir el precio
            mejora la utilidad aunque se vendan menos menús.
          </li>
        </ul>
      </details>
    </>
  )
}

function VistaEstres({ c }: { c: Corrida }) {
  const r = c.resultado!
  const golpes = r.golpes ?? []
  const negocios = (r.negocios ?? []).filter((n) => n.golpes)
  const maximo = Math.max(1, ...negocios.flatMap((n) => n.golpes!.map((g) => Math.abs(g.utilidad))))
  const sobreviven = negocios.filter((n) => n.golpes!.find((g) => g.golpe === 'todo')!.utilidad >= 0)
  return (
    <>
      <p className="es-recomendacion">
        <strong>
          {sobreviven.length} de {negocios.length}
        </strong>{' '}
        negocios siguen ganando con todos los golpes juntos
        {sobreviven.length ? `: ${sobreviven.map((n) => n.nombre).join(', ')}.` : '.'}
      </p>
      <div className="es-tabla-caja">
        <table className="es-tabla es-matriz es-comparar">
          <caption>Utilidad del mes de cada negocio frente a cada golpe (pasa el mouse para ver el riesgo)</caption>
          <thead>
            <tr>
              <th>Negocio</th>
              {golpes.map((g) => (
                <th key={g.clave}>{g.nombre}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {negocios.map((n) => (
              <tr key={n.id}>
                <th>{n.nombre}</th>
                {golpes.map((g) => {
                  const x = n.golpes!.find((y) => y.golpe === g.clave)!
                  const fuerza = Math.min(1, Math.abs(x.utilidad) / maximo)
                  return (
                    <td
                      key={g.clave}
                      className={x.utilidad >= 0 ? 'es-celda-pos' : 'es-celda-neg'}
                      style={{ ['--fuerza' as string]: `${Math.round(12 + fuerza * 48)}%` }}
                      title={`${pct(x.prob_perdida, 0)} de probabilidad de perder en el año`}
                    >
                      {soles(x.utilidad)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="es-nota">
        Cada golpe va solo, salvo “Todo junto” (clientela −15 %, insumos +20 %, IGV 18 %, sueldos +10 % y alquiler +25 % a la
        vez). “Competidor”: bajas S/ 1 el precio para no perder clientes.
      </p>
    </>
  )
}

export function PanelCorridas({ onError }: Props) {
  const [lista, setLista] = useState<Corrida[]>([])
  const [escenarios, setEscenarios] = useState<Guardado[]>([])
  const [base, setBase] = useState<number | ''>('')
  const [recetas, setRecetas] = useState(true)
  const [abierta, setAbierta] = useState<Corrida | null>(null)
  const [aviso, setAviso] = useState('')

  const refrescar = useCallback(() => api.corridas().then(setLista).catch(onError), [onError])

  useEffect(() => {
    refrescar()
    api
      .escenarios()
      .then((l) => {
        setEscenarios(l)
        const candela = l.find((g) => g.nombre.startsWith('Candela'))
        setBase(candela?.id ?? l[0]?.id ?? '')
        setRecetas(Boolean(candela))
      })
      .catch(onError)
  }, [refrescar, onError])

  const enMarcha = lista.some((c) => c.estado === 'corriendo' || c.estado === 'pendiente')
  useEffect(() => {
    if (!enMarcha) return
    const t = setInterval(refrescar, 1500)
    return () => clearInterval(t)
  }, [enMarcha, refrescar])

  // Al terminar la que está abierta, traer su resultado
  useEffect(() => {
    if (!abierta) return
    const fresca = lista.find((c) => c.id === abierta.id)
    if (fresca && fresca.estado !== abierta.estado) api.corrida(fresca.id).then(setAbierta).catch(onError)
  }, [lista, abierta, onError])

  const lanzar = async (cuerpo: Parameters<typeof api.lanzarCorrida>[0]) => {
    setAviso('')
    try {
      const c = await api.lanzarCorrida(cuerpo)
      setAbierta(c)
      refrescar()
    } catch (e) {
      setAviso(e instanceof Error ? e.message : 'No se pudo lanzar')
      onError(e)
    }
  }

  const nombreBase = useMemo(() => escenarios.find((g) => g.id === base)?.nombre, [escenarios, base])

  return (
    <div className="es-resultados es-solo">
      <p className="es-nota">
        Aquí el estudio calcula solo, en Railway, cientos de combinaciones y las guarda. Puedes cerrar la página: la corrida
        sigue y la encuentras aquí después.
      </p>
      <section className="es-formulario">
        <h2>Barrido de decisiones</h2>
        <p className="es-nota">
          Prueba juntos precio (−S/ 1 a +S/ 3), porción (económica, estándar, generosa), mezcla de segundos (más res o más
          pollo, con tus recetas) y turno noche, cada uno con tres supuestos de cuántos clientes se pierden al subir el precio.
        </p>
        <div className="es-fila">
          <select
            value={base}
            onChange={(e) => {
              const id = e.target.value === '' ? '' : Number(e.target.value)
              setBase(id)
              // las recetas cargadas son las de Candela
              setRecetas(Boolean(escenarios.find((g) => g.id === id)?.nombre.startsWith('Candela')))
            }}
          >
            {escenarios.map((g) => (
              <option key={g.id} value={g.id}>
                {g.nombre}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="es-principal"
            disabled={base === '' || enMarcha}
            onClick={() => lanzar({ tipo: 'decisiones', escenario_id: base as number, usar_recetas: recetas })}
          >
            Correr {nombreBase ? `“${nombreBase}”` : ''}
          </button>
        </div>
        <label className="es-check">
          <input type="checkbox" checked={recetas} onChange={(e) => setRecetas(e.target.checked)} />
          <span>Probar la mezcla de segundos con mis recetas (solo para el negocio dueño de esas recetas)</span>
        </label>
        <h2>Prueba de estrés</h2>
        <div className="es-fila">
          <button type="button" className="es-secundario" disabled={enMarcha} onClick={() => lanzar({ tipo: 'estres' })}>
            Someter a todos los negocios a golpes
          </button>
        </div>
        {aviso && <p className="es-error">{aviso}</p>}
      </section>

      <section>
        <h2>Corridas</h2>
        <div className="es-lista">
          {lista.map((c) => (
            <div key={c.id} className="es-lista-fila">
              <button
                type="button"
                className={abierta?.id === c.id ? 'es-lista-boton es-lista-on' : 'es-lista-boton'}
                onClick={() => api.corrida(c.id).then(setAbierta).catch(onError)}
              >
                <strong>{c.nombre}</strong>
                <span>
                  {ESTADO[c.estado]}
                  {c.estado === 'corriendo' ? ` ${Math.round(c.progreso * 100)} %` : ''} ·{' '}
                  {new Date(c.creado + 'Z').toLocaleString('es-PE', { dateStyle: 'short', timeStyle: 'short' })}
                  {c.total ? ` · ${c.total} cálculos` : ''}
                </span>
                {c.estado === 'corriendo' && (
                  <span className="es-progreso">
                    <i style={{ width: `${Math.round(c.progreso * 100)}%` }} />
                  </span>
                )}
              </button>
              {c.estado !== 'corriendo' && (
                <button
                  type="button"
                  className="es-quitar"
                  aria-label={`Borrar ${c.nombre}`}
                  onClick={async () => {
                    await api.borrarCorrida(c.id)
                    if (abierta?.id === c.id) setAbierta(null)
                    refrescar()
                  }}
                >
                  ✕
                </button>
              )}
            </div>
          ))}
          {!lista.length && <p className="es-nota">Aún no hay corridas.</p>}
        </div>
      </section>

      {abierta?.estado === 'lista' && abierta.resultado && (
        <section className="es-resultados-corrida">
          <h2>{abierta.nombre}</h2>
          {abierta.tipo === 'decisiones' ? <VistaDecisiones c={abierta} /> : <VistaEstres c={abierta} />}
        </section>
      )}
      {abierta?.estado === 'error' && <p className="es-error">La corrida falló: {abierta.error}</p>}
    </div>
  )
}
