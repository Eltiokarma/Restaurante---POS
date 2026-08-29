import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, clearAdminToken, getAdminToken, setAdminToken, soles, NOMBRE_CATEGORIA } from '../api'
import type { CajaEstado, ConfigOut, DatosLocal, Insumo, MesaEstado, MovimientoKardex, OrdenOut, Plato, PlantillaMenuIn, StatsOut, VozPanel } from '../api'
import { Ticket } from '../components/Ticket'

type Tab = 'resumen' | 'menu' | 'ordenes' | 'insumos' | 'cancelaciones' | 'voz' | 'config'

interface PlatoEditable {
  id?: number
  nombre: string
  categoria: string
  precio: string // como texto mientras se edita
  activo_hoy: boolean
  sale_al_momento: boolean
  sinonimos: string[]
}

export function Admin() {
  const [logueado, setLogueado] = useState(() => getAdminToken() !== '')
  const [tab, setTab] = useState<Tab>('resumen')

  if (!logueado) {
    return <AdminLogin onOk={() => setLogueado(true)} />
  }

  return (
    <div className="pantalla-admin">
      <header className="admin-cabecera">
        <h1>⚙️ Administración</h1>
        <nav className="admin-tabs">
          <button className={tab === 'resumen' ? 'activa' : ''} onClick={() => setTab('resumen')}>Resumen</button>
          <button className={tab === 'menu' ? 'activa' : ''} onClick={() => setTab('menu')}>Menú del día</button>
          <button className={tab === 'ordenes' ? 'activa' : ''} onClick={() => setTab('ordenes')}>Órdenes de hoy</button>
          <button className={tab === 'insumos' ? 'activa' : ''} onClick={() => setTab('insumos')}>Insumos</button>
          <button className={tab === 'cancelaciones' ? 'activa' : ''} onClick={() => setTab('cancelaciones')}>Cancelaciones</button>
          <button className={tab === 'voz' ? 'activa' : ''} onClick={() => setTab('voz')}>Voz</button>
          <button className={tab === 'config' ? 'activa' : ''} onClick={() => setTab('config')}>Configuración</button>
        </nav>
        <button
          className="boton-salir"
          onClick={() => {
            clearAdminToken()
            setLogueado(false)
          }}
        >
          Salir
        </button>
      </header>
      <main className="admin-contenido">
        {tab === 'resumen' && <TabResumen onSesionVencida={() => setLogueado(false)} />}
        {tab === 'menu' && <TabMenu onSesionVencida={() => setLogueado(false)} />}
        {tab === 'ordenes' && <TabOrdenes />}
        {tab === 'insumos' && <TabInsumos onSesionVencida={() => setLogueado(false)} />}
        {tab === 'cancelaciones' && <TabCancelaciones onSesionVencida={() => setLogueado(false)} />}
        {tab === 'voz' && <TabVoz onSesionVencida={() => setLogueado(false)} />}
        {tab === 'config' && <TabConfig onSesionVencida={() => setLogueado(false)} />}
      </main>
    </div>
  )
}

function manejarError(e: unknown, onSesionVencida: () => void): string {
  if (e instanceof ApiError && e.status === 401) {
    clearAdminToken()
    onSesionVencida()
    return 'Sesión vencida, entra de nuevo'
  }
  return e instanceof Error ? e.message : 'Error inesperado'
}

function AdminLogin({ onOk }: { onOk: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const entrar = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const { token } = await api.login(password)
      setAdminToken(token)
      onOk()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error de conexión')
    }
  }

  return (
    <div className="pantalla-admin admin-login">
      <form onSubmit={entrar} className="login-caja">
        <h1>⚙️ Administración</h1>
        <input
          type="password"
          placeholder="Contraseña"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
        />
        {error && <div className="banner-error">{error}</div>}
        <button type="submit" className="boton-grande boton-primario">Entrar</button>
      </form>
    </div>
  )
}

// ---------- Resumen del día ----------

function formatearDuracion(seg: number | null): string {
  if (seg === null) return '—'
  if (seg < 60) return `${seg} s`
  return `${Math.floor(seg / 60)} min ${seg % 60} s`
}

type Periodo = 'hoy' | '7' | '30'

const NOMBRE_PERIODO: Record<Periodo, string> = {
  hoy: 'hoy',
  '7': 'últimos 7 días',
  '30': 'últimos 30 días',
}

function fechaLocalISO(diasAtras: number): string {
  const d = new Date()
  d.setDate(d.getDate() - diasAtras)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function rangoDe(periodo: Periodo): { desde: string; hasta: string } {
  const hasta = fechaLocalISO(0)
  return { desde: periodo === 'hoy' ? hasta : fechaLocalISO(parseInt(periodo) - 1), hasta }
}

function TabResumen({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [periodo, setPeriodo] = useState<Periodo>('hoy')
  const [stats, setStats] = useState<StatsOut | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const cargar = () => {
      const consulta =
        periodo === 'hoy'
          ? api.statsHoy()
          : api.statsRango(rangoDe(periodo).desde, rangoDe(periodo).hasta)
      consulta.then(setStats).catch((e) => setError(manejarError(e, onSesionVencida)))
    }
    cargar()
    const intervalo = window.setInterval(cargar, 30_000)
    return () => window.clearInterval(intervalo)
  }, [periodo, onSesionVencida])

  if (error) return <div className="banner-error">{error}</div>
  if (!stats) return <p>Cargando…</p>

  const maxCantidad = Math.max(1, ...stats.ventas_por_plato.map((v) => v.cantidad))
  const maxHora = Math.max(1, ...stats.ordenes_por_hora.map((h) => h.cantidad))
  const maxDia = Math.max(1, ...stats.ventas_por_dia.map((d) => d.total))

  const descargar = () => {
    const { desde, hasta } = rangoDe(periodo)
    api.descargarVentasCsv(desde, hasta).catch(() => setError('No se pudo descargar el CSV'))
  }

  return (
    <div>
      <div className="admin-acciones">
        {(['hoy', '7', '30'] as Periodo[]).map((p) => (
          <button key={p} className={periodo === p ? 'boton-primario' : ''} onClick={() => setPeriodo(p)}>
            {p === 'hoy' ? 'Hoy' : `Últimos ${p} días`}
          </button>
        ))}
        <button onClick={descargar}>⬇️ Descargar CSV ({NOMBRE_PERIODO[periodo]})</button>
      </div>

      <div className="tiles-resumen">
        <div className="tile">
          <span className="tile-etiqueta">Total vendido ({NOMBRE_PERIODO[periodo]})</span>
          <span className="tile-valor">{soles(stats.total_vendido)}</span>
        </div>
        <div className="tile">
          <span className="tile-etiqueta">Órdenes</span>
          <span className="tile-valor">{stats.num_ordenes}</span>
        </div>
        <div className="tile">
          <span className="tile-etiqueta">Tiempo promedio por pedido</span>
          <span className="tile-valor">{formatearDuracion(stats.duracion_promedio_seg)}</span>
          <span className="tile-detalle">de tocar la pantalla a confirmar</span>
        </div>
        <div className="tile">
          <span className="tile-etiqueta">Cancelaciones en la ventana</span>
          <span className="tile-valor">{stats.num_cancelaciones}</span>
          <span className="tile-detalle">
            {stats.num_cancelaciones > 0
              ? `${(stats.tasa_cancelacion * 100).toFixed(1)}% de los intentos — ${soles(stats.total_cancelado)}`
              : 'ninguna hoy 🎉'}
          </span>
        </div>
      </div>

      <h3 className="subtitulo-resumen">Ventas por plato</h3>
      {stats.ventas_por_plato.length === 0 ? (
        <p className="nota-admin">Todavía no hay ventas hoy.</p>
      ) : (
        <table className="tabla-admin tabla-resumen">
          <thead>
            <tr>
              <th>Plato</th>
              <th className="col-cantidad">Cantidad</th>
              <th></th>
              <th className="col-total">Total</th>
            </tr>
          </thead>
          <tbody>
            {stats.ventas_por_plato.map((v) => (
              <tr key={v.nombre}>
                <td>{v.nombre}</td>
                <td className="col-cantidad">{v.cantidad}</td>
                <td className="celda-barra">
                  <div className="barra-proporcion" style={{ width: `${(v.cantidad / maxCantidad) * 100}%` }} />
                </td>
                <td className="col-total">{soles(v.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {periodo !== 'hoy' && stats.ventas_por_dia.length > 0 && (
        <>
          <h3 className="subtitulo-resumen">Ventas por día</h3>
          <div className="barras-horas">
            {stats.ventas_por_dia.map((d) => (
              <div
                className="barra-hora barra-dia"
                key={d.fecha}
                title={`${d.fecha}: ${d.ordenes} órdenes — ${soles(d.total)}`}
              >
                <span className="barra-hora-valor">{soles(d.total)}</span>
                <div className="barra-hora-relleno" style={{ height: `${(d.total / maxDia) * 100}%` }} />
                <span className="barra-hora-etiqueta">{d.fecha.slice(5)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <HistorialCierres onSesionVencida={onSesionVencida} />

      {stats.ordenes_por_hora.length > 0 && (
        <>
          <h3 className="subtitulo-resumen">Órdenes por hora{periodo !== 'hoy' ? ' (acumulado del período)' : ''}</h3>
          <div className="barras-horas">
            {stats.ordenes_por_hora.map((h) => (
              <div className="barra-hora" key={h.hora} title={`${h.cantidad} órdenes entre ${h.hora}:00 y ${h.hora}:59`}>
                <span className="barra-hora-valor">{h.cantidad}</span>
                <div className="barra-hora-relleno" style={{ height: `${(h.cantidad / maxHora) * 100}%` }} />
                <span className="barra-hora-etiqueta">{h.hora}:00</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// Movimiento de caja de todos los días (últimos 30 cierres)
function HistorialCierres({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [cierres, setCierres] = useState<CajaEstado[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.cierresHistorial()
      .then((d) => setCierres(d.cierres))
      .catch((e) => setError(manejarError(e, onSesionVencida)))
  }, [onSesionVencida])

  if (error) return <div className="banner-error">{error}</div>
  if (cierres.length === 0) return null

  return (
    <>
      <h3 className="subtitulo-resumen">Cierres de caja (últimos 30 días)</h3>
      <table className="tabla-admin">
        <thead>
          <tr>
            <th>Fecha</th>
            <th className="col-cantidad">Fondo</th>
            <th className="col-cantidad">💵 Efectivo</th>
            <th className="col-cantidad">💳 Tarjeta</th>
            <th className="col-cantidad">📱 Yape</th>
            <th className="col-cantidad">Contado</th>
            <th className="col-total">Diferencia</th>
          </tr>
        </thead>
        <tbody>
          {cierres.map((c) => (
            <tr key={c.fecha}>
              <td>{c.fecha}{!c.cerrada && ' (sin cerrar)'}</td>
              <td className="col-cantidad">{soles(c.monto_apertura ?? 0)}</td>
              <td className="col-cantidad">{soles(c.ventas_efectivo)}</td>
              <td className="col-cantidad">{soles(c.ventas_tarjeta)}</td>
              <td className="col-cantidad">{soles(c.ventas_yape)}</td>
              <td className="col-cantidad">{c.monto_contado != null ? soles(c.monto_contado) : '—'}</td>
              <td className={`col-total ${(c.diferencia ?? 0) < 0 ? 'stock-negativo' : ''}`}>
                {c.diferencia != null
                  ? c.diferencia === 0 ? '🎯 exacto' : soles(c.diferencia)
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

// ---------- Menú del día ----------

function TabMenu({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [platos, setPlatos] = useState<PlatoEditable[]>([])
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')

  const aEditable = (p: Plato): PlatoEditable => ({
    id: p.id,
    nombre: p.nombre,
    categoria: p.categoria,
    precio: p.precio.toFixed(2),
    activo_hoy: p.activo_hoy,
    sale_al_momento: p.sale_al_momento ?? false,
    sinonimos: p.sinonimos ?? [],
  })

  const cargar = useCallback(async () => {
    try {
      const data = await api.menuHoy()
      setPlatos(data.platos.map(aEditable))
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }, [onSesionVencida])

  useEffect(() => {
    cargar()
  }, [cargar])

  const editar = (idx: number, cambios: Partial<PlatoEditable>) => {
    setPlatos((prev) => prev.map((p, i) => (i === idx ? { ...p, ...cambios } : p)))
  }

  const agregar = () => {
    setPlatos((prev) => [
      ...prev,
      { nombre: '', categoria: 'fondo', precio: '', activo_hoy: true, sale_al_momento: false, sinonimos: [] },
    ])
  }

  const quitar = (idx: number) => {
    setPlatos((prev) => prev.filter((_, i) => i !== idx))
  }

  const cargarAyer = async () => {
    setError('')
    setMensaje('')
    try {
      const data = await api.menuAnterior()
      if (data.platos.length === 0) {
        setMensaje('No hay un menú anterior guardado todavía.')
        return
      }
      setPlatos(data.platos.map((p) => ({ ...aEditable(p), activo_hoy: true })))
      setMensaje(`Menú del ${data.fecha} cargado. Ajusta lo que necesites y guarda.`)
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const cargarDelCatalogo = async () => {
    setError('')
    setMensaje('')
    try {
      const data = await api.catalogo()
      const actuales = new Set(platos.filter((p) => p.id).map((p) => p.id))
      const nuevos = data.platos.filter((p) => !actuales.has(p.id))
      setPlatos((prev) => [...prev, ...nuevos.map((p) => ({ ...aEditable(p), activo_hoy: false }))])
      setMensaje('Catálogo cargado: activa los platos que van hoy.')
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const guardar = async () => {
    setError('')
    setMensaje('')
    // Un plato con nombre pero precio inválido no debe descartarse en
    // silencio (se desactivaría sin que el dueño se entere)
    const sinPrecio = platos.filter((p) => p.nombre.trim() !== '' && !(parseFloat(p.precio) > 0))
    if (sinPrecio.length > 0) {
      setError(`Falta el precio de: ${sinPrecio.map((p) => p.nombre.trim()).join(', ')}`)
      return
    }
    const validos = platos.filter((p) => p.nombre.trim() !== '' && parseFloat(p.precio) > 0)
    try {
      const data = await api.guardarMenu(
        validos.map((p) => ({
          id: p.id,
          nombre: p.nombre.trim(),
          categoria: p.categoria,
          precio: parseFloat(p.precio),
          activo_hoy: p.activo_hoy,
          sale_al_momento: p.sale_al_momento,
          sinonimos: p.sinonimos,
        })),
      )
      setPlatos(data.platos.map(aEditable))
      setMensaje('Menú guardado ✔ (la terminal lo verá en el próximo refresco)')
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  return (
    <div>
      <div className="admin-acciones">
        <button onClick={agregar}>+ Agregar plato</button>
        <button onClick={cargarAyer}>Cargar menú de ayer</button>
        <button onClick={cargarDelCatalogo}>Ver catálogo histórico</button>
        <button className="boton-primario" onClick={guardar}>💾 Guardar menú del día</button>
      </div>
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {error && <div className="banner-error">{error}</div>}
      <table className="tabla-admin">
        <thead>
          <tr>
            <th>Plato</th>
            <th>Categoría</th>
            <th>Precio S/</th>
            <th>Sinónimos (para la voz)</th>
            <th title="Se prepara al pedido (bistec frito): obliga entrega por tiempos">Al momento</th>
            <th>Disponible hoy</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {platos.map((p, idx) => (
            <tr key={p.id ?? `nuevo-${idx}`}>
              <td>
                <input value={p.nombre} onChange={(e) => editar(idx, { nombre: e.target.value })} placeholder="Nombre del plato" />
              </td>
              <td>
                <select value={p.categoria} onChange={(e) => editar(idx, { categoria: e.target.value })}>
                  {Object.entries(NOMBRE_CATEGORIA).map(([valor, texto]) => (
                    <option key={valor} value={valor}>{texto}</option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  type="number"
                  step="0.50"
                  min="0"
                  value={p.precio}
                  onChange={(e) => editar(idx, { precio: e.target.value })}
                  placeholder="0.00"
                />
              </td>
              <td>
                <ChipsSinonimos
                  sinonimos={p.sinonimos}
                  onCambiar={(sinonimos) => editar(idx, { sinonimos })}
                />
              </td>
              <td className="celda-centro">
                <input
                  type="checkbox"
                  checked={p.sale_al_momento}
                  onChange={(e) => editar(idx, { sale_al_momento: e.target.checked })}
                />
              </td>
              <td className="celda-centro">
                <input
                  type="checkbox"
                  checked={p.activo_hoy}
                  onChange={(e) => editar(idx, { activo_hoy: e.target.checked })}
                />
              </td>
              <td>
                {p.id === undefined && (
                  <button className="boton-quitar" onClick={() => quitar(idx)}>✕</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="nota-admin">
        Para agotar un plato a mitad de servicio: desmarca "Disponible hoy" y guarda. Desaparece de la
        terminal en el siguiente refresco (máx. 30 segundos).
      </p>
      <EditorPlantillas onSesionVencida={onSesionVencida} />
    </div>
  )
}

// ---------- Menús encadenados (plantillas) ----------

interface TiempoEditable {
  rotulo: string
  obligatorio: boolean
  precio_extra: string // como texto mientras se edita
  alternativas: { plato_id: number; recargo: string }[]
}

interface PlantillaEditable {
  id?: number
  nombre: string
  precio: string
  activo_hoy: boolean
  tiempos: TiempoEditable[]
}

const TIEMPOS_SUGERIDOS = ['Entrada o sopa', 'Segundo', 'Refresco', 'Postre']

function EditorPlantillas({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [plantillas, setPlantillas] = useState<PlantillaEditable[]>([])
  const [catalogo, setCatalogo] = useState<Plato[]>([])
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')

  const cargar = useCallback(async () => {
    try {
      const [datosPlantillas, datosCatalogo] = await Promise.all([
        api.plantillas(),
        api.catalogo(),
      ])
      setCatalogo(datosCatalogo.platos)
      setPlantillas(
        datosPlantillas.plantillas.map((p) => ({
          id: p.id,
          nombre: p.nombre,
          precio: p.precio.toFixed(2),
          activo_hoy: p.activo_hoy,
          tiempos: p.tiempos.map((t) => ({
            rotulo: t.rotulo,
            obligatorio: t.obligatorio,
            precio_extra: t.precio_extra > 0 ? t.precio_extra.toFixed(2) : '',
            alternativas: t.alternativas.map((a) => ({
              plato_id: a.plato_id,
              recargo: a.recargo > 0 ? a.recargo.toFixed(2) : '',
            })),
          })),
        })),
      )
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }, [onSesionVencida])

  useEffect(() => {
    cargar()
  }, [cargar])

  const editar = (idx: number, cambios: Partial<PlantillaEditable>) => {
    setPlantillas((prev) => prev.map((p, i) => (i === idx ? { ...p, ...cambios } : p)))
  }

  const editarTiempo = (idx: number, t: number, cambios: Partial<TiempoEditable>) => {
    setPlantillas((prev) =>
      prev.map((p, i) =>
        i === idx
          ? { ...p, tiempos: p.tiempos.map((x, j) => (j === t ? { ...x, ...cambios } : x)) }
          : p,
      ),
    )
  }

  const alternarPlato = (idx: number, t: number, platoId: number) => {
    setPlantillas((prev) =>
      prev.map((p, i) => {
        if (i !== idx) return p
        const tiempos = p.tiempos.map((x, j) => {
          if (j !== t) return x
          const ya = x.alternativas.some((a) => a.plato_id === platoId)
          return {
            ...x,
            alternativas: ya
              ? x.alternativas.filter((a) => a.plato_id !== platoId)
              : [...x.alternativas, { plato_id: platoId, recargo: '' }],
          }
        })
        return { ...p, tiempos }
      }),
    )
  }

  const agregarPlantilla = () => {
    setPlantillas((prev) => [
      ...prev,
      {
        nombre: 'Menú del día',
        precio: '',
        activo_hoy: true,
        tiempos: [
          { rotulo: 'Entrada o sopa', obligatorio: true, precio_extra: '3.00', alternativas: [] },
          { rotulo: 'Segundo', obligatorio: true, precio_extra: '', alternativas: [] },
        ],
      },
    ])
  }

  const guardar = async () => {
    setError('')
    setMensaje('')
    const validas = plantillas.filter((p) => p.nombre.trim() !== '')
    const sinPrecio = validas.filter((p) => !(parseFloat(p.precio) > 0))
    if (sinPrecio.length > 0) {
      setError(`Falta el precio de: ${sinPrecio.map((p) => p.nombre.trim()).join(', ')}`)
      return
    }
    const sinAlternativas = validas.filter((p) =>
      p.tiempos.some((t) => t.rotulo.trim() !== '' && t.alternativas.length === 0),
    )
    if (sinAlternativas.length > 0) {
      setError(
        `Cada tiempo necesita al menos un plato: revisa ${sinAlternativas
          .map((p) => p.nombre.trim())
          .join(', ')}`,
      )
      return
    }
    const payload: PlantillaMenuIn[] = validas.map((p) => ({
      id: p.id,
      nombre: p.nombre.trim(),
      precio: parseFloat(p.precio),
      activo_hoy: p.activo_hoy,
      tiempos: p.tiempos
        .filter((t) => t.rotulo.trim() !== '')
        .map((t) => ({
          rotulo: t.rotulo.trim(),
          obligatorio: t.obligatorio,
          precio_extra: parseFloat(t.precio_extra) > 0 ? parseFloat(t.precio_extra) : 0,
          alternativas: t.alternativas.map((a) => ({
            plato_id: a.plato_id,
            recargo: parseFloat(a.recargo) > 0 ? parseFloat(a.recargo) : 0,
          })),
        })),
    }))
    try {
      await api.guardarPlantillas(payload)
      await cargar()
      setMensaje('Menús guardados ✔ (la terminal los verá en el próximo refresco)')
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const nombreDe = (platoId: number) =>
    catalogo.find((p) => p.id === platoId)?.nombre ?? `#${platoId}`

  return (
    <div className="editor-plantillas">
      <h2 className="titulo-categoria">Menús (combo con tiempos)</h2>
      <p className="nota-admin">
        El menú se cobra por SU precio, no por la suma de los platos. "Extra S/" es el precio de
        una porción adicional de ese tiempo pedida junto al menú (déjalo vacío si no se ofrece);
        "recargo" es lo que suma elegir ese plato dentro del menú.
      </p>
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {error && <div className="banner-error">{error}</div>}
      {plantillas.map((p, idx) => (
        <div className="plantilla-editor" key={p.id ?? `nueva-${idx}`}>
          <div className="plantilla-cabecera">
            <input
              value={p.nombre}
              onChange={(e) => editar(idx, { nombre: e.target.value })}
              placeholder="Nombre del menú"
            />
            <label>
              S/{' '}
              <input
                type="number" step="0.50" min="0" className="input-precio"
                value={p.precio}
                onChange={(e) => editar(idx, { precio: e.target.value })}
                placeholder="11.00"
              />
            </label>
            <label>
              <input
                type="checkbox"
                checked={p.activo_hoy}
                onChange={(e) => editar(idx, { activo_hoy: e.target.checked })}
              />{' '}
              Se vende hoy
            </label>
            <button
              className="boton-quitar"
              onClick={() => setPlantillas((prev) => prev.filter((_, i) => i !== idx))}
              title="Quitar este menú (se retira al guardar; las ventas pasadas no cambian)"
            >
              ✕
            </button>
          </div>
          {p.tiempos.map((t, ti) => (
            <div className="plantilla-tiempo" key={ti}>
              <div className="plantilla-tiempo-fila">
                <span className="tiempo-orden">{ti + 1}</span>
                <input
                  value={t.rotulo}
                  onChange={(e) => editarTiempo(idx, ti, { rotulo: e.target.value })}
                  placeholder={TIEMPOS_SUGERIDOS[ti] ?? 'Rótulo del tiempo'}
                />
                <label title="Precio de una porción adicional pedida con el menú">
                  Extra S/{' '}
                  <input
                    type="number" step="0.50" min="0" className="input-precio"
                    value={t.precio_extra}
                    onChange={(e) => editarTiempo(idx, ti, { precio_extra: e.target.value })}
                    placeholder="—"
                  />
                </label>
                <button
                  className="boton-quitar"
                  onClick={() =>
                    editar(idx, { tiempos: p.tiempos.filter((_, j) => j !== ti) })
                  }
                >
                  ✕
                </button>
              </div>
              <div className="chips-sinonimos">
                {t.alternativas.map((a) => (
                  <span className="chip" key={a.plato_id}>
                    {nombreDe(a.plato_id)}
                    <label title="Recargo por elegir este plato en el menú">
                      {' '}+S/{' '}
                      <input
                        type="number" step="0.50" min="0" className="input-recargo"
                        value={a.recargo}
                        onChange={(e) =>
                          editarTiempo(idx, ti, {
                            alternativas: t.alternativas.map((x) =>
                              x.plato_id === a.plato_id ? { ...x, recargo: e.target.value } : x,
                            ),
                          })
                        }
                        placeholder="0"
                      />
                    </label>
                    <button onClick={() => alternarPlato(idx, ti, a.plato_id)} aria-label={`Quitar ${nombreDe(a.plato_id)}`}>✕</button>
                  </span>
                ))}
                <select
                  className="chip-input"
                  value=""
                  onChange={(e) => {
                    if (e.target.value) alternarPlato(idx, ti, Number(e.target.value))
                  }}
                >
                  <option value="">+ plato…</option>
                  {catalogo
                    .filter((pl) => !t.alternativas.some((a) => a.plato_id === pl.id))
                    .map((pl) => (
                      <option key={pl.id} value={pl.id}>
                        {pl.nombre}
                      </option>
                    ))}
                </select>
              </div>
            </div>
          ))}
          <button
            onClick={() =>
              editar(idx, {
                tiempos: [
                  ...p.tiempos,
                  {
                    rotulo: TIEMPOS_SUGERIDOS[p.tiempos.length] ?? '',
                    obligatorio: true,
                    precio_extra: '',
                    alternativas: [],
                  },
                ],
              })
            }
          >
            + Agregar tiempo
          </button>
        </div>
      ))}
      <div className="admin-acciones">
        <button onClick={agregarPlantilla}>+ Agregar menú</button>
        <button className="boton-primario" onClick={guardar}>💾 Guardar menús</button>
      </div>
    </div>
  )
}

// Editor de sinónimos (chips): la herramienta de mejora continua de la voz
function ChipsSinonimos({
  sinonimos,
  onCambiar,
}: {
  sinonimos: string[]
  onCambiar: (s: string[]) => void
}) {
  const [texto, setTexto] = useState('')

  const agregar = () => {
    const nuevo = texto.trim().toLowerCase()
    if (nuevo && !sinonimos.includes(nuevo)) onCambiar([...sinonimos, nuevo])
    setTexto('')
  }

  return (
    <div className="chips-sinonimos">
      {sinonimos.map((s) => (
        <span className="chip" key={s}>
          {s}
          <button onClick={() => onCambiar(sinonimos.filter((x) => x !== s))} aria-label={`Quitar ${s}`}>✕</button>
        </span>
      ))}
      <input
        className="chip-input"
        value={texto}
        placeholder="+ sinónimo"
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            agregar()
          }
        }}
        onBlur={agregar}
      />
    </div>
  )
}

// ---------- Panel de voz ----------

function TabVoz({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [panel, setPanel] = useState<VozPanel | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const cargar = () =>
      api.vozLogsHoy().then(setPanel).catch((e) => setError(manejarError(e, onSesionVencida)))
    cargar()
    const intervalo = window.setInterval(cargar, 30_000)
    return () => window.clearInterval(intervalo)
  }, [onSesionVencida])

  if (error) return <div className="banner-error">{error}</div>
  if (!panel) return <p>Cargando…</p>

  const m = panel.metricas
  return (
    <div>
      <p className="nota-admin">
        Cada semana revisa los <strong>corregidos y descartados</strong>: las palabras que el
        sistema no entendió se agregan como sinónimos en Menú del día. Así la precisión sube
        semana a semana. El toggle de encendido está en Configuración.
      </p>
      <div className="tiles-resumen">
        <div className="tile">
          <span className="tile-etiqueta">Pedidos por voz hoy</span>
          <span className="tile-valor">{m.total}</span>
        </div>
        <div className="tile">
          <span className="tile-etiqueta">Aceptado sin corrección</span>
          <span className="tile-valor">{m.pct_aceptado}%</span>
        </div>
        <div className="tile">
          <span className="tile-etiqueta">Corregido / Descartado</span>
          <span className="tile-valor">{m.pct_corregido}% / {m.pct_descartado}%</span>
        </div>
        <div className="tile">
          <span className="tile-etiqueta">Latencia promedio</span>
          <span className="tile-valor">
            {m.latencia_promedio_ms !== null ? `${(m.latencia_promedio_ms / 1000).toFixed(1)} s` : '—'}
          </span>
        </div>
        <div className="tile">
          <span className="tile-etiqueta">Costo estimado del día</span>
          <span className="tile-valor">≈ S/ {m.costo_dia_soles.toFixed(2)}</span>
          <span className="tile-detalle">${m.costo_dia_usd.toFixed(4)} USD</span>
        </div>
      </div>

      <table className="tabla-admin">
        <thead>
          <tr>
            <th>Hora</th>
            <th>Transcripción</th>
            <th>Interpretación</th>
            <th>Resultado</th>
            <th>Latencia</th>
          </tr>
        </thead>
        <tbody>
          {panel.logs.map((l) => (
            <tr key={l.id}>
              <td>{l.hora}</td>
              <td>“{l.transcripcion}”</td>
              <td>
                {l.interpretacion.items.map((i) => `${i.cantidad}× #${i.plato_id}`).join(', ') || '—'}
                {l.interpretacion.no_encontrados.length > 0 && (
                  <span className="voz-log-no-encontrados">
                    {' '}(sin match: {l.interpretacion.no_encontrados.join(', ')})
                  </span>
                )}
              </td>
              <td><span className={`etiqueta-estado etiqueta-voz-${l.resultado}`}>{l.resultado}</span></td>
              <td>{(l.latencia_ms / 1000).toFixed(1)} s</td>
            </tr>
          ))}
        </tbody>
      </table>
      {panel.logs.length === 0 && <p className="nota-admin">Sin pedidos por voz hoy.</p>}
    </div>
  )
}

// ---------- Órdenes de hoy ----------

function fechaHoyISO(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function TabOrdenes() {
  const [ordenes, setOrdenes] = useState<OrdenOut[]>([])
  const [totalVendido, setTotalVendido] = useState(0)
  const [ticket, setTicket] = useState<{ orden: OrdenOut; local: DatosLocal } | null>(null)
  // Movimiento de cualquier día, no solo hoy
  const [fecha, setFecha] = useState(fechaHoyISO())

  useEffect(() => {
    const esHoy = fecha === fechaHoyISO()
    const cargar = () =>
      (esHoy ? api.ordenesHoy() : api.ordenesDeDia(fecha))
        .then((data) => {
          setOrdenes(data.ordenes)
          setTotalVendido(data.total_vendido)
        })
        .catch(() => {})
    cargar()
    if (!esHoy) return
    const intervalo = window.setInterval(cargar, 15_000)
    return () => window.clearInterval(intervalo)
  }, [fecha])

  const [avisoReimpresion, setAvisoReimpresion] = useState('')

  // Reimpresión: útil cuando el ticket original no salió (papel, impresora
  // apagada, etc.). En modo "estacion" se reencola para /ticketera; en modo
  // "terminal" se imprime desde esta misma pantalla.
  const reimprimir = async (orden: OrdenOut) => {
    setAvisoReimpresion('')
    try {
      const cfg = await api.config()
      if (cfg.modo_impresion === 'estacion') {
        await api.reimprimirOrden(orden.id)
        setAvisoReimpresion(
          `Ticket #${String(orden.numero_orden_dia).padStart(3, '0')} enviado a la estación de impresión.`,
        )
        return
      }
      setTicket({
        orden,
        local: { nombre: cfg.nombre_local, direccion: cfg.direccion, ruc: cfg.ruc },
      })
    } catch {
      setTicket({ orden, local: { nombre: '', direccion: '', ruc: '' } })
    }
  }

  useEffect(() => {
    if (!ticket) return
    const timer = window.setTimeout(() => {
      window.print()
      setTicket(null)
    }, 150)
    return () => window.clearTimeout(timer)
  }, [ticket])

  return (
    <div>
      <div className="total-dia">
        <label className="selector-fecha">
          Día:{' '}
          <input type="date" value={fecha} max={fechaHoyISO()} onChange={(e) => setFecha(e.target.value)} />
        </label>
        {' '}Total vendido: <strong>{soles(totalVendido)}</strong> ({ordenes.length} órdenes)
      </div>
      {avisoReimpresion && <div className="banner-ok">{avisoReimpresion}</div>}
      <table className="tabla-admin">
        <thead>
          <tr>
            <th>#</th>
            <th>Hora</th>
            <th>Items</th>
            <th>Total</th>
            <th>Estado</th>
            <th>Ticket</th>
          </tr>
        </thead>
        <tbody>
          {ordenes.map((o) => (
            <tr key={o.id}>
              <td>#{String(o.numero_orden_dia).padStart(3, '0')}</td>
              <td>{o.hora}</td>
              <td>
                {[
                  ...o.menus.map(
                    (m) =>
                      `${m.cantidad}× ${m.nombre} (${m.items.map((i) => i.nombre).join(' + ')})`,
                  ),
                  ...o.items.map((i) => `${i.cantidad}× ${i.nombre}`),
                ].join(', ')}
              </td>
              <td>{soles(o.total)}</td>
              <td><span className={`etiqueta-estado etiqueta-${o.estado}`}>{o.estado}</span></td>
              <td>
                <button className="boton-reimprimir" onClick={() => reimprimir(o)} title="Reimprimir ticket">
                  🖨️
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {ordenes.length === 0 && <p className="nota-admin">Todavía no hay órdenes hoy.</p>}
      {ticket && (
        <div className="solo-impresion">
          <Ticket orden={ticket.orden} local={ticket.local} />
        </div>
      )}
    </div>
  )
}

// ---------- Insumos, recetas y kardex ----------

function TabInsumos({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [insumos, setInsumos] = useState<Insumo[]>([])
  const [valorInventario, setValorInventario] = useState(0)
  const [movimientos, setMovimientos] = useState<MovimientoKardex[]>([])
  const [catalogo, setCatalogo] = useState<Plato[]>([])
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')

  // Formularios
  const [nuevo, setNuevo] = useState({ nombre: '', unidad: 'kg', costo: '' })
  const [mov, setMov] = useState({ insumoId: '', tipo: 'compra', cantidad: '', costo: '', nota: '' })
  const [recetaPlato, setRecetaPlato] = useState('')
  const [recetaItems, setRecetaItems] = useState<{ insumo_id: number; cantidad: string }[]>([])
  const [costoPorcion, setCostoPorcion] = useState<number | null>(null)

  const cargar = useCallback(async () => {
    try {
      const [datos, kardex, cat] = await Promise.all([
        api.insumos(),
        api.kardex(),
        api.catalogo(),
      ])
      setInsumos(datos.insumos)
      setValorInventario(datos.valor_inventario)
      setMovimientos(kardex.movimientos)
      setCatalogo(cat.platos)
      setError('')
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }, [onSesionVencida])

  useEffect(() => {
    cargar()
  }, [cargar])

  const crearInsumo = async () => {
    if (!nuevo.nombre.trim()) return
    try {
      await api.crearInsumo(nuevo.nombre.trim(), nuevo.unidad.trim() || 'unidad', parseFloat(nuevo.costo) || 0)
      setNuevo({ nombre: '', unidad: 'kg', costo: '' })
      setMensaje('Insumo creado ✔')
      cargar()
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const registrarMovimiento = async () => {
    const insumoId = parseInt(mov.insumoId)
    const cantidad = parseFloat(mov.cantidad)
    const costo = parseFloat(mov.costo)
    if (!insumoId) {
      setError('Elige el insumo')
      return
    }
    // Ajuste = conteo físico (0 es válido); compra y merma necesitan cantidad > 0
    if (mov.tipo === 'ajuste' ? !(cantidad >= 0) : !(cantidad > 0)) {
      setError(mov.tipo === 'ajuste' ? 'Pon el stock contado (puede ser 0)' : 'Pon una cantidad mayor a 0')
      return
    }
    if (mov.tipo === 'compra' && !(costo > 0)) {
      setError('Pon el costo total pagado por la compra (mayor a 0)')
      return
    }
    try {
      await api.movimientoInsumo(
        insumoId,
        mov.tipo as 'compra' | 'merma' | 'ajuste',
        cantidad,
        mov.tipo === 'compra' ? costo : undefined,
        mov.nota,
      )
      setMov({ insumoId: '', tipo: 'compra', cantidad: '', costo: '', nota: '' })
      setMensaje('Movimiento registrado ✔')
      setError('')
      cargar()
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const cargarReceta = async (platoId: string) => {
    setRecetaPlato(platoId)
    setCostoPorcion(null)
    if (!platoId) {
      setRecetaItems([])
      return
    }
    try {
      const receta = await api.receta(parseInt(platoId))
      setRecetaItems(receta.items.map((i) => ({ insumo_id: i.insumo_id, cantidad: String(i.cantidad) })))
      setCostoPorcion(receta.costo_porcion)
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const guardarReceta = async () => {
    if (!recetaPlato) return
    try {
      const receta = await api.guardarReceta(
        parseInt(recetaPlato),
        recetaItems
          .map((i) => ({ insumo_id: i.insumo_id, cantidad: parseFloat(i.cantidad) || 0 }))
          .filter((i) => i.cantidad > 0),
      )
      setCostoPorcion(receta.costo_porcion)
      setMensaje('Receta guardada ✔ (las ventas descontarán estos insumos)')
      cargar()
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const precioPlato = catalogo.find((p) => p.id === parseInt(recetaPlato))?.precio

  return (
    <div>
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {error && <div className="banner-error">{error}</div>}

      <h3 className="subtitulo-resumen">Inventario (valor: {soles(valorInventario)})</h3>
      <table className="tabla-admin">
        <thead>
          <tr><th>Insumo</th><th>Unidad</th><th className="col-cantidad">Stock</th><th className="col-cantidad">Costo unit.</th><th className="col-total">Valor</th></tr>
        </thead>
        <tbody>
          {insumos.map((i) => (
            <tr key={i.id}>
              <td>{i.nombre}</td>
              <td>{i.unidad}</td>
              <td className={`col-cantidad ${i.stock_actual < 0 ? 'stock-negativo' : ''}`}>{i.stock_actual}</td>
              <td className="col-cantidad">{soles(i.costo_unitario)}</td>
              <td className="col-total">{soles(i.valor)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {insumos.length === 0 && <p className="nota-admin">Todavía no hay insumos. Crea el primero abajo.</p>}

      <div className="formularios-insumos">
        <div className="form-insumo">
          <h3 className="subtitulo-resumen">+ Nuevo insumo</h3>
          <input placeholder="Nombre (Papa, Arroz…)" value={nuevo.nombre}
                 onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} />
          <input placeholder="Unidad (kg, l, unidad)" value={nuevo.unidad}
                 onChange={(e) => setNuevo({ ...nuevo, unidad: e.target.value })} />
          <input type="number" step="0.1" min="0" placeholder="Costo por unidad (opcional)"
                 value={nuevo.costo} onChange={(e) => setNuevo({ ...nuevo, costo: e.target.value })} />
          <button className="boton-primario" onClick={crearInsumo}>Crear</button>
        </div>

        <div className="form-insumo">
          <h3 className="subtitulo-resumen">Registrar movimiento</h3>
          <select value={mov.insumoId} onChange={(e) => setMov({ ...mov, insumoId: e.target.value })}>
            <option value="">— Insumo —</option>
            {insumos.map((i) => <option key={i.id} value={i.id}>{i.nombre} ({i.unidad})</option>)}
          </select>
          <select value={mov.tipo} onChange={(e) => setMov({ ...mov, tipo: e.target.value })}>
            <option value="compra">🛒 Compra (entra stock)</option>
            <option value="merma">🗑 Merma (se perdió)</option>
            <option value="ajuste">📋 Ajuste (conteo físico)</option>
          </select>
          <input type="number" step="0.01" min="0"
                 placeholder={mov.tipo === 'ajuste' ? 'Stock contado' : 'Cantidad'}
                 value={mov.cantidad} onChange={(e) => setMov({ ...mov, cantidad: e.target.value })} />
          {mov.tipo === 'compra' && (
            <input type="number" step="0.1" min="0" placeholder="Costo total S/ de la compra"
                   value={mov.costo} onChange={(e) => setMov({ ...mov, costo: e.target.value })} />
          )}
          <input placeholder="Nota (opcional)" value={mov.nota}
                 onChange={(e) => setMov({ ...mov, nota: e.target.value })} />
          <button className="boton-primario" onClick={registrarMovimiento}>Registrar</button>
        </div>

        <div className="form-insumo">
          <h3 className="subtitulo-resumen">Receta por plato</h3>
          <select value={recetaPlato} onChange={(e) => cargarReceta(e.target.value)}>
            <option value="">— Plato —</option>
            {catalogo.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
          </select>
          {recetaPlato && (
            <>
              {recetaItems.map((item, idx) => (
                <div className="receta-fila" key={idx}>
                  <select
                    value={item.insumo_id}
                    onChange={(e) => setRecetaItems((prev) =>
                      prev.map((x, i) => (i === idx ? { ...x, insumo_id: parseInt(e.target.value) } : x)))}
                  >
                    {insumos.map((i) => <option key={i.id} value={i.id}>{i.nombre}</option>)}
                  </select>
                  <input type="number" step="0.01" min="0" placeholder="Cant./porción"
                         value={item.cantidad}
                         onChange={(e) => setRecetaItems((prev) =>
                           prev.map((x, i) => (i === idx ? { ...x, cantidad: e.target.value } : x)))} />
                  <button className="boton-quitar"
                          onClick={() => setRecetaItems((prev) => prev.filter((_, i) => i !== idx))}>✕</button>
                </div>
              ))}
              <button
                disabled={insumos.length === 0}
                onClick={() => setRecetaItems((prev) => [...prev, { insumo_id: insumos[0]?.id ?? 0, cantidad: '' }])}
              >
                + Agregar insumo a la receta
              </button>
              <button className="boton-primario" onClick={guardarReceta}>💾 Guardar receta</button>
              {costoPorcion !== null && (
                <p className="nota-admin">
                  Costo por porción: <strong>{soles(costoPorcion)}</strong>
                  {precioPlato !== undefined && costoPorcion > 0 && (
                    <> · margen: <strong>{soles(precioPlato - costoPorcion)}</strong> ({Math.round((1 - costoPorcion / precioPlato) * 100)}%)</>
                  )}
                </p>
              )}
            </>
          )}
        </div>
      </div>

      <h3 className="subtitulo-resumen">Kardex (últimos 7 días)</h3>
      <table className="tabla-admin">
        <thead>
          <tr><th>Fecha</th><th>Hora</th><th>Insumo</th><th>Tipo</th><th className="col-cantidad">Cantidad</th><th>Referencia</th></tr>
        </thead>
        <tbody>
          {movimientos.map((m) => (
            <tr key={m.id}>
              <td>{m.fecha}</td>
              <td>{m.hora}</td>
              <td>{m.insumo}</td>
              <td>{m.tipo}{m.costo_total != null ? ` (${soles(m.costo_total)})` : ''}</td>
              <td className={`col-cantidad ${m.cantidad < 0 ? 'stock-negativo' : ''}`}>
                {m.cantidad > 0 ? '+' : ''}{m.cantidad} {m.unidad}
              </td>
              <td>{m.referencia}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {movimientos.length === 0 && <p className="nota-admin">Sin movimientos en los últimos 7 días.</p>}
      <p className="nota-admin">
        Las ventas descuentan insumos SOLO en los platos que tienen receta. Un stock en rojo
        significa que se vendió más de lo que el kardex tenía: corrígelo con un ajuste de
        conteo físico.
      </p>
    </div>
  )
}

// ---------- Cancelaciones ----------

function TabCancelaciones({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [cancelaciones, setCancelaciones] = useState<
    { id: number; fecha: string; hora: string; total: number; items: { nombre: string; cantidad: number; precio: number }[] }[]
  >([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.cancelacionesHoy()
      .then((data) => setCancelaciones(data.cancelaciones))
      .catch((e) => setError(manejarError(e, onSesionVencida)))
  }, [onSesionVencida])

  return (
    <div>
      <p className="nota-admin">
        Pedidos cancelados durante la ventana de cancelación. Si son muchos, algo del flujo está
        confundiendo a los clientes.
      </p>
      {error && <div className="banner-error">{error}</div>}
      <table className="tabla-admin">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Hora</th>
            <th>Items</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {cancelaciones.map((c) => (
            <tr key={c.id}>
              <td>{c.fecha}</td>
              <td>{c.hora}</td>
              <td>{c.items.map((i) => `${i.cantidad}× ${i.nombre}`).join(', ')}</td>
              <td>{soles(c.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {cancelaciones.length === 0 && !error && <p className="nota-admin">Sin cancelaciones hoy 🎉</p>}
    </div>
  )
}

// ---------- Configuración ----------

function TabConfig({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [config, setConfig] = useState<ConfigOut | null>(null)
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.config().then(setConfig).catch(() => setError('No se pudo cargar la configuración'))
  }, [])

  if (!config) return <p>{error || 'Cargando…'}</p>

  const guardar = async () => {
    setMensaje('')
    setError('')
    try {
      const actualizada = await api.guardarConfig(config)
      setConfig(actualizada)
      setMensaje('Configuración guardada ✔')
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  return (
    <div className="form-config">
      <label>
        Nombre del local
        <input value={config.nombre_local} onChange={(e) => setConfig({ ...config, nombre_local: e.target.value })} />
      </label>
      <label>
        Dirección
        <input value={config.direccion} onChange={(e) => setConfig({ ...config, direccion: e.target.value })} />
      </label>
      <label>
        RUC (para el ticket)
        <input value={config.ruc} onChange={(e) => setConfig({ ...config, ruc: e.target.value })} />
      </label>
      <label>
        Ventana de cancelación (segundos)
        <input
          type="number"
          min="5"
          max="120"
          value={config.ventana_cancelacion_seg}
          onChange={(e) => setConfig({ ...config, ventana_cancelacion_seg: parseInt(e.target.value) || 30 })}
        />
      </label>
      <label>
        Timeout de inactividad (segundos)
        <input
          type="number"
          min="30"
          max="600"
          value={config.timeout_inactividad_seg}
          onChange={(e) => setConfig({ ...config, timeout_inactividad_seg: parseInt(e.target.value) || 90 })}
        />
      </label>
      <label>
        ¿Dónde se imprimen los tickets?
        <select
          value={config.modo_impresion}
          onChange={(e) =>
            setConfig({ ...config, modo_impresion: e.target.value as 'terminal' | 'estacion' })
          }
        >
          <option value="terminal">En la terminal del cliente (PC con impresora conectada)</option>
          <option value="estacion">Estación de impresión (/ticketera en la PC de la impresora)</option>
        </select>
      </label>
      {config.modo_impresion === 'estacion' && (
        <p className="nota-admin">
          Modo para terminales tablet: abre <strong>/ticketera</strong> en la computadora que tiene
          la impresora conectada y déjala abierta. Los tickets de todas las terminales salen por ahí.
        </p>
      )}
      <label className="config-toggle">
        <input
          type="checkbox"
          checked={config.exigir_caja_abierta}
          onChange={(e) => setConfig({ ...config, exigir_caja_abierta: e.target.checked })}
        />
        🔒 No permitir ventas hasta abrir la caja (fondo inicial)
      </label>
      <label className="config-toggle">
        <input
          type="checkbox"
          checked={config.voz_habilitada}
          onChange={(e) => setConfig({ ...config, voz_habilitada: e.target.checked })}
        />
        🎤 Pedido por voz habilitado (kill switch)
      </label>
      {config.voz_habilitada && !config.voz_disponible && (
        <p className="nota-admin nota-advertencia">
          ⚠ La voz está encendida pero faltan las API keys (OPENAI_API_KEY y ANTHROPIC_API_KEY)
          en el .env del servidor: el botón NO aparecerá en la terminal hasta configurarlas y
          reiniciar.
        </p>
      )}
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {error && <div className="banner-error">{error}</div>}
      <button className="boton-grande boton-primario" onClick={guardar}>💾 Guardar configuración</button>

      <GestorMesas onSesionVencida={onSesionVencida} />
    </div>
  )
}

// ---------- Configuración de mesas ----------

function GestorMesas({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [mesas, setMesas] = useState<MesaEstado[]>([])
  const [nombreNueva, setNombreNueva] = useState('')
  const [error, setError] = useState('')

  const cargar = useCallback(() => {
    api.mesas().then((d) => setMesas(d.mesas)).catch(() => {})
  }, [])

  useEffect(() => {
    cargar()
  }, [cargar])

  const crear = async () => {
    if (!nombreNueva.trim()) return
    try {
      await api.crearMesa(nombreNueva.trim())
      setNombreNueva('')
      cargar()
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const actualizar = async (id: number, cambios: { nombre?: string; activa?: boolean }) => {
    try {
      await api.actualizarMesa(id, cambios)
      cargar()
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  return (
    <div className="gestor-mesas">
      <h3 className="subtitulo-resumen">🪑 Mesas del local</h3>
      <p className="nota-admin">
        La caja asigna tickets a estas mesas (varias juntas = combinadas) y las libera cuando
        el grupo se va. Desactiva una mesa para retirarla sin perder su historial.
      </p>
      {error && <div className="banner-error">{error}</div>}
      <div className="mesas-lista">
        {mesas.map((m) => (
          <div className="mesa-fila" key={m.id}>
            <input
              defaultValue={m.nombre}
              onBlur={(e) => {
                const nombre = e.target.value.trim()
                if (nombre && nombre !== m.nombre) actualizar(m.id, { nombre })
              }}
            />
            <label className="config-toggle mesa-activa">
              <input
                type="checkbox"
                checked={m.activa}
                onChange={(e) => actualizar(m.id, { activa: e.target.checked })}
              />
              activa
            </label>
            {m.ocupada && <span className="badge-mesa">ocupada #{m.ordenes.join(' #')}</span>}
          </div>
        ))}
      </div>
      <div className="mesa-fila">
        <input
          placeholder="Nombre de la mesa nueva (Mesa 5, Barra…)"
          value={nombreNueva}
          onChange={(e) => setNombreNueva(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && crear()}
        />
        <button className="boton-primario boton-crear-mesa" onClick={crear}>+ Agregar mesa</button>
      </div>
    </div>
  )
}
