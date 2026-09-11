import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError, clearAdminToken, soles } from '../api'
import type { InsumoTablero, Tablero } from '../api'

/** Columnas ordenables de la tabla de insumos. */
type Columna = 'nombre' | 'clase_abc' | 'consumido_soles' | 'comprado_soles' |
  'merma_soles' | 'stock_actual' | 'dias_stock'

const COLUMNAS: { id: Columna; titulo: string; num: boolean }[] = [
  { id: 'nombre', titulo: 'Insumo', num: false },
  { id: 'clase_abc', titulo: 'ABC', num: false },
  { id: 'consumido_soles', titulo: 'Se usó S/', num: true },
  { id: 'comprado_soles', titulo: 'Se compró S/', num: true },
  { id: 'merma_soles', titulo: 'Merma S/', num: true },
  { id: 'stock_actual', titulo: 'Queda', num: true },
  { id: 'dias_stock', titulo: 'Días', num: true },
]

const NOMBRE_CLASE: Record<string, string> = {
  A: 'A · vigilar',
  B: 'B · medio',
  C: 'C · poco peso',
  '-': 'sin consumo',
}

/** Redondea el tope de la escala a una cifra limpia (1200, 2500, 5000…)
 *  para que las marcas del eje sean números que se leen de un vistazo. */
function topeLimpio(max: number): number {
  if (max <= 0) return 1
  const magnitud = Math.pow(10, Math.floor(Math.log10(max)))
  for (const paso of [1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10]) {
    if (max <= paso * magnitud) return paso * magnitud
  }
  return 10 * magnitud
}

/** Marca del eje: número redondo y con separador de miles (S/ 1,500). */
function marcaEje(v: number): string {
  return `S/ ${Math.round(v).toLocaleString('es-PE')}`
}

function valorOrden(i: InsumoTablero, col: Columna): number | string {
  if (col === 'nombre') return i.nombre.toLowerCase()
  if (col === 'clase_abc') return i.clase_abc
  if (col === 'dias_stock') return i.dias_stock ?? Number.MAX_SAFE_INTEGER
  return i[col] as number
}

/**
 * El tablero del dueño: los números grandes arriba, cómo va la venta día
 * a día, qué día de la semana rinde más, qué platos salen y — el corazón
 * del pedido — la tabla de insumos clasificada, para ver de un vistazo
 * en qué se va la plata de la cocina.
 */
export function TabTablero({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [dias, setDias] = useState(30)
  const [datos, setDatos] = useState<Tablero | null>(null)
  const [error, setError] = useState('')
  const [busca, setBusca] = useState('')
  const [orden, setOrden] = useState<Columna>('consumido_soles')
  const [desc, setDesc] = useState(true)

  const cargar = useCallback(async () => {
    try {
      setDatos(await api.tablero(dias))
      setError('')
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        clearAdminToken()
        onSesionVencida()
        setError('Sesión vencida, entra de nuevo')
      } else {
        setError(e instanceof Error ? e.message : 'No se pudo cargar el tablero')
      }
    }
  }, [dias, onSesionVencida])

  useEffect(() => { cargar() }, [cargar])

  const insumos = useMemo(() => {
    const texto = busca.trim().toLowerCase()
    const lista = (datos?.insumos ?? []).filter((i) => !texto || i.nombre.toLowerCase().includes(texto))
    return [...lista].sort((a, b) => {
      const va = valorOrden(a, orden)
      const vb = valorOrden(b, orden)
      const cmp = typeof va === 'string' ? va.localeCompare(vb as string) : (va as number) - (vb as number)
      return desc ? -cmp : cmp
    })
  }, [datos, busca, orden, desc])

  const ordenarPor = (col: Columna) => {
    if (col === orden) setDesc((v) => !v)
    else { setOrden(col); setDesc(col !== 'nombre') }
  }

  const descargarCSV = () => {
    const cab = ['Insumo', 'Unidad', 'Clase ABC', 'Se usó', 'Se usó S/', '% del gasto',
                 'Se compró', 'Se compró S/', 'Merma', 'Merma S/', 'Queda', 'Días de stock']
    const filas = insumos.map((i) => [
      i.nombre, i.unidad, i.clase_abc, i.consumido, i.consumido_soles, i.pct_valor,
      i.comprado, i.comprado_soles, i.merma, i.merma_soles, i.stock_actual,
      i.dias_stock ?? '',
    ])
    const csv = [cab, ...filas]
      .map((f) => f.map((c) => (typeof c === 'string' && c.includes(',') ? `"${c}"` : c)).join(','))
      .join('\n')
    const url = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `insumos-${datos?.desde ?? 'periodo'}-a-${datos?.hasta ?? ''}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (error) return <section><h2>Tablero</h2><p className="error-admin">{error}</p></section>
  if (!datos) return <section><h2>Tablero</h2><p className="nota-admin">Cargando…</p></section>

  const k = datos.kpis
  const conVenta = datos.por_dia.filter((d) => d.ventas > 0)
  const maxDia = Math.max(1, ...conVenta.map((d) => d.ventas))
  const topeDia = topeLimpio(maxDia)
  const maxSemana = Math.max(1, ...datos.por_dia_semana.map((d) => d.promedio))
  const topeSemana = topeLimpio(maxSemana)
  const mejorDiaSemana = datos.por_dia_semana.reduce(
    (a, b) => (b.promedio > a.promedio ? b : a), datos.por_dia_semana[0])
  const maxPlato = Math.max(1, ...datos.top_platos.map((p) => p.cantidad))
  const totalGasto = datos.insumos.reduce((s, i) => s + i.consumido_soles, 0)
  const maxGasto = Math.max(1, ...datos.insumos.map((i) => i.consumido_soles))

  return (
    <section className="tablero">
      <div className="tablero-cabecera">
        <h2>Tablero</h2>
        <div className="admin-acciones">
          {[7, 30, 90].map((d) => (
            <button key={d} className={dias === d ? 'boton-primario' : ''} onClick={() => setDias(d)}>
              {d} días
            </button>
          ))}
        </div>
      </div>
      <p className="nota-admin">
        Del {datos.desde} al {datos.hasta} · {k.dias_con_venta} día{k.dias_con_venta === 1 ? '' : 's'} con venta
      </p>

      {/* Los números grandes: cada uno es una cifra, no una gráfica */}
      <div className="tb-kpis">
        <div className="tb-kpi tb-kpi-hero">
          <span className="tb-kpi-rotulo">Vendido</span>
          <span className="tb-kpi-cifra">{soles(k.ventas)}</span>
          <span className="tb-kpi-pie">{soles(k.promedio_dia)} por día</span>
        </div>
        <div className="tb-kpi">
          <span className="tb-kpi-rotulo">Insumos usados</span>
          <span className="tb-kpi-cifra">{soles(k.costo_insumos)}</span>
          <span className="tb-kpi-pie">lo que se cocinó, según recetas</span>
        </div>
        <div className="tb-kpi">
          <span className="tb-kpi-rotulo">Margen</span>
          <span className="tb-kpi-cifra">{k.margen_pct != null ? `${k.margen_pct}%` : '—'}</span>
          <span className="tb-kpi-pie">queda después de la comida</span>
        </div>
        <div className="tb-kpi">
          <span className="tb-kpi-rotulo">Salió del cajón</span>
          <span className="tb-kpi-cifra">{soles(k.egresos + k.compras)}</span>
          <span className="tb-kpi-pie">compras {soles(k.compras)} · gastos {soles(k.egresos)}</span>
        </div>
        <div className="tb-kpi">
          <span className="tb-kpi-rotulo">Mermas</span>
          <span className="tb-kpi-cifra">{soles(k.mermas)}</span>
          <span className="tb-kpi-pie">lo que se botó</span>
        </div>
      </div>

      {/* Venta por día: una sola serie, un solo color, sin leyenda */}
      <div className="tb-panel">
        <h3>Cuánto se vendió cada día</h3>
        {conVenta.length === 0 ? (
          <p className="nota-admin">Sin ventas en el período.</p>
        ) : (
          <div className="tb-plot">
            <div className="tb-eje" aria-hidden="true">
              <span>{marcaEje(topeDia)}</span>
              <span>{marcaEje(topeDia / 2)}</span>
              <span>0</span>
            </div>
            <div className="tb-columnas">
            {conVenta.map((d) => (
              <div className="tb-col" key={d.fecha}
                   title={`${d.dia_semana} ${d.etiqueta}: ${soles(d.ventas)}`}>
                {d.ventas === maxDia && <span className="tb-col-valor">{soles(d.ventas)}</span>}
                <i className="tb-barra-venta" style={{ height: `${(d.ventas / topeDia) * 100}%` }} />
                <span className="tb-col-x">{d.etiqueta}</span>
              </div>
            ))}
            </div>
          </div>
        )}
      </div>

      <div className="tb-dos">
        {/* Qué día de la semana rinde más (el histograma que pediste) */}
        <div className="tb-panel">
          <h3>Qué día vende más</h3>
          <p className="nota-admin">Promedio de los días que abriste.</p>
          <div className="tb-columnas tb-columnas-semana">
            {datos.por_dia_semana.map((d) => (
              <div className="tb-col" key={d.dia}
                   title={d.veces ? `${d.dia}: ${soles(d.promedio)} en promedio (${d.veces} ${d.veces === 1 ? 'vez' : 'veces'})` : `${d.dia}: sin servicio`}>
                {d.dia === mejorDiaSemana?.dia && d.promedio > 0 && (
                  <span className="tb-col-valor">{soles(d.promedio)}</span>
                )}
                <i className="tb-barra-venta" style={{ height: `${(d.promedio / topeSemana) * 100}%` }} />
                <span className="tb-col-x">{d.dia.slice(0, 3)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Los platos que más salen: barras horizontales con su cifra */}
        <div className="tb-panel">
          <h3>Los platos que más salen</h3>
          <div className="tb-ranking">
            {datos.top_platos.map((p) => (
              <div className="tb-rank-fila" key={p.nombre} title={`${p.cantidad} vendidos · ${soles(p.total)}`}>
                <span className="tb-rank-nombre">{p.nombre}</span>
                <span className="tb-rank-barra">
                  <i style={{ width: `${(p.cantidad / maxPlato) * 100}%` }} />
                </span>
                <span className="tb-rank-cifra">{p.cantidad}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* La tabla: el corazón del pedido */}
      <div className="tb-panel">
        <div className="tb-tabla-cabecera">
          <h3>En qué se va la plata de la cocina</h3>
          <div className="tb-tabla-controles">
            <input className="tb-busca" placeholder="Buscar insumo…" value={busca}
                   aria-label="Buscar insumo" onChange={(e) => setBusca(e.target.value)} />
            <button className="boton boton--sm boton--papel" onClick={descargarCSV}>⬇️ Excel (CSV)</button>
          </div>
        </div>
        <p className="nota-admin">
          <strong>A</strong> = los pocos insumos que se llevan el 80% del gasto (los que hay que vigilar),
          <strong> B</strong> el siguiente 15%, <strong>C</strong> la cola. Toca un título para ordenar.
        </p>
        <div className="tabla-envoltorio">
          <table className="tb-tabla">
            <thead>
              <tr>
                {COLUMNAS.map((c) => (
                  <th key={c.id} className={c.num ? 'num' : ''}>
                    <button onClick={() => ordenarPor(c.id)}
                            aria-label={`Ordenar por ${c.titulo}`}>
                      {c.titulo}{orden === c.id ? (desc ? ' ▼' : ' ▲') : ''}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {insumos.map((i) => (
                <tr key={i.id} className={i.clase_abc === 'A' ? 'fila-a' : ''}>
                  <td>
                    <span className="tb-insumo">{i.nombre}</span>
                    <span className="tb-unidad">{i.unidad}</span>
                  </td>
                  <td><span className={`tb-abc tb-abc-${i.clase_abc.toLowerCase()}`}
                            title={NOMBRE_CLASE[i.clase_abc] ?? i.clase_abc}>{i.clase_abc}</span></td>
                  <td className="num">
                    <span className="tb-celda-barra" aria-hidden="true">
                      <i style={{ width: `${(i.consumido_soles / maxGasto) * 100}%` }} />
                    </span>
                    <strong>{soles(i.consumido_soles)}</strong>
                    <small>{i.consumido} {i.unidad} · {i.pct_valor}%</small>
                  </td>
                  <td className="num">
                    {i.comprado_soles > 0 ? <>{soles(i.comprado_soles)}<small>{i.comprado} {i.unidad}</small></> : '—'}
                  </td>
                  <td className="num">{i.merma_soles > 0 ? soles(i.merma_soles) : '—'}</td>
                  <td className={`num ${i.stock_actual < 0 ? 'tb-negativo' : ''}`}>
                    {i.stock_actual}
                    {i.bajo_minimo && <small className="tb-aviso">⚠ bajo el mínimo</small>}
                  </td>
                  <td className="num">
                    {i.dias_stock == null ? '—' : (
                      <span className={i.dias_stock < 3 ? 'tb-urgente' : ''}>
                        {i.dias_stock < 3 && '⚠ '}{i.dias_stock}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
              {insumos.length === 0 && (
                <tr><td colSpan={7} className="nota-admin">Sin insumos que mostrar.</td></tr>
              )}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={2}><strong>Total</strong></td>
                <td className="num"><strong>{soles(totalGasto)}</strong></td>
                <td className="num"><strong>{soles(datos.insumos.reduce((s, i) => s + i.comprado_soles, 0))}</strong></td>
                <td className="num"><strong>{soles(datos.insumos.reduce((s, i) => s + i.merma_soles, 0))}</strong></td>
                <td colSpan={2}></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </section>
  )
}
