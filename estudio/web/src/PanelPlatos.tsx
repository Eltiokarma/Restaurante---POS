import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ErrorToken, type AnalisisPlatos, type ClasePlato, type Escenario, type Insumo, type Plato, type TipoPlato } from './api'
import { Barra, Chips, Dato } from './Controles'
import { pct, soles } from './formato'

interface Props {
  esc: Escenario
  onUsarCosto: (insumosPorMenu: number) => void
  onError: (e: unknown) => void
}

const IGV: Record<number, number> = { 2026: 10.5, 2027: 15, 2028: 18 }
const UNIDADES = ['kg', 'litro', 'unidad', 'atado', 'paquete', 'lata', 'docena']
const TIPOS: { valor: TipoPlato; texto: string }[] = [
  { valor: 'entrada', texto: 'Entrada' },
  { valor: 'segundo', texto: 'Segundo' },
  { valor: 'sopa', texto: 'Sopa' },
  { valor: 'bebida', texto: 'Refresco' },
  { valor: 'postre', texto: 'Postre' },
  { valor: 'extra', texto: 'Extra' },
]
const NOMBRE_TIPO = Object.fromEntries(TIPOS.map((t) => [t.valor, t.texto])) as Record<TipoPlato, string>
const CLASE: Record<ClasePlato, { texto: string; icono: string }> = {
  estrella: { texto: 'Estrella', icono: '★' },
  caballo: { texto: 'Caballito de batalla', icono: '▲' },
  rompecabezas: { texto: 'Rompecabezas', icono: '◆' },
  perro: { texto: 'Perro', icono: '▼' },
}

const num = (v: string) => (v.trim() === '' ? null : Number(v.replace(',', '.')))

// ---------------- Insumos ----------------

const INSUMO_VACIO = { nombre: '', unidad: 'kg', precio: '', merma: '' }

function Insumos({ insumos, recargar, onError }: { insumos: Insumo[]; recargar: () => void; onError: (e: unknown) => void }) {
  const [f, setF] = useState(INSUMO_VACIO)
  const [editando, setEditando] = useState<number | null>(null)
  const [error, setError] = useState('')

  const guardar = async () => {
    const precio = num(f.precio)
    if (!f.nombre.trim() || precio === null || Number.isNaN(precio)) return setError('Pon nombre y precio.')
    try {
      await api.guardarInsumo(
        { nombre: f.nombre, unidad: f.unidad, precio, merma: (num(f.merma) ?? 0) / 100, categoria: null },
        editando ?? undefined,
      )
      setF(INSUMO_VACIO)
      setEditando(null)
      setError('')
      recargar()
    } catch (e) {
      if (e instanceof ErrorToken) onError(e)
      else setError(e instanceof Error ? e.message : 'Error')
    }
  }

  const borrar = async (i: Insumo) => {
    if (!window.confirm(`¿Borrar ${i.nombre}?`)) return
    try {
      await api.borrarInsumo(i.id)
      recargar()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error')
    }
  }

  return (
    <div className="es-resultados es-solo">
      <section className="es-formulario">
        <h2>{editando ? 'Editar insumo' : 'Nuevo insumo'}</h2>
        <div className="es-campos">
          <label className="es-ancho">
            <span>Nombre</span>
            <input value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} placeholder="Pollo entero" />
          </label>
          <label>
            <span>Se compra por</span>
            <select value={f.unidad} onChange={(e) => setF({ ...f, unidad: e.target.value })}>
              {UNIDADES.map((u) => (
                <option key={u}>{u}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Precio por {f.unidad}</span>
            <input inputMode="decimal" value={f.precio} onChange={(e) => setF({ ...f, precio: e.target.value })} placeholder="9.50" />
          </label>
          <label>
            <span>Merma % (lo que se bota)</span>
            <input inputMode="decimal" value={f.merma} onChange={(e) => setF({ ...f, merma: e.target.value })} placeholder="0" />
          </label>
        </div>
        <div className="es-fila">
          <button type="button" className="es-principal" onClick={guardar}>
            {editando ? 'Guardar cambios' : 'Agregar insumo'}
          </button>
          {editando && (
            <button
              type="button"
              className="es-secundario"
              onClick={() => {
                setEditando(null)
                setF(INSUMO_VACIO)
              }}
            >
              Cancelar
            </button>
          )}
        </div>
        {error && <p className="es-error">{error}</p>}
        <p className="es-nota">
          Merma: lo que se pierde al limpiar (piel y hueso del pollo, cáscara de la papa). En las recetas pones lo que va
          al plato y el costo suma la merma.
        </p>
      </section>

      <div className="es-tabla-caja">
        <table className="es-tabla">
          <caption>{insumos.length} insumos</caption>
          <thead>
            <tr>
              <th>Insumo</th>
              <th>Precio</th>
              <th>Merma</th>
              <th>Costo real</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {insumos.map((i) => (
              <tr key={i.id}>
                <th>{i.nombre}</th>
                <td>
                  {soles(i.precio, 2)} / {i.unidad}
                </td>
                <td>{pct(i.merma, 0)}</td>
                <td>
                  {soles(i.precio / (1 - i.merma), 2)} / {i.unidad}
                </td>
                <td className="es-acciones">
                  <button
                    type="button"
                    className="es-secundario"
                    onClick={() => {
                      setEditando(i.id)
                      setF({ nombre: i.nombre, unidad: i.unidad, precio: String(i.precio), merma: String(Math.round(i.merma * 1000) / 10) })
                      window.scrollTo({ top: 0, behavior: 'smooth' })
                    }}
                  >
                    Editar
                  </button>
                  <button type="button" className="es-quitar" aria-label={`Borrar ${i.nombre}`} onClick={() => borrar(i)}>
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------- Platos ----------------

interface Borrador {
  id?: number
  nombre: string
  tipo: TipoPlato
  porciones: string
  precio: string
  vendidos: string
  items: { insumo_id: number | ''; cantidad: string }[]
}

const borradorDe = (p?: Plato): Borrador =>
  p
    ? {
        id: p.id,
        nombre: p.nombre,
        tipo: p.tipo,
        porciones: String(p.porciones),
        precio: p.precio === null ? '' : String(p.precio),
        vendidos: p.vendidos === null ? '' : String(p.vendidos),
        items: p.items.map((i) => ({ insumo_id: i.insumo_id, cantidad: String(i.cantidad) })),
      }
    : { nombre: '', tipo: 'segundo', porciones: '10', precio: '', vendidos: '', items: [{ insumo_id: '', cantidad: '' }] }

function EditorPlato({
  inicial,
  insumos,
  onListo,
  onCancelar,
}: {
  inicial: Borrador
  insumos: Insumo[]
  onListo: () => void
  onCancelar: () => void
}) {
  const [b, setB] = useState(inicial)
  const [error, setError] = useState('')
  const porId = useMemo(() => new Map(insumos.map((i) => [i.id, i])), [insumos])
  const costoItem = (it: Borrador['items'][number]) => {
    const ins = it.insumo_id === '' ? undefined : porId.get(it.insumo_id)
    const c = num(it.cantidad)
    return ins && c ? (c * ins.precio) / (1 - ins.merma) : 0
  }
  const total = b.items.reduce((s, it) => s + costoItem(it), 0)
  const porciones = num(b.porciones) || 1

  const guardar = async () => {
    const items = b.items
      .filter((it) => it.insumo_id !== '' && (num(it.cantidad) ?? 0) > 0)
      .map((it) => ({ insumo_id: it.insumo_id as number, cantidad: num(it.cantidad)! }))
    if (!b.nombre.trim()) return setError('Ponle nombre al plato.')
    try {
      await api.guardarPlato(
        { nombre: b.nombre, tipo: b.tipo, porciones, precio: num(b.precio), vendidos: num(b.vendidos), notas: null, items },
        b.id,
      )
      onListo()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error')
    }
  }

  return (
    <section className="es-formulario">
      <h2>{b.id ? 'Editar plato' : 'Nuevo plato'}</h2>
      <label className="es-campo">
        <span>Nombre</span>
        <input value={b.nombre} onChange={(e) => setB({ ...b, nombre: e.target.value })} placeholder="Arroz con pollo" />
      </label>
      <Chips valor={b.tipo} onChange={(tipo) => setB({ ...b, tipo })} opciones={TIPOS} />
      <div className="es-campos">
        <label>
          <span>La receta rinde (porciones)</span>
          <input inputMode="decimal" value={b.porciones} onChange={(e) => setB({ ...b, porciones: e.target.value })} />
        </label>
        <label>
          <span>{b.tipo === 'segundo' ? 'Precio del menú con este segundo' : 'Precio si se vende solo (opcional)'}</span>
          <input inputMode="decimal" value={b.precio} onChange={(e) => setB({ ...b, precio: e.target.value })} placeholder="11" />
        </label>
        <label>
          <span>Se venden por semana</span>
          <input inputMode="decimal" value={b.vendidos} onChange={(e) => setB({ ...b, vendidos: e.target.value })} placeholder="60" />
        </label>
      </div>

      <h2>Receta completa (lo que va al plato)</h2>
      {insumos.length === 0 && <p className="es-nota">Primero agrega insumos en la pestaña Insumos.</p>}
      {b.items.map((it, k) => {
        const ins = it.insumo_id === '' ? undefined : porId.get(it.insumo_id)
        return (
          <div key={k} className="es-item">
            <select
              value={it.insumo_id}
              onChange={(e) =>
                setB({
                  ...b,
                  items: b.items.map((x, j) => (j === k ? { ...x, insumo_id: e.target.value === '' ? '' : Number(e.target.value) } : x)),
                })
              }
            >
              <option value="">Insumo…</option>
              {insumos.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.nombre}
                </option>
              ))}
            </select>
            <label className="es-cantidad">
              <input
                inputMode="decimal"
                value={it.cantidad}
                placeholder="0.5"
                aria-label="Cantidad"
                onChange={(e) =>
                  setB({ ...b, items: b.items.map((x, j) => (j === k ? { ...x, cantidad: e.target.value } : x)) })
                }
              />
              <span>{ins?.unidad ?? ''}</span>
            </label>
            <span className="es-item-costo">{soles(costoItem(it), 2)}</span>
            <button
              type="button"
              className="es-quitar"
              aria-label="Quitar insumo"
              onClick={() => setB({ ...b, items: b.items.filter((_, j) => j !== k) })}
            >
              ✕
            </button>
          </div>
        )
      })}
      <button type="button" className="es-secundario" onClick={() => setB({ ...b, items: [...b.items, { insumo_id: '', cantidad: '' }] })}>
        + Agregar insumo a la receta
      </button>
      <div className="es-datos">
        <Dato titulo="Costo de la receta" valor={soles(total, 2)} />
        <Dato titulo="Costo por porción" valor={soles(total / porciones, 2)} nota={`rinde ${porciones}`} />
      </div>
      <div className="es-fila">
        <button type="button" className="es-principal" onClick={guardar}>
          Guardar plato
        </button>
        <button type="button" className="es-secundario" onClick={onCancelar}>
          Cancelar
        </button>
      </div>
      {error && <p className="es-error">{error}</p>}
    </section>
  )
}

function Platos({ platos, insumos, recargar }: { platos: Plato[]; insumos: Insumo[]; recargar: () => void }) {
  const [editando, setEditando] = useState<Borrador | null>(null)
  if (editando)
    return (
      <div className="es-resultados es-solo">
        <EditorPlato
          inicial={editando}
          insumos={insumos}
          onCancelar={() => setEditando(null)}
          onListo={() => {
            setEditando(null)
            recargar()
          }}
        />
      </div>
    )
  return (
    <div className="es-resultados es-solo">
      <button type="button" className="es-principal" onClick={() => setEditando(borradorDe())}>
        + Nuevo plato
      </button>
      {TIPOS.map((t) => {
        const grupo = platos.filter((p) => p.tipo === t.valor)
        if (!grupo.length) return null
        return (
          <section key={t.valor}>
            <h2>{t.texto}</h2>
            <div className="es-lista">
              {grupo.map((p) => (
                <div key={p.id} className="es-lista-fila">
                  <button type="button" className="es-lista-boton" onClick={() => setEditando(borradorDe(p))}>
                    <strong>{p.nombre}</strong>
                    <span>
                      {p.items.length} insumos · rinde {p.porciones}
                      {p.precio ? ` · ${soles(p.precio, 2)}` : ''}
                      {p.vendidos ? ` · ${p.vendidos}/semana` : ''}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="es-quitar"
                    aria-label={`Borrar ${p.nombre}`}
                    onClick={async () => {
                      if (window.confirm(`¿Borrar ${p.nombre}?`)) {
                        await api.borrarPlato(p.id)
                        recargar()
                      }
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </section>
        )
      })}
      {!platos.length && <p className="es-nota">Aún no hay platos. Agrega primero los insumos y luego arma las recetas.</p>}
    </div>
  )
}

// ---------------- Análisis ----------------

function Cuadrante({ filas }: { filas: AnalisisPlatos['platos'] }) {
  const con = filas.filter((f) => f.clase && f.popularidad !== null && f.margen !== null)
  if (con.length < 2) return null
  const AN = 640
  const AL = 300
  const M = { izq: 56, der: 16, arr: 16, aba: 40 }
  const xs = con.map((f) => f.popularidad!)
  const ys = con.map((f) => f.margen!)
  const umbral = con[0].umbral_popularidad ?? 0
  const mprom = con[0].margen_promedio ?? 0
  const xMax = Math.max(...xs, umbral) * 1.15
  const yMin = Math.min(...ys, mprom) - 0.5
  const yMax = Math.max(...ys, mprom) + 0.5
  const x = (v: number) => M.izq + (v / xMax) * (AN - M.izq - M.der)
  const y = (v: number) => M.arr + ((yMax - v) / (yMax - yMin)) * (AL - M.arr - M.aba)
  return (
    <figure className="es-grafico">
      <figcaption>Segundos: cuánto se venden y cuánto dejan</figcaption>
      <div className="es-lienzo">
        <svg viewBox={`0 0 ${AN} ${AL}`} role="img" aria-label="Ingeniería de menú">
          <line x1={x(umbral)} x2={x(umbral)} y1={M.arr} y2={AL - M.aba} className="es-guia" />
          <line x1={M.izq} x2={AN - M.der} y1={y(mprom)} y2={y(mprom)} className="es-guia" />
          <text x={AN - M.der} y={M.arr + 12} textAnchor="end" className="es-eje">
            Estrellas ★
          </text>
          <text x={M.izq + 4} y={M.arr + 12} className="es-eje">
            ◆ Rompecabezas
          </text>
          <text x={AN - M.der} y={AL - M.aba - 6} textAnchor="end" className="es-eje">
            Caballitos de batalla ▲
          </text>
          <text x={M.izq + 4} y={AL - M.aba - 6} className="es-eje">
            ▼ Perros
          </text>
          <text x={(M.izq + AN) / 2} y={AL - 8} textAnchor="middle" className="es-eje">
            Parte de las ventas →
          </text>
          <text x={14} y={(AL - M.aba) / 2} className="es-eje" transform={`rotate(-90 14 ${(AL - M.aba) / 2})`} textAnchor="middle">
            Margen por menú →
          </text>
          {con.map((f) => (
            <g key={f.id}>
              <circle cx={x(f.popularidad!)} cy={y(f.margen!)} r={7} className="es-punto">
                <title>
                  {f.nombre}: {pct(f.popularidad!, 0)} de las ventas, deja {soles(f.margen!, 2)}
                </title>
              </circle>
              <text
                x={x(f.popularidad!) + (x(f.popularidad!) > AN * 0.7 ? -10 : 10)}
                y={y(f.margen!)}
                dy="0.32em"
                textAnchor={x(f.popularidad!) > AN * 0.7 ? 'end' : 'start'}
                className="es-etiqueta"
              >
                {f.nombre}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </figure>
  )
}

function Analisis({
  analisis,
  esc,
  onUsarCosto,
}: {
  analisis: AnalisisPlatos
  esc: Escenario
  onUsarCosto: (v: number) => void
}) {
  const [elegido, setElegido] = useState<number | ''>(analisis.pareto[0]?.insumo_id ?? '')
  const [alza, setAlza] = useState(0.2)
  const menu = analisis.menu
  const costoPct = menu.precio_promedio ? menu.costo / (menu.precio_promedio / (1 + (esc.formal ? (IGV[esc.anio] ?? 18) / 100 : 0))) : null
  const contrib = menu.por_insumo.find((p) => p.insumo_id === elegido)?.costo ?? 0
  const subeMenu = contrib * alza
  const subeMes = subeMenu * esc.q * esc.dias

  if (!analisis.platos.length) return <p className="es-nota">Arma tus recetas en la pestaña Platos para ver el análisis.</p>
  return (
    <div className="es-resultados es-solo">
      <div className="es-datos">
        <Dato titulo="Costo de insumos del menú promedio" valor={soles(menu.costo, 2)} nota="segundo + entrada y refresco promedio" />
        <Dato titulo="Precio promedio del menú" valor={menu.precio_promedio ? soles(menu.precio_promedio, 2) : '—'} />
        <Dato
          titulo="Costo de insumos sobre el precio sin IGV"
          valor={costoPct === null ? '—' : pct(costoPct, 0)}
          nota="en menú popular suele ir de 35 a 45 %"
          tono={costoPct !== null && costoPct <= 0.45 ? 'bien' : 'mal'}
        />
        <Dato titulo="Compras de la semana" valor={soles(analisis.gasto_semana)} nota="según lo que se vende" />
      </div>
      {menu.costo > 0 && (
        <button type="button" className="es-secundario" onClick={() => onUsarCosto(Math.round((menu.costo / 1.05) * 100) / 100)}>
          Usar este costo en el simulador (insumos por menú: {soles(menu.costo / 1.05, 2)})
        </button>
      )}
      <p className="es-nota">
        El simulador le suma 5 % de merma general al costo; como tus recetas ya cuentan la merma de cada insumo, se pasa
        el costo dividido entre 1.05.
      </p>

      <div className="es-tabla-caja">
        <table className="es-tabla">
          <caption>Plato por plato (IGV {esc.formal ? `${IGV[esc.anio] ?? 18} %` : 'no, informal'})</caption>
          <thead>
            <tr>
              <th>Plato</th>
              <th>Costo porción</th>
              <th>Costo de venta</th>
              <th>Precio</th>
              <th>Margen</th>
              <th>% costo</th>
              <th>Por semana</th>
              <th>Clase</th>
            </tr>
          </thead>
          <tbody>
            {analisis.platos.map((f) => (
              <tr key={f.id}>
                <th>
                  {f.nombre}
                  <span className="es-nota-celda"> · {NOMBRE_TIPO[f.tipo]}</span>
                </th>
                <td>{soles(f.costo_porcion, 2)}</td>
                <td>{f.es_menu ? soles(f.costo_venta, 2) : '—'}</td>
                <td>{f.precio ? soles(f.precio, 2) : '—'}</td>
                <td className={f.margen !== null && f.margen < 0 ? 'es-mal' : undefined}>
                  {f.margen === null ? '—' : soles(f.margen, 2)}
                </td>
                <td>{f.costo_pct === null ? '—' : pct(f.costo_pct, 0)}</td>
                <td>{f.vendidos ?? '—'}</td>
                <td title={f.consejo ?? undefined}>{f.clase ? `${CLASE[f.clase].icono} ${CLASE[f.clase].texto}` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="es-nota">
        Costo de venta de un segundo = su porción + la entrada y el refresco promedio ({soles(analisis.costo_entrada_bebida_promedio, 2)}).
        Margen = precio sin IGV − costo de venta. Las clases se calculan dentro de cada tipo y necesitan precio y ventas
        por semana de al menos dos platos.
      </p>

      <Cuadrante filas={analisis.platos.filter((f) => f.tipo === 'segundo')} />
      <ul className="es-consejos">
        {analisis.platos
          .filter((f) => f.clase)
          .map((f) => (
            <li key={f.id}>
              <strong>
                {CLASE[f.clase!].icono} {f.nombre}:
              </strong>{' '}
              {f.consejo}
            </li>
          ))}
      </ul>

      {analisis.pareto.length > 0 && (
        <>
          <div className="es-tabla-caja">
            <table className="es-tabla">
              <caption>En qué se va la plata de las compras</caption>
              <thead>
                <tr>
                  <th>Insumo</th>
                  <th>A la semana</th>
                  <th>Parte</th>
                  <th>Acumulado</th>
                  <th>Si sube 10 %, el menú sube</th>
                </tr>
              </thead>
              <tbody>
                {analisis.pareto.map((p) => (
                  <tr key={p.insumo_id}>
                    <th>{p.insumo}</th>
                    <td>{soles(p.gasto_semana)}</td>
                    <td>
                      <span className="es-barrita" style={{ width: `${Math.max(2, p.parte * 100)}%` }} /> {pct(p.parte, 0)}
                    </td>
                    <td>{pct(p.acumulado, 0)}</td>
                    <td>{soles(p.menu_mas_10pct, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <section className="es-formulario">
            <h2>¿Y si sube un insumo?</h2>
            <select value={elegido} onChange={(e) => setElegido(Number(e.target.value))}>
              {analisis.pareto.map((p) => (
                <option key={p.insumo_id} value={p.insumo_id}>
                  {p.insumo}
                </option>
              ))}
            </select>
            <Barra etiqueta="Sube" valor={alza} min={0.05} max={1} paso={0.05} onChange={setAlza} formato={(v) => pct(v, 0)} />
            <div className="es-datos">
              <Dato titulo="El menú promedio cuesta más" valor={soles(subeMenu, 2)} />
              <Dato
                titulo={`Al mes (${esc.q} menús × ${esc.dias} días)`}
                valor={`−${soles(subeMes)}`}
                tono="mal"
                nota="de utilidad, si no subes el precio"
              />
            </div>
          </section>
        </>
      )}
    </div>
  )
}

// ---------------- Panel ----------------

export function PanelPlatos({ esc, onUsarCosto, onError }: Props) {
  const [vista, setVista] = useState<'analisis' | 'platos' | 'insumos'>('analisis')
  const [insumos, setInsumos] = useState<Insumo[]>([])
  const [platos, setPlatos] = useState<Plato[]>([])
  const [analisis, setAnalisis] = useState<AnalisisPlatos | null>(null)

  const igv = IGV[esc.anio] ?? 18
  const recargar = useCallback(() => {
    api.insumos().then(setInsumos).catch(onError)
    api.platos().then(setPlatos).catch(onError)
    api.analisis(igv, esc.formal).then(setAnalisis).catch(onError)
  }, [igv, esc.formal, onError])
  useEffect(recargar, [recargar])

  return (
    <div className="es-platos">
      <Chips
        valor={vista}
        onChange={setVista}
        opciones={[
          { valor: 'analisis', texto: 'Análisis' },
          { valor: 'platos', texto: `Platos (${platos.length})` },
          { valor: 'insumos', texto: `Insumos (${insumos.length})` },
        ]}
      />
      {vista === 'analisis' &&
        (analisis ? <Analisis analisis={analisis} esc={esc} onUsarCosto={onUsarCosto} /> : <p className="es-nota">Calculando…</p>)}
      {vista === 'platos' && <Platos platos={platos} insumos={insumos} recargar={recargar} />}
      {vista === 'insumos' && <Insumos insumos={insumos} recargar={recargar} onError={onError} />}
    </div>
  )
}
