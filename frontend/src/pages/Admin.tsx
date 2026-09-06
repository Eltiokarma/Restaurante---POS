import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, clearAdminToken, getAdminToken, setAdminToken, soles, urlFotoPlato, NOMBRE_CATEGORIA, NOMBRE_EMPAQUE } from '../api'
import { IconoBillete, IconoEgreso, IconoEngranaje, IconoMovil, IconoTarjeta } from '../components/Iconos'
import type { CajaEstado, ConfigOut, DatosLocal, Empaque, Insumo, MenuGuardadoOut, MesaEstado, MovimientoKardex, OrdenOut, Plato, PlantillaMenuIn, ReporteConsumo, ResumenDatos, StatsOut, VozPanel } from '../api'
import { Ticket } from '../components/Ticket'

type Tab = 'resumen' | 'menu' | 'ordenes' | 'insumos' | 'cancelaciones' | 'voz' | 'config'

interface PlatoEditable {
  id?: number
  nombre: string
  categoria: string
  precio: string // como texto mientras se edita
  activo_hoy: boolean
  sale_al_momento: boolean
  foto: string | null
  sinonimos: string[]
}

const TABS_EXTRA: { id: Tab; texto: string }[] = [
  { id: 'cancelaciones', texto: 'Cancelaciones' },
  { id: 'voz', texto: 'Voz' },
  { id: 'config', texto: 'Configuración' },
]

export function Admin() {
  const [logueado, setLogueado] = useState(() => getAdminToken() !== '')
  const [tab, setTab] = useState<Tab>('resumen')
  // Tabs de uso ocasional agrupadas tras el "⋯" (auditoría visual, h. 07)
  const [tabsExtraAbierto, setTabsExtraAbierto] = useState(false)

  useEffect(() => {
    if (!tabsExtraAbierto) return
    const alTocarFuera = (ev: MouseEvent) => {
      if (!(ev.target as HTMLElement).closest('.menu-mas')) setTabsExtraAbierto(false)
    }
    const alTeclear = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setTabsExtraAbierto(false)
    }
    document.addEventListener('click', alTocarFuera)
    document.addEventListener('keydown', alTeclear)
    return () => {
      document.removeEventListener('click', alTocarFuera)
      document.removeEventListener('keydown', alTeclear)
    }
  }, [tabsExtraAbierto])

  if (!logueado) {
    return <AdminLogin onOk={() => setLogueado(true)} />
  }

  return (
    <div className="pantalla-admin">
      <header className="admin-cabecera">
        <h1><IconoEngranaje tam={26} /> Administración</h1>
        <nav className="admin-tabs">
          <button className={tab === 'resumen' ? 'activa' : ''} onClick={() => setTab('resumen')}>Resumen</button>
          <button className={tab === 'menu' ? 'activa' : ''} onClick={() => setTab('menu')}>Menú del día</button>
          <button className={tab === 'ordenes' ? 'activa' : ''} onClick={() => setTab('ordenes')}>Órdenes</button>
          <button className={tab === 'insumos' ? 'activa' : ''} onClick={() => setTab('insumos')}>Insumos</button>
          <div className="menu-mas">
            <button
              className={`boton-mas ${TABS_EXTRA.some((t) => t.id === tab) ? 'activa' : ''}`}
              aria-haspopup="menu"
              aria-expanded={tabsExtraAbierto}
              aria-label="Más secciones"
              onClick={() => setTabsExtraAbierto((v) => !v)}
            >
              ⋯
            </button>
            {tabsExtraAbierto && (
              <div className="popover-mas" role="menu">
                {TABS_EXTRA.map((t) => (
                  <button
                    key={t.id}
                    role="menuitem"
                    className={tab === t.id ? 'activa' : ''}
                    onClick={() => { setTab(t.id); setTabsExtraAbierto(false) }}
                  >
                    {t.texto}
                  </button>
                ))}
              </div>
            )}
          </div>
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
        <h1><IconoEngranaje tam={26} /> Administración</h1>
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

// Fecha local en AAAA-MM-DD (toISOString daría el día de ayer en Lima)
function fechaIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function sumarDias(d: Date, dias: number): Date {
  const copia = new Date(d)
  copia.setDate(copia.getDate() + dias)
  return copia
}

function fechaLocalISO(diasAtras: number): string {
  return fechaIso(sumarDias(new Date(), -diasAtras))
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
  // El color marca lo que está por ENCIMA del promedio; el pico va rotulado
  const promedioHora =
    stats.ordenes_por_hora.reduce((s, h) => s + h.cantidad, 0) /
    Math.max(1, stats.ordenes_por_hora.length)
  const promedioDia =
    stats.ventas_por_dia.reduce((s, d) => s + d.total, 0) /
    Math.max(1, stats.ventas_por_dia.length)
  const horaPico = stats.ordenes_por_hora.reduce(
    (a, h) => (h.cantidad > a.cantidad ? h : a),
    stats.ordenes_por_hora[0] ?? { hora: 0, cantidad: 0 },
  )
  const mejorDia = stats.ventas_por_dia.reduce(
    (a, d) => (d.total > a.total ? d : a),
    stats.ventas_por_dia[0] ?? { fecha: '', total: 0, ordenes: 0 },
  )

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
        <div className="tabla-desplazable"><table className="tabla-admin tabla-resumen">
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
        </table></div>
      )}

      {periodo !== 'hoy' && stats.ventas_por_dia.length > 0 && (
        <>
          <h3 className="subtitulo-resumen">Ventas por día</h3>
          <div className="barras-horas barras-fluidas">
            <p className="pico-grafico">
              mejor día {mejorDia.fecha.slice(5)} · {soles(mejorDia.total)}
            </p>
            <div className="fila-barras">
              {stats.ventas_por_dia.map((d) => (
                <div
                  className={`barra-hora barra-dia ${d.total > promedioDia ? 'sobre-promedio' : ''}`}
                  key={d.fecha}
                  title={`${d.fecha}: ${d.ordenes} órdenes — ${soles(d.total)}`}
                >
                  <span className="barra-hora-valor">{soles(d.total)}</span>
                  <div className="barra-hora-relleno" style={{ height: `${(d.total / maxDia) * 100}%` }} />
                </div>
              ))}
            </div>
            <div className="fila-etiquetas">
              {stats.ventas_por_dia.map((d) => (
                <span className="barra-hora-etiqueta" key={d.fecha}>{d.fecha.slice(5)}</span>
              ))}
            </div>
          </div>
        </>
      )}

      <HistorialCierres onSesionVencida={onSesionVencida} />

      {stats.ordenes_por_hora.length > 0 && (
        <>
          <h3 className="subtitulo-resumen">Órdenes por hora{periodo !== 'hoy' ? ' (acumulado del período)' : ''}</h3>
          <div className="barras-horas barras-fluidas">
            <p className="pico-grafico">
              pico {horaPico.hora}:00 · {horaPico.cantidad} {horaPico.cantidad === 1 ? 'orden' : 'órdenes'}
            </p>
            <div className="fila-barras">
              {stats.ordenes_por_hora.map((h) => (
                <div
                  className={`barra-hora ${h.cantidad > promedioHora ? 'sobre-promedio' : ''}`}
                  key={h.hora} title={`${h.cantidad} órdenes entre ${h.hora}:00 y ${h.hora}:59`}
                >
                  <span className="barra-hora-valor">{h.cantidad}</span>
                  <div className="barra-hora-relleno" style={{ height: `${(h.cantidad / maxHora) * 100}%` }} />
                </div>
              ))}
            </div>
            <div className="fila-etiquetas">
              {stats.ordenes_por_hora.map((h) => (
                <span className="barra-hora-etiqueta" key={h.hora}>{h.hora}</span>
              ))}
            </div>
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
      <div className="tabla-desplazable"><table className="tabla-admin">
        <thead>
          <tr>
            <th>Fecha</th>
            <th className="col-cantidad">Fondo</th>
            <th className="col-cantidad"><IconoBillete tam={15} /> Efectivo</th>
            <th className="col-cantidad"><IconoTarjeta tam={15} /> Tarjeta</th>
            <th className="col-cantidad"><IconoMovil tam={15} /> Yape</th>
            <th className="col-cantidad"><IconoEgreso tam={15} /> Egresos</th>
            <th className="col-cantidad">Contado</th>
            <th className="col-total">Diferencia</th>
          </tr>
        </thead>
        <tbody>
          {cierres.map((c) => (
            <tr key={`${c.fecha}-${c.turno ?? 1}`}>
              <td>
                {c.fecha}
                {(c.turno ?? 1) > 1 && ` · caja ${c.turno}`}
                {!c.cerrada && ' (sin cerrar)'}
              </td>
              <td className="col-cantidad">{soles(c.monto_apertura ?? 0)}</td>
              <td className="col-cantidad">{soles(c.ventas_efectivo)}</td>
              <td className="col-cantidad">{soles(c.ventas_tarjeta)}</td>
              <td className="col-cantidad">{soles(c.ventas_yape)}</td>
              <td className="col-cantidad">{(c.egresos ?? 0) > 0 ? `−${soles(c.egresos ?? 0)}` : '—'}</td>
              <td className="col-cantidad">{c.monto_contado != null ? soles(c.monto_contado) : '—'}</td>
              <td className={`col-total ${(c.diferencia ?? 0) < 0 ? 'stock-negativo' : ''}`}>
                {c.diferencia != null
                  ? c.diferencia === 0 ? '🎯 exacto' : soles(c.diferencia)
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </>
  )
}

// ---------- Menús guardados ("el menú de los jueves") ----------

const DIAS_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

function SeccionMenusGuardados({ onSesionVencida, onCargado }: {
  onSesionVencida: () => void
  onCargado: (mensaje: string) => void
}) {
  const [guardados, setGuardados] = useState<MenuGuardadoOut[]>([])
  const [nombre, setNombre] = useState('')
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')
  // Guardar sobre un día que YA tiene menú lo reemplaza: se confirma en
  // una hoja propia diciendo qué se pierde (hallazgo 29)
  const [reemplazando, setReemplazando] = useState<{ nombre: string; existente: MenuGuardadoOut } | null>(null)

  useEffect(() => {
    api.menusGuardados()
      .then((d) => setGuardados(d.guardados))
      .catch((e) => setError(manejarError(e, onSesionVencida)))
  }, [onSesionVencida])

  const guardarDirecto = async (limpio: string) => {
    setReemplazando(null)
    setError('')
    try {
      const data = await api.guardarMenuDeHoyComo(limpio)
      setGuardados(data.guardados)
      setNombre('')
      setMensaje(`Menú de hoy guardado como "${limpio}" ✔`)
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const guardar = (n: string) => {
    const limpio = n.trim()
    if (!limpio) {
      setError('Ponle un nombre al menú (por ejemplo, el día de la semana)')
      return
    }
    const existente = guardados.find((g) => g.nombre.toLowerCase() === limpio.toLowerCase())
    if (existente) {
      setReemplazando({ nombre: limpio, existente })
      return
    }
    guardarDirecto(limpio)
  }

  const cargar = async (g: MenuGuardadoOut) => {
    if (!window.confirm(
      `¿Cargar "${g.nombre}"? Reemplaza el menú de HOY (platos activos y menú del día).`,
    )) return
    setError('')
    try {
      await api.cargarMenuGuardado(g.id)
      setMensaje('')
      onCargado(`Menú "${g.nombre}" cargado como menú de hoy ✔`)
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const borrar = async (g: MenuGuardadoOut) => {
    if (!window.confirm(`¿Borrar el menú guardado "${g.nombre}"? El menú de hoy no cambia.`)) return
    try {
      const data = await api.borrarMenuGuardado(g.id)
      setGuardados(data.guardados)
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  return (
    <div className="panel-config seccion-guardados">
      <h3 className="subtitulo-resumen">📅 Menús guardados</h3>
      <p className="nota-admin">
        Guarda el menú de hoy con un nombre (por ejemplo "{DIAS_SEMANA[0]}") y otro día
        cárgalo con un toque: platos y menú del día quedan listos.
      </p>
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {error && <div className="banner-error">{error}</div>}
      {guardados.length > 0 && (
        <div className="lista-guardados">
          {guardados.map((g) => (
            <div className="fila-guardado" key={g.id}>
              <div className="fila-guardado-datos">
                <strong>{g.nombre}</strong>
                <span className="nota-admin">
                  {g.cuantos_platos} plato{g.cuantos_platos === 1 ? '' : 's'}: {g.resumen}
                </span>
              </div>
              <button className="boton-primario" onClick={() => cargar(g)}>▶ Cargar hoy</button>
              <button onClick={() => borrar(g)}>🗑</button>
            </div>
          ))}
        </div>
      )}
      <div className="admin-acciones fila-guardar-menu">
        <span>Guardar el menú de hoy como:</span>
        {DIAS_SEMANA.map((d) => {
          const existente = guardados.find((g) => g.nombre.toLowerCase() === d.toLowerCase())
          return (
            <button key={d} className={existente ? 'dia-ocupado' : ''}
                    title={existente ? `Ya guardado (${existente.cuantos_platos} platos): guardar encima lo reemplaza` : undefined}
                    onClick={() => guardar(d)}>
              {existente ? `${d} · ${existente.cuantos_platos} platos` : `Guardar como ${d}`}
            </button>
          )
        })}
        <input
          placeholder="u otro nombre…"
          value={nombre}
          maxLength={60}
          onChange={(e) => setNombre(e.target.value)}
        />
        <button className="boton-primario" onClick={() => guardar(nombre)}>💾 Guardar</button>
      </div>
      {reemplazando && (
        <div className="modal-fondo" onClick={() => setReemplazando(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>¿Reemplazar "{reemplazando.existente.nombre}"?</h2>
            <p>
              "{reemplazando.existente.nombre}" ya tiene un menú guardado con{' '}
              <strong>{reemplazando.existente.cuantos_platos} plato{reemplazando.existente.cuantos_platos === 1 ? '' : 's'}</strong>
              {reemplazando.existente.resumen ? ` (${reemplazando.existente.resumen})` : ''}. Guardar
              encima lo reemplaza con el menú de HOY y esa lista se pierde.
            </p>
            <div className="modal-botones">
              <button className="boton-grande boton-secundario" onClick={() => setReemplazando(null)}>
                Cancelar
              </button>
              <button className="boton-grande boton-confirmar"
                      onClick={() => guardarDirecto(reemplazando.nombre)}>
                Sí, reemplazar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------- Menú del día ----------

// Qué campos viven en el estado local hasta "Guardar" (la foto NO: se sube
// al instante). Sirve para contar cambios sin guardar (hallazgo 25).
const serialPlato = (p: PlatoEditable) =>
  JSON.stringify([p.nombre, p.categoria, p.precio, p.activo_hoy, p.sale_al_momento, p.sinonimos])

function TabMenu({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [platos, setPlatos] = useState<PlatoEditable[]>([])
  const [baseline, setBaseline] = useState<Map<number, string>>(new Map())
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')
  const [menuEmpezar, setMenuEmpezar] = useState(false)
  // Índice del plato abierto en la hoja ⋯ (foto, sinónimos, al momento…)
  const [editando, setEditando] = useState<number | null>(null)
  const [confirmandoAyer, setConfirmandoAyer] = useState(false)

  const aEditable = (p: Plato): PlatoEditable => ({
    id: p.id,
    nombre: p.nombre,
    categoria: p.categoria,
    precio: p.precio.toFixed(2),
    activo_hoy: p.activo_hoy,
    sale_al_momento: p.sale_al_momento ?? false,
    foto: p.foto ?? null,
    sinonimos: p.sinonimos ?? [],
  })

  const fijarBaseline = (lista: PlatoEditable[]) => {
    setBaseline(new Map(lista.filter((p) => p.id !== undefined).map((p) => [p.id as number, serialPlato(p)])))
  }

  const cargar = useCallback(async () => {
    try {
      const data = await api.menuHoy()
      const lista = data.platos.map(aEditable)
      setPlatos(lista)
      fijarBaseline(lista)
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }, [onSesionVencida])

  useEffect(() => {
    cargar()
  }, [cargar])

  const tocado = (p: PlatoEditable) =>
    p.id === undefined || baseline.get(p.id) !== serialPlato(p)
  const cambios = platos.filter(tocado).length

  // Cerrar la pestaña del navegador con cambios pendientes avisa (h. 25)
  useEffect(() => {
    if (cambios === 0) return
    const avisa = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', avisa)
    return () => window.removeEventListener('beforeunload', avisa)
  }, [cambios])

  const editar = (idx: number, cambiosPlato: Partial<PlatoEditable>) => {
    setPlatos((prev) => prev.map((p, i) => (i === idx ? { ...p, ...cambiosPlato } : p)))
  }

  const agregar = () => {
    setPlatos((prev) => [
      ...prev,
      { nombre: '', categoria: 'fondo', precio: '', activo_hoy: true, sale_al_momento: false, foto: null, sinonimos: [] },
    ])
  }

  const quitar = (idx: number) => {
    setPlatos((prev) => prev.filter((_, i) => i !== idx))
  }

  const cargarAyer = async () => {
    setError('')
    setMensaje('')
    setConfirmandoAyer(false)
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

  // Reemplaza TODO lo escrito: si hay cambios sin guardar, primero pregunta (h. 24)
  const pedirCargarAyer = () => {
    if (cambios > 0) setConfirmandoAyer(true)
    else cargarAyer()
  }

  const cargarDelCatalogo = async () => {
    setError('')
    setMensaje('')
    try {
      const data = await api.catalogo()
      const actuales = new Set(platos.filter((p) => p.id).map((p) => p.id))
      const nuevos = data.platos.filter((p) => !actuales.has(p.id))
      if (nuevos.length === 0) {
        setMensaje('Todo el catálogo ya está en la lista.')
        return
      }
      setPlatos((prev) => [...prev, ...nuevos.map((p) => ({ ...aEditable(p), activo_hoy: false }))])
      setMensaje(`${nuevos.length} plato(s) del catálogo agregados APAGADOS: prende los que salen hoy y guarda.`)
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
      const lista = data.platos.map(aEditable)
      setPlatos(lista)
      fijarBaseline(lista)
      setMensaje('Menú guardado ✔ La terminal se actualiza en menos de 30 segundos.')
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const nombreDe = (p: PlatoEditable) => p.nombre.trim() || 'Plato nuevo'
  const activos = platos.filter((p) => p.activo_hoy).length

  return (
    <div>
      <div className="admin-acciones">
        <button onClick={agregar}>+ Agregar plato</button>
        <div className="menu-empezar-envoltorio">
          <button onClick={() => setMenuEmpezar((v) => !v)} aria-expanded={menuEmpezar}>
            Empezar desde… ▾
          </button>
          {menuEmpezar && (
            <>
              <button className="fondo-popover" aria-label="Cerrar" onClick={() => setMenuEmpezar(false)} />
              {/* Cada opción declara su consecuencia ANTES de tocarla (h. 24) */}
              <div className="menu-empezar">
                <button onClick={() => { setMenuEmpezar(false); pedirCargarAyer() }}>
                  <strong>El menú de ayer</strong>
                  <span>Reemplaza los {platos.length} platos de la lista de hoy</span>
                </button>
                <button onClick={() => {
                  setMenuEmpezar(false)
                  document.querySelector('.seccion-guardados')?.scrollIntoView({ behavior: 'smooth' })
                }}>
                  <strong>Un menú guardado</strong>
                  <span>Lunes, Martes… — se eligen más abajo</span>
                </button>
                <button onClick={() => { setMenuEmpezar(false); cargarDelCatalogo() }}>
                  <strong>Agregar del catálogo</strong>
                  <span>Suma a la lista, apagados, los platos históricos que falten</span>
                </button>
              </div>
            </>
          )}
        </div>
      </div>
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {error && <div className="banner-error">{error}</div>}
      {platos.length > 0 && (
        <div className="platos-progreso">
          <span className="cuenta">{activos}</span>
          <span>plato{activos === 1 ? '' : 's'} sale{activos === 1 ? '' : 'n'} hoy · {platos.length} en la lista</span>
        </div>
      )}
      <p className="ayuda-arriba">
        Para agotar un plato a mitad de servicio: apaga "Sale hoy" y guarda.
      </p>

      {/* En celular cada plato es una tarjeta y "Sale hoy" manda (h. 23/26) */}
      <div className="menu-tarjetas">
        {platos.map((p, idx) => (
          <div key={p.id ?? `nuevo-${idx}`}
               className={`plato-tarjeta ${p.activo_hoy ? 'sale-hoy' : 'no-sale-hoy'} ${tocado(p) ? 'tocada' : ''}`}>
            <div className="plato-tarjeta-cabecera">
              {p.foto && <img className="mini-foto" src={urlFotoPlato(p.foto)} alt="" />}
              <div className="plato-tarjeta-datos">
                <strong>{nombreDe(p)}</strong>
                <span>
                  {NOMBRE_CATEGORIA[p.categoria] ?? p.categoria}
                  {p.sinonimos.length > 0 && ` · ${p.sinonimos.length} sinónimo${p.sinonimos.length === 1 ? '' : 's'}`}
                  {p.sale_al_momento && ' · al momento'}
                </span>
              </div>
              <span className="plato-tarjeta-precio">
                {parseFloat(p.precio) > 0 ? soles(parseFloat(p.precio)) : '—'}
              </span>
            </div>
            <div className="plato-tarjeta-acciones">
              <button type="button" className="toggle-sale-hoy" aria-pressed={p.activo_hoy}
                      aria-label={`${nombreDe(p)} sale hoy`}
                      onClick={() => editar(idx, { activo_hoy: !p.activo_hoy })}>
                <span className="riel"><span className="perilla" /></span>
                {p.activo_hoy ? 'Sale hoy' : 'No sale hoy'}
              </button>
              <button className="boton-mas-plato" aria-label={`Editar ${nombreDe(p)}`}
                      onClick={() => setEditando(idx)}>⋯</button>
            </div>
          </div>
        ))}
      </div>

      {/* En escritorio se conserva la tabla completa */}
      <div className="tabla-menu-envoltorio tabla-desplazable"><table className="tabla-admin tabla-editable">
        <thead>
          <tr>
            <th>Plato</th>
            <th title="Se ve en la tarjeta de la terminal: sube la conversión del kiosko">Foto</th>
            <th>Categoría</th>
            <th>Precio S/</th>
            <th>Sinónimos (para la voz)</th>
            <th title="Se prepara al pedido (bistec frito): obliga entrega por tiempos">Al momento</th>
            <th>Sale hoy</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {platos.map((p, idx) => (
            <tr key={p.id ?? `nuevo-${idx}`} className={tocado(p) ? 'fila-tocada' : ''}>
              <td>
                <input value={p.nombre} onChange={(e) => editar(idx, { nombre: e.target.value })} placeholder="Nombre del plato" />
              </td>
              <td>
                <CeldaFoto
                  plato={p}
                  onCambio={(foto) => editar(idx, { foto })}
                  onError={(e) => setError(manejarError(e, onSesionVencida))}
                />
              </td>
              <td>
                <select value={p.categoria} onChange={(e) => editar(idx, { categoria: e.target.value })}
                        aria-label={`Categoría de ${nombreDe(p)}`}>
                  {Object.entries(NOMBRE_CATEGORIA).map(([valor, texto]) => (
                    <option key={valor} value={valor}>{texto}</option>
                  ))}
                </select>
              </td>
              <td className="col-precio">
                <input
                  type="number"
                  step="0.50"
                  min="0"
                  value={p.precio}
                  onChange={(e) => editar(idx, { precio: e.target.value })}
                  placeholder="0.00"
                  aria-label={`Precio de ${nombreDe(p)}`}
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
                  aria-label={`${nombreDe(p)} se prepara al momento`}
                  onChange={(e) => editar(idx, { sale_al_momento: e.target.checked })}
                />
              </td>
              <td className="celda-centro">
                <input
                  type="checkbox"
                  checked={p.activo_hoy}
                  aria-label={`${nombreDe(p)} sale hoy`}
                  onChange={(e) => editar(idx, { activo_hoy: e.target.checked })}
                />
              </td>
              <td>
                {p.id === undefined && (
                  <button className="boton-quitar" aria-label={`Quitar ${nombreDe(p)}`}
                          onClick={() => quitar(idx)}>✕</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table></div>

      {/* Un solo modelo de guardado, con el contador a la vista (h. 24/25) */}
      <div className={`barra-guardado ${cambios === 0 ? 'limpia' : ''}`}>
        <span className="cuenta-cambios">
          {cambios === 0 ? 'Todo guardado' : `${cambios} cambio${cambios === 1 ? '' : 's'} sin guardar`}
        </span>
        <button className="boton-primario" onClick={guardar}>💾 Guardar menú del día</button>
      </div>

      <SeccionMenusGuardados
        onSesionVencida={onSesionVencida}
        onCargado={(msg) => { cargar(); setMensaje(msg) }}
      />

      {/* Hoja ⋯: lo secundario del plato, con espacio real (h. 23/26/28) */}
      {editando !== null && platos[editando] && (
        <div className="modal-fondo" onClick={() => setEditando(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>{nombreDe(platos[editando])}</h2>
            <div className="hoja-plato">
              <div className="campo-etiquetado">
                <label>Nombre</label>
                <input type="text" value={platos[editando].nombre}
                       onChange={(e) => editar(editando, { nombre: e.target.value })}
                       placeholder="Nombre del plato" />
              </div>
              <div className="campo-etiquetado">
                <label>Categoría</label>
                <select value={platos[editando].categoria}
                        onChange={(e) => editar(editando, { categoria: e.target.value })}>
                  {Object.entries(NOMBRE_CATEGORIA).map(([valor, texto]) => (
                    <option key={valor} value={valor}>{texto}</option>
                  ))}
                </select>
              </div>
              <div className="campo-etiquetado">
                <label>Precio S/</label>
                <input type="number" inputMode="decimal" step="0.50" min="0"
                       value={platos[editando].precio}
                       onChange={(e) => editar(editando, { precio: e.target.value })}
                       placeholder="0.00" />
              </div>
              <div className="campo-etiquetado">
                <label>Foto (se guarda al instante, sin pasar por "Guardar")</label>
                <CeldaFoto
                  plato={platos[editando]}
                  onCambio={(foto) => editar(editando, { foto })}
                  onError={(e) => setError(manejarError(e, onSesionVencida))}
                />
              </div>
              <div className="campo-etiquetado">
                <label>Sinónimos (para la voz)</label>
                <ChipsSinonimos
                  sinonimos={platos[editando].sinonimos}
                  onCambiar={(sinonimos) => editar(editando, { sinonimos })}
                />
              </div>
              <label className="opcion-al-momento">
                <input type="checkbox" checked={platos[editando].sale_al_momento}
                       onChange={(e) => editar(editando, { sale_al_momento: e.target.checked })} />
                <span className="explica">
                  <strong>Sale al momento</strong>
                  <span>Se prepara al pedido (bistec frito). Obliga entrega por tiempos en cocina.</span>
                </span>
              </label>
              {platos[editando].id === undefined ? (
                <button className="boton-grande boton--peligro"
                        onClick={() => { quitar(editando); setEditando(null) }}>
                  ✕ Quitar esta fila
                </button>
              ) : (
                <p className="nota-admin">
                  Para que no salga hoy, apaga "Sale hoy": el plato queda en el catálogo y su
                  historial no cambia.
                </p>
              )}
              <button className="boton-grande boton-confirmar" onClick={() => setEditando(null)}>
                Listo
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cargar el menú de ayer con cambios sin guardar: se pierde trabajo (h. 24) */}
      {confirmandoAyer && (
        <div className="modal-fondo" onClick={() => setConfirmandoAyer(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>¿Cargar el menú de ayer?</h2>
            <p>
              Tienes <strong>{cambios} cambio{cambios === 1 ? '' : 's'} sin guardar</strong> en la
              lista de hoy. Cargar el menú de ayer reemplaza toda la lista y esos cambios se pierden.
            </p>
            <div className="modal-botones">
              <button className="boton-grande boton-secundario" onClick={() => setConfirmandoAyer(false)}>
                Cancelar
              </button>
              <button className="boton-grande boton-confirmar" onClick={cargarAyer}>
                Sí, cargar el de ayer
              </button>
            </div>
          </div>
        </div>
      )}
      <EditorPlantillas onSesionVencida={onSesionVencida} />
      <EditorAgregados onSesionVencida={onSesionVencida} />
    </div>
  )
}

// ---------- Menús encadenados (plantillas) ----------

interface TiempoEditable {
  rotulo: string
  obligatorio: boolean
  precio_extra: string // como texto mientras se edita
  descuento_quitar: string // cuánto baja el menú si el cliente lo quita
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
            descuento_quitar: t.descuento_si_se_quita > 0 ? t.descuento_si_se_quita.toFixed(2) : '',
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
          { rotulo: 'Entrada o sopa', obligatorio: true, precio_extra: '3.00', descuento_quitar: '1.00', alternativas: [] },
          { rotulo: 'Segundo', obligatorio: true, precio_extra: '', descuento_quitar: '', alternativas: [] },
        ],
      },
    ])
  }

  const guardar = () => guardarLista(plantillas)

  const guardarLista = async (lista: PlantillaEditable[]) => {
    setError('')
    setMensaje('')
    // Nada se descarta en silencio: un menú sin nombre o un tiempo sin
    // rótulo se avisan, porque al no enviarse el backend los retiraría del
    // catálogo y el menú desaparecería de la terminal con un "guardado ✔"
    if (lista.some((p) => p.nombre.trim() === '')) {
      setError('Hay un menú sin nombre: ponle uno o quítalo con la ✕.')
      return false
    }
    const validas = lista
    const sinPrecio = validas.filter((p) => !(parseFloat(p.precio) > 0))
    if (sinPrecio.length > 0) {
      setError(`Falta el precio de: ${sinPrecio.map((p) => p.nombre.trim()).join(', ')}`)
      return false
    }
    const sinRotulo = validas.filter((p) => p.tiempos.some((t) => t.rotulo.trim() === ''))
    if (sinRotulo.length > 0) {
      setError(
        `Hay un tiempo sin nombre (ej. "Postre") en: ${sinRotulo
          .map((p) => p.nombre.trim())
          .join(', ')}. Ponle rótulo o quítalo con la ✕.`,
      )
      return false
    }
    const sinTiempos = validas.filter((p) => p.tiempos.length === 0)
    if (sinTiempos.length > 0) {
      setError(
        `Un menú necesita al menos un tiempo: revisa ${sinTiempos
          .map((p) => p.nombre.trim())
          .join(', ')}`,
      )
      return false
    }
    const sinAlternativas = validas.filter((p) =>
      p.tiempos.some((t) => t.alternativas.length === 0),
    )
    if (sinAlternativas.length > 0) {
      setError(
        `Cada tiempo necesita al menos un plato: revisa ${sinAlternativas
          .map((p) => p.nombre.trim())
          .join(', ')}`,
      )
      return false
    }
    const payload: PlantillaMenuIn[] = validas.map((p) => ({
      id: p.id,
      nombre: p.nombre.trim(),
      precio: parseFloat(p.precio),
      activo_hoy: p.activo_hoy,
      tiempos: p.tiempos
        .map((t) => ({
          rotulo: t.rotulo.trim(),
          obligatorio: t.obligatorio,
          precio_extra: parseFloat(t.precio_extra) > 0 ? parseFloat(t.precio_extra) : 0,
          descuento_si_se_quita: parseFloat(t.descuento_quitar) > 0 ? parseFloat(t.descuento_quitar) : 0,
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
      return true
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
      return false
    }
  }

  const nombreDe = (platoId: number) =>
    catalogo.find((p) => p.id === platoId)?.nombre ?? `#${platoId}`

  return (
    <div className="editor-plantillas">
      <h2 className="titulo-categoria">Menús (combo con tiempos)</h2>
      <p className="nota-admin">
        Un menú es entrada + segundo + refresco (y postre si quieres) por UN precio. Sin esto, la
        terminal cobra cada plato por separado. El menú se cobra por SU precio, no por la suma de
        los platos.
      </p>
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {error && <div className="banner-error">{error}</div>}
      <AsistenteMenu
        catalogo={catalogo}
        yaHayMenus={plantillas.length > 0}
        onCrear={(nueva) => guardarLista([...plantillas, nueva])}
      />
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
                <label title="Cuánto baja el menú si el cliente quita este tiempo (ej. sin sopa). Vacío = no baja">
                  Si lo quita −S/{' '}
                  <input
                    type="number" step="0.50" min="0" className="input-precio"
                    value={t.descuento_quitar}
                    onChange={(e) => editarTiempo(idx, ti, { descuento_quitar: e.target.value })}
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
                    descuento_quitar: '',
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
        placeholder="+ sinónimo ⏎"
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            agregar()
          }
        }}
        // Un scroll no es una confirmación: al perder el foco se descarta
        // lo escrito a medias en vez de guardarlo en silencio (hallazgo 28)
        onBlur={() => setTexto('')}
      />
    </div>
  )
}

// Subir/cambiar/quitar la foto de un plato. La foto se guarda al instante
// (no espera al botón "Guardar menú"): vive en el backend, no en la tabla.
function CeldaFoto({
  plato,
  onCambio,
  onError,
}: {
  plato: PlatoEditable
  onCambio: (foto: string | null) => void
  onError: (e: unknown) => void
}) {
  const [subiendo, setSubiendo] = useState(false)

  if (plato.id === undefined) {
    return <span className="nota-foto">guarda primero</span>
  }
  const platoId = plato.id

  return (
    <div className="celda-foto">
      {plato.foto && <img className="mini-foto" src={urlFotoPlato(plato.foto)} alt="" />}
      <label className="boton-subir-foto">
        {subiendo ? 'Subiendo…' : plato.foto ? 'Cambiar' : '📷 Subir'}
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          hidden
          disabled={subiendo}
          onChange={async (e) => {
            const archivo = e.target.files?.[0]
            e.target.value = ''
            if (!archivo) return
            setSubiendo(true)
            try {
              const r = await api.subirFotoPlato(platoId, archivo)
              onCambio(r.foto)
            } catch (err) {
              onError(err)
            } finally {
              setSubiendo(false)
            }
          }}
        />
      </label>
      {plato.foto && (
        <button
          className="boton-quitar"
          title="Quitar la foto"
          onClick={async () => {
            try {
              await api.quitarFotoPlato(platoId)
              onCambio(null)
            } catch (err) {
              onError(err)
            }
          }}
        >
          ✕
        </button>
      )}
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

      <div className="tabla-desplazable"><table className="tabla-admin">
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
      </table></div>
      {panel.logs.length === 0 && <p className="nota-admin">Sin pedidos por voz hoy.</p>}
    </div>
  )
}

// ---------- Órdenes de hoy ----------

function fechaHoyISO(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// Una línea por partida con los tiempos del menú debajo, en vez del
// join(', ') con paréntesis anidados (hallazgo 30)
function PartidasDeOrden({ orden }: { orden: OrdenOut }) {
  return (
    <ul className="orden-partidas">
      {orden.menus.map((m, i) => (
        <li className="orden-partida" key={`m-${i}`}>
          <span className="cantidad">{m.cantidad}×</span>
          <span className="cuerpo">
            <strong>{m.nombre}</strong>
            {m.items.length > 0 && (
              <span className="tiempos">{m.items.map((x) => x.nombre).join(' · ')}</span>
            )}
          </span>
        </li>
      ))}
      {orden.items.map((it, i) => (
        <li className="orden-partida" key={`i-${i}`}>
          <span className="cantidad">{it.cantidad}×</span>
          <span className="cuerpo"><strong>{it.nombre}</strong></span>
        </li>
      ))}
    </ul>
  )
}

const ESTADOS_ORDEN = ['pendiente', 'preparando', 'listo', 'entregado', 'anulada']

function TabOrdenes() {
  const [ordenes, setOrdenes] = useState<OrdenOut[]>([])
  const [totalVendido, setTotalVendido] = useState(0)
  const [ticket, setTicket] = useState<{ orden: OrdenOut; local: DatosLocal } | null>(null)
  // Movimiento de cualquier día, no solo hoy
  const [fecha, setFecha] = useState(fechaHoyISO())
  const [busqueda, setBusqueda] = useState('')
  const [filtroEstado, setFiltroEstado] = useState('')
  const [ultimaCarga, setUltimaCarga] = useState<number | null>(null)
  const [avisoReimpresion, setAvisoReimpresion] = useState('')
  const [error, setError] = useState('')
  // Confirmación previa de la reimpresión, con adónde va (hallazgo 32)
  const [confirmando, setConfirmando] = useState<{ orden: OrdenOut; modo: string; local: DatosLocal } | null>(null)

  const cargar = useCallback(() => {
    const esHoy = fecha === fechaHoyISO()
    return (esHoy ? api.ordenesHoy() : api.ordenesDeDia(fecha))
      .then((data) => {
        // El refresco de 15s no debe hacer saltar la lista bajo el dedo:
        // solo se reemplaza el arreglo si de verdad cambió
        setOrdenes((prev) =>
          JSON.stringify(prev) === JSON.stringify(data.ordenes) ? prev : data.ordenes,
        )
        setTotalVendido(data.total_vendido)
        setUltimaCarga(Date.now())
      })
      .catch(() => {})
  }, [fecha])

  useEffect(() => {
    cargar()
    if (fecha !== fechaHoyISO()) return
    const intervalo = window.setInterval(cargar, 15_000)
    return () => window.clearInterval(intervalo)
  }, [cargar, fecha])

  // Re-render periódico solo para que "actualizado hace N s" no se congele
  const [, setTic] = useState(0)
  useEffect(() => {
    const t = window.setInterval(() => setTic((n) => n + 1), 5_000)
    return () => window.clearInterval(t)
  }, [])

  // Reimpresión: útil cuando el ticket original no salió (papel, impresora
  // apagada, etc.). Si la configuración del local no llega, NO se imprime:
  // saldría un ticket sin nombre ni RUC.
  const prepararReimpresion = async (orden: OrdenOut) => {
    setAvisoReimpresion('')
    setError('')
    try {
      const cfg = await api.config()
      setConfirmando({
        orden,
        modo: cfg.modo_impresion,
        local: { nombre: cfg.nombre_local, direccion: cfg.direccion, ruc: cfg.ruc },
      })
    } catch {
      setError('No se pudo leer la configuración del local, así que no se reimprime (saldría un ticket sin nombre ni RUC). Prueba de nuevo en unos segundos.')
    }
  }

  const confirmarReimpresion = async () => {
    if (!confirmando) return
    const { orden, modo, local } = confirmando
    setConfirmando(null)
    if (modo === 'estacion') {
      try {
        await api.reimprimirOrden(orden.id)
        setAvisoReimpresion(
          `Ticket #${String(orden.numero_orden_dia).padStart(3, '0')} enviado a la estación de impresión.`,
        )
      } catch {
        setError('No se pudo reenviar el ticket a la estación. Revisa que la ticketera esté abierta y prueba de nuevo.')
      }
      return
    }
    setTicket({ orden, local })
  }

  useEffect(() => {
    if (!ticket) return
    const timer = window.setTimeout(() => {
      window.print()
      setTicket(null)
    }, 150)
    return () => window.clearTimeout(timer)
  }, [ticket])

  const esHoy = fecha === fechaHoyISO()
  const num = (o: OrdenOut) => String(o.numero_orden_dia).padStart(3, '0')
  const hace = ultimaCarga ? Math.max(0, Math.round((Date.now() - ultimaCarga) / 1000)) : null
  const filtroNum = busqueda.trim().replace(/^#/, '')
  const ordenesFiltradas = ordenes.filter((o) => {
    if (filtroEstado && o.estado !== filtroEstado) return false
    if (filtroNum && !num(o).includes(filtroNum) && String(o.numero_orden_dia) !== filtroNum) return false
    return true
  })
  const estadosPresentes = ESTADOS_ORDEN.filter((e) => ordenes.some((o) => o.estado === e))

  return (
    <div>
      <div className="total-dia">
        <div className="cifra">
          <span>Vendido</span>
          <strong>{soles(totalVendido)}</strong>
        </div>
        <div className="cifra">
          <span>Órdenes</span>
          <strong>{ordenes.length}</strong>
        </div>
        <label className="selector-fecha">
          Día
          <input type="date" value={fecha} max={fechaHoyISO()}
                 onChange={(e) => e.target.value && setFecha(e.target.value)} />
        </label>
      </div>
      {avisoReimpresion && <div className="banner-ok">{avisoReimpresion}</div>}
      {error && <div className="banner-error">{error}</div>}
      {(ordenes.length > 0 || esHoy) && (
        <div className="ordenes-filtros">
          <input className="buscador-orden" inputMode="numeric" placeholder="🔍 Nº de orden…"
                 value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
          {estadosPresentes.map((e) => (
            <button key={e} type="button" className="chip-estado" aria-pressed={filtroEstado === e}
                    onClick={() => setFiltroEstado((f) => (f === e ? '' : e))}>
              {e} · {ordenes.filter((o) => o.estado === e).length}
            </button>
          ))}
          {esHoy && (
            <span className="acuse-refresco">
              {hace !== null && (hace < 10 ? 'recién actualizado' : `actualizado hace ${hace} s`)}
              <button type="button" onClick={() => { void cargar() }}>↻ Refrescar</button>
            </span>
          )}
        </div>
      )}

      {/* En celular cada orden es una tarjeta legible bajo presión (h. 30) */}
      <div className="ordenes-tarjetas">
        {ordenesFiltradas.map((o) => (
          <div className="orden-tarjeta" key={o.id}>
            <div className="orden-tarjeta-cabecera">
              <span className="orden-tarjeta-numero">#{num(o)}</span>
              <span className="orden-tarjeta-hora">{o.hora}</span>
              <span className={`etiqueta-estado etiqueta-${o.estado}`}>{o.estado}</span>
              <span className="orden-tarjeta-total">{soles(o.total)}</span>
            </div>
            <PartidasDeOrden orden={o} />
            <div className="orden-tarjeta-pie">
              <button className="boton-reimprimir"
                      aria-label={`Reimprimir ticket de la orden ${num(o)}`}
                      onClick={() => prepararReimpresion(o)}>
                🖨 Reimprimir ticket
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* En escritorio se conserva la tabla, con las partidas como lista */}
      <div className="tabla-ordenes-envoltorio tabla-desplazable"><table className="tabla-admin">
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
          {ordenesFiltradas.map((o) => (
            <tr key={o.id}>
              <td>#{num(o)}</td>
              <td>{o.hora}</td>
              <td className="col-items"><PartidasDeOrden orden={o} /></td>
              <td>{soles(o.total)}</td>
              <td><span className={`etiqueta-estado etiqueta-${o.estado}`}>{o.estado}</span></td>
              <td>
                <button className="boton-reimprimir"
                        aria-label={`Reimprimir ticket de la orden ${num(o)}`}
                        onClick={() => prepararReimpresion(o)}>
                  🖨 Reimprimir
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table></div>
      {ordenesFiltradas.length === 0 && (
        <p className="nota-admin">
          {ordenes.length > 0
            ? 'Ninguna orden coincide con el filtro.'
            : esHoy
              ? 'Todavía no hay órdenes hoy.'
              : `No hubo órdenes el ${fecha}.`}
        </p>
      )}
      {confirmando && (
        <div className="modal-fondo" onClick={() => setConfirmando(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>¿Reimprimir el ticket #{num(confirmando.orden)}?</h2>
            <p>
              {confirmando.modo === 'estacion'
                ? 'Se reimprime en la estación de impresión (la PC con la impresora).'
                : 'Se imprime desde esta pantalla: se va a abrir el diálogo de impresión.'}
            </p>
            <div className="modal-botones">
              <button className="boton-grande boton-secundario" onClick={() => setConfirmando(null)}>
                Cancelar
              </button>
              <button className="boton-grande boton-confirmar" onClick={confirmarReimpresion}>
                🖨 Reimprimir
              </button>
            </div>
          </div>
        </div>
      )}
      {ticket && (
        <div className="solo-impresion">
          <Ticket orden={ticket.orden} local={ticket.local} />
        </div>
      )}
    </div>
  )
}

// ---------- Insumos, recetas y kardex ----------

// Unidades cerradas de la despensa (hallazgo 16): texto libre creaba
// "Kg", "kilo" y "kg." como tres unidades distintas y rompía la
// conversión de las recetas base semanas después.
const UNIDADES_INSUMO = ['kg', 'g', 'l', 'ml', 'unidad', 'atado']

const redondear = (n: number) => Math.round(n * 1000) / 1000

function TabInsumos({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [insumos, setInsumos] = useState<Insumo[]>([])
  const [valorInventario, setValorInventario] = useState(0)
  const [porAgotarse, setPorAgotarse] = useState<string[]>([])
  const [movimientos, setMovimientos] = useState<MovimientoKardex[]>([])
  const [catalogo, setCatalogo] = useState<Plato[]>([])
  const [mensaje, setMensaje] = useState('')
  // Canal ámbar (hallazgo 21): "salió bien pero falta algo" no es un error
  const [aviso, setAviso] = useState('')
  const [error, setError] = useState('')
  const [seccion, setSeccion] = useState<'despensa' | 'consumo' | 'recetas' | 'historial'>('despensa')

  // ---------- Despensa ----------
  const [busquedaDespensa, setBusquedaDespensa] = useState('')
  const [soloBajos, setSoloBajos] = useState(false)
  // Hoja de movimiento abierta (hallazgo 14: una hoja por movimiento,
  // con color y verbo propios, en vez de la fila inline idéntica)
  const [accion, setAccion] = useState<{ id: number; tipo: 'compra' | 'merma' | 'ajuste' } | null>(null)
  const [accionCantidad, setAccionCantidad] = useState('')
  const [accionCosto, setAccionCosto] = useState('')
  const [accionNota, setAccionNota] = useState('')
  // El mínimo se edita donde tiene contexto: en la hoja de "Conté" (h. 17)
  const [accionMinimo, setAccionMinimo] = useState('')
  const [confirmandoCostoRaro, setConfirmandoCostoRaro] = useState(false)
  const [minimoAcuse, setMinimoAcuse] = useState<number | null>(null)
  const [nuevo, setNuevo] = useState({ nombre: '', unidad: 'kg', costo: '' })
  const [mostrarNuevo, setMostrarNuevo] = useState(false)

  // ---------- Historial ----------
  const [histRango, setHistRango] = useState<'7' | '30' | 'manual'>('7')
  const [histFechas, setHistFechas] = useState(() => ({
    desde: fechaIso(sumarDias(new Date(), -6)),
    hasta: fechaIso(new Date()),
  }))
  // Filtro "solo este insumo": se llega con el 🧾 de la despensa
  const [histInsumo, setHistInsumo] = useState<Insumo | null>(null)
  const [busquedaHistorial, setBusquedaHistorial] = useState('')

  // ---------- Recetas ----------
  const [busquedaPlato, setBusquedaPlato] = useState('')
  const [filtroReceta, setFiltroReceta] = useState<'sin' | 'con' | 'todos'>('sin')
  const [recetaPlato, setRecetaPlato] = useState('')
  const [recetaItems, setRecetaItems] = useState<{ insumo_id: number; cantidad: string }[]>([])
  // Guardado sucio/limpio (h. 22): cambiar de plato no borra sin preguntar
  const [recetaSucia, setRecetaSucia] = useState(false)
  const [saliendoA, setSaliendoA] = useState<string | null>(null)
  const [buscandoInsumo, setBuscandoInsumo] = useState(false)
  const [busquedaInsumo, setBusquedaInsumo] = useState('')
  const [unidadNueva, setUnidadNueva] = useState('kg')
  const [confirmandoBase, setConfirmandoBase] = useState(false)
  const [costoPorcion, setCostoPorcion] = useState<number | null>(null)
  const [sugerida, setSugerida] = useState<{ base: string | null; encontrada: boolean; items: { insumo: string; unidad: string; cantidad: number; existe: boolean; sin_conversion: boolean }[] } | null>(null)
  const [platosConReceta, setPlatosConReceta] = useState<Set<number>>(new Set())

  const cargar = useCallback(async () => {
    try {
      const [datos, cat, conReceta] = await Promise.all([
        api.insumos(), api.catalogo(), api.platosConReceta(),
      ])
      setInsumos(datos.insumos)
      setValorInventario(datos.valor_inventario)
      setPorAgotarse(datos.por_agotarse)
      setCatalogo(cat.platos)
      setPlatosConReceta(new Set(conReceta.plato_ids))
      setError('')
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }, [onSesionVencida])

  useEffect(() => {
    cargar()
  }, [cargar])

  // El historial se trae con sus propios filtros y se refresca cada vez que
  // se entra (así un movimiento recién guardado aparece al toque)
  useEffect(() => {
    if (seccion !== 'historial') return
    const rango =
      histRango === 'manual'
        ? histFechas
        : {
            desde: fechaIso(sumarDias(new Date(), histRango === '7' ? -6 : -29)),
            hasta: fechaIso(new Date()),
          }
    let vigente = true
    api.kardex({ ...rango, insumoId: histInsumo?.id })
      .then((r) => { if (vigente) setMovimientos(r.movimientos) })
      .catch((e) => { if (vigente) setError(manejarError(e, onSesionVencida)) })
    return () => { vigente = false }
  }, [seccion, histRango, histFechas, histInsumo, onSesionVencida])

  const verMovimientosDe = (insumo: Insumo) => {
    setHistInsumo(insumo)
    setBusquedaHistorial('')
    setSeccion('historial')
  }

  const avisar = (texto: string) => {
    setMensaje(texto)
    setAviso('')
    setError('')
  }

  // ---------- Despensa: handlers ----------

  const cargarDespensa = async () => {
    try {
      const r = await api.cargarDespensaBase()
      avisar(
        r.creados.length === 0
          ? 'Tu despensa ya tiene todos los insumos típicos.'
          : `Listo: ${r.creados.length} insumo(s) típicos de fonda agregados con stock 0. Edítalos a tu gusto y registra tu primera compra o conteo.`,
      )
      cargar()
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const crearInsumo = async () => {
    if (!nuevo.nombre.trim()) return
    try {
      await api.crearInsumo(nuevo.nombre.trim(), nuevo.unidad, parseFloat(nuevo.costo) || 0)
      setNuevo({ nombre: '', unidad: 'kg', costo: '' })
      setMostrarNuevo(false)
      avisar('Insumo creado')
      cargar()
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const abrirAccion = (insumo: Insumo, tipo: 'compra' | 'merma' | 'ajuste') => {
    setAccion({ id: insumo.id, tipo })
    setAccionCantidad('')
    setAccionCosto('')
    setAccionNota('')
    setAccionMinimo(insumo.stock_minimo ? String(insumo.stock_minimo) : '')
    setConfirmandoCostoRaro(false)
    setError('')
  }

  const insumoAccion = accion ? insumos.find((i) => i.id === accion.id) : undefined
  const cantidadNum = parseFloat(accionCantidad)
  const costoNum = parseFloat(accionCosto)
  // Unitario en vivo (h. 15): un 120 donde iba 12.00 mueve el costo de
  // TODAS las recetas; se muestra y se compara antes de guardar
  const unitarioVivo =
    accion?.tipo === 'compra' && cantidadNum > 0 && costoNum > 0 ? costoNum / cantidadNum : null
  const desviacionCosto =
    unitarioVivo !== null && insumoAccion && insumoAccion.costo_unitario > 0
      ? (unitarioVivo - insumoAccion.costo_unitario) / insumoAccion.costo_unitario
      : null
  const costoRaro = desviacionCosto !== null && Math.abs(desviacionCosto) > 0.5

  const confirmarAccion = async () => {
    if (!accion || !insumoAccion) return
    if (!(cantidadNum >= 0) || (accion.tipo !== 'ajuste' && !(cantidadNum > 0))) {
      setError('Pon la cantidad.')
      return
    }
    if (accion.tipo === 'compra' && !(costoNum > 0)) {
      setError('Pon cuánto pagaste en total por esta compra: con eso se calcula el costo promedio.')
      return
    }
    // Costo fuera de lo normal (>50 % de desviación): segunda confirmación
    if (accion.tipo === 'compra' && costoRaro && !confirmandoCostoRaro) {
      setConfirmandoCostoRaro(true)
      return
    }
    try {
      await api.movimientoInsumo(
        accion.id, accion.tipo, cantidadNum,
        accion.tipo === 'compra' ? costoNum : undefined,
        accionNota.trim(),
      )
      if (accion.tipo === 'ajuste') {
        const minimo = parseFloat(accionMinimo) || 0
        if (minimo !== insumoAccion.stock_minimo) {
          await api.actualizarInsumo(accion.id, { stock_minimo: minimo })
        }
      }
      const u = insumoAccion.unidad
      avisar({
        compra: `Compra registrada: +${cantidadNum} ${u} de ${insumoAccion.nombre}` +
          (unitarioVivo !== null ? ` a ${soles(unitarioVivo)} el ${u}` : ''),
        merma: `Pérdida registrada: −${cantidadNum} ${u} de ${insumoAccion.nombre}`,
        ajuste: `${insumoAccion.nombre}: stock corregido a ${cantidadNum} ${u} según tu conteo`,
      }[accion.tipo])
      setAccion(null)
      cargar()
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const guardarMinimo = async (insumo: Insumo, valor: string) => {
    const minimo = parseFloat(valor) || 0
    if (minimo === insumo.stock_minimo) return
    try {
      await api.actualizarInsumo(insumo.id, { stock_minimo: minimo })
      // Acuse (h. 17): el guardado silencioso al perder el foco no se veía
      setMinimoAcuse(insumo.id)
      window.setTimeout(() => setMinimoAcuse(null), 1500)
      cargar()
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const bajos = insumos.filter((i) => i.bajo_minimo).length
  const insumosFiltrados = insumos.filter(
    (i) =>
      (!soloBajos || i.bajo_minimo) &&
      i.nombre.toLowerCase().includes(busquedaDespensa.trim().toLowerCase()),
  )

  // ---------- Recetas: handlers ----------

  const platoElegido = catalogo.find((p) => p.id === parseInt(recetaPlato))
  const precioPlato = platoElegido?.precio
  const unidadDe = (id: number) => insumos.find((i) => i.id === id)?.unidad ?? ''

  const cargarReceta = async (platoId: string) => {
    setRecetaPlato(platoId)
    setRecetaItems([])
    setCostoPorcion(null)
    setSugerida(null)
    setRecetaSucia(false)
    if (!platoId) return
    try {
      const [receta, sug] = await Promise.all([
        api.receta(parseInt(platoId)),
        api.recetaSugerida(parseInt(platoId)),
      ])
      setRecetaItems(receta.items.map((i) => ({ insumo_id: i.insumo_id, cantidad: String(i.cantidad) })))
      setCostoPorcion(receta.costo_porcion)
      setSugerida(sug)
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  // Navegar entre lista y editor respetando lo escrito (h. 22)
  const irA = (destino: string) => {
    if (recetaSucia) {
      setSaliendoA(destino)
      return
    }
    cargarReceta(destino)
  }

  const editarItemReceta = (idx: number, cantidad: string) => {
    setRecetaSucia(true)
    setRecetaItems((prev) => prev.map((x, i) => (i === idx ? { ...x, cantidad } : x)))
  }

  const quitarItemReceta = (idx: number) => {
    setRecetaSucia(true)
    setRecetaItems((prev) => prev.filter((_, i) => i !== idx))
  }

  const agregarInsumoAReceta = (insumoId: number) => {
    setRecetaSucia(true)
    setRecetaItems((prev) => [...prev, { insumo_id: insumoId, cantidad: '' }])
    setBuscandoInsumo(false)
  }

  const crearInsumoDesdeBuscador = async () => {
    const nombre = busquedaInsumo.trim()
    if (!nombre) return
    try {
      const creado = await api.crearInsumo(nombre, unidadNueva, 0)
      await cargar()
      agregarInsumoAReceta(creado.id)
      avisar(`Insumo «${nombre}» creado en ${unidadNueva}: ponle su cantidad por porción.`)
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const aplicarBase = async () => {
    if (!recetaPlato) return
    setConfirmandoBase(false)
    try {
      const receta = await api.aplicarRecetaSugerida(parseInt(recetaPlato))
      setRecetaItems(receta.items.map((i) => ({ insumo_id: i.insumo_id, cantidad: String(i.cantidad) })))
      setCostoPorcion(receta.costo_porcion)
      setRecetaSucia(false)
      setMensaje(
        `Receta base de ${platoElegido?.nombre ?? 'este plato'} cargada: ${receta.items.length} insumo(s). ` +
        'Ajusta las cantidades a tu mano y guarda.',
      )
      setError('')
      await cargar()
      // Lo pendiente NO es un error: canal ámbar con la acción de arreglo (h. 21)
      setAviso(receta.avisos.length > 0 ? `${receta.avisos.join(' ')} Agrégalo a mano con "+ Buscar insumo".` : '')
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const usarSugerida = () => {
    if (!recetaPlato) return
    // La base REEMPLAZA la receta guardada: hoja propia, no window.confirm
    if (recetaItems.length > 0) setConfirmandoBase(true)
    else aplicarBase()
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
      setRecetaSucia(false)
      avisar('Receta guardada (cada venta de este plato descontará estos insumos)')
      cargar()
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  // Costo y margen EN VIVO con los costos ya en memoria (h. 20): el
  // servidor sigue siendo la verdad al guardar; esto es la vista previa
  const costoVivo = recetaItems.reduce((s, it) => {
    const ins = insumos.find((x) => x.id === it.insumo_id)
    return s + (ins?.costo_unitario ?? 0) * (parseFloat(it.cantidad) || 0)
  }, 0)
  const margenVivo = precioPlato !== undefined ? precioPlato - costoVivo : null
  const margenPct =
    precioPlato !== undefined && precioPlato > 0 ? 1 - costoVivo / precioPlato : null
  const claseMargen =
    margenVivo !== null && margenVivo < 0
      ? 'margen-perdida'
      : margenPct !== null && margenPct < 0.4
        ? 'margen-justo'
        : 'margen-sano'

  // Lista de platos (h. 18): buscable, con progreso y la urgencia primero
  const sinReceta = catalogo.filter((p) => !platosConReceta.has(p.id)).length
  const rangoPlato = (p: Plato) =>
    !platosConReceta.has(p.id) ? (p.activo_hoy ? 0 : 1) : 2
  const platosFiltrados = catalogo
    .filter((p) => {
      if (filtroReceta === 'sin' && platosConReceta.has(p.id)) return false
      if (filtroReceta === 'con' && !platosConReceta.has(p.id)) return false
      return p.nombre.toLowerCase().includes(busquedaPlato.trim().toLowerCase())
    })
    .sort((a, b) => rangoPlato(a) - rangoPlato(b) || a.nombre.localeCompare(b.nombre))

  const insumosUsados = new Set(recetaItems.map((i) => i.insumo_id))
  const candidatosInsumo = insumos.filter(
    (i) =>
      !insumosUsados.has(i.id) &&
      i.nombre.toLowerCase().includes(busquedaInsumo.trim().toLowerCase()),
  )

  return (
    <div>
      <nav className="subtabs">
        <button className={seccion === 'despensa' ? 'activa' : ''} onClick={() => setSeccion('despensa')}>
          🧺 Despensa {porAgotarse.length > 0 && <span className="subtab-alerta">{porAgotarse.length}</span>}
        </button>
        <button className={seccion === 'consumo' ? 'activa' : ''} onClick={() => setSeccion('consumo')}>
          📉 Consumo
        </button>
        <button className={seccion === 'recetas' ? 'activa' : ''} onClick={() => setSeccion('recetas')}>
          📖 Recetas
        </button>
        <button className={seccion === 'historial' ? 'activa' : ''} onClick={() => setSeccion('historial')}>
          🧾 Historial
        </button>
      </nav>
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {aviso && <div className="banner-aviso">{aviso}</div>}
      {error && <div className="banner-error">{error}</div>}

      {seccion === 'despensa' && (
        <>
          {porAgotarse.length > 0 && (
            <div className="aviso-por-agotarse">
              <strong>⚠ Se está acabando:</strong>{' '}
              {porAgotarse.slice(0, 8).join(', ')}
              {porAgotarse.length > 8 && ` y ${porAgotarse.length - 8} más (filtra con el botón "bajos")`}
              . Compra antes de la próxima hora punta.
            </div>
          )}
          <div className="admin-acciones">
            <button onClick={() => setMostrarNuevo((v) => !v)}>+ Nuevo insumo</button>
            <button onClick={cargarDespensa} title="Arroz, papa, pollo, aceite… lo típico de una fonda, con stock 0 para que lo edites">
              🧺 Cargar despensa típica de fonda
            </button>
            <span className="nota-admin">Inventario valorizado: <strong>{soles(valorInventario)}</strong></span>
          </div>
          {mostrarNuevo && (
            <div className="form-insumo form-insumo-hoja">
              <div className="campo-etiquetado">
                <label>Nombre del insumo</label>
                <input placeholder="Papa, ají amarillo, aceite…" value={nuevo.nombre} autoFocus
                       onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} />
              </div>
              <div className="campo-etiquetado">
                <label>Unidad en la que lo mides</label>
                <div className="chips-unidad">
                  {UNIDADES_INSUMO.map((u) => (
                    <button key={u} type="button" className="chip-unidad" aria-pressed={nuevo.unidad === u}
                            onClick={() => setNuevo({ ...nuevo, unidad: u })}>
                      {u}
                    </button>
                  ))}
                </div>
              </div>
              <div className="campo-etiquetado">
                <label>Costo por {nuevo.unidad} (opcional)</label>
                <input type="number" inputMode="decimal" min="0"
                       placeholder="Si lo dejas vacío, se aprende de tu primera compra"
                       value={nuevo.costo} onChange={(e) => setNuevo({ ...nuevo, costo: e.target.value })} />
              </div>
              <div className="admin-acciones">
                <button className="boton-primario" onClick={crearInsumo}>Crear insumo</button>
                <button onClick={() => setMostrarNuevo(false)}>Cancelar</button>
              </div>
            </div>
          )}
          {insumos.length === 0 && (
            <div className="asistente-menu">
              <h3>Tu despensa está vacía</h3>
              <p className="nota-admin">
                Lo más rápido: <strong>"Cargar despensa típica de fonda"</strong> te pone arroz, papa,
                pollo, aceite y 60 insumos más con su unidad y un costo de referencia. Después borras
                o editas lo que no uses y registras tu primer conteo.
              </p>
            </div>
          )}
          {insumos.length > 0 && (
            <>
              <div className="admin-acciones despensa-filtros">
                <input className="buscador" placeholder="🔍 Buscar insumo…" value={busquedaDespensa}
                       onChange={(e) => setBusquedaDespensa(e.target.value)} />
                {bajos > 0 && (
                  <button className={`chip-filtro ${soloBajos ? 'activa' : ''}`}
                          onClick={() => setSoloBajos((v) => !v)}>
                    ⚠ {bajos} bajo{bajos === 1 ? '' : 's'}
                  </button>
                )}
              </div>

              {/* En celular la fila pasa a tarjeta: la tarea diaria (Compré /
                  Conté) a 56px, sin scroll horizontal escondido (h. 13) */}
              <div className="despensa-tarjetas">
                {insumosFiltrados.map((i) => (
                  <div className={`insumo-tarjeta ${i.bajo_minimo ? 'esta-bajo' : ''}`} key={i.id}>
                    <div className="insumo-tarjeta-cabecera">
                      <span className="insumo-tarjeta-nombre">{i.nombre}</span>
                      {i.bajo_minimo && <span className="insumo-tarjeta-aviso">se está acabando</span>}
                      <span className={`insumo-tarjeta-stock ${i.stock_actual < 0 ? 'stock-negativo' : ''}`}>
                        {i.stock_actual} <span className="unidad">{i.unidad}</span>
                      </span>
                    </div>
                    <div className="insumo-tarjeta-acciones">
                      <button className="boton-accion es-frecuente es-compra" onClick={() => abrirAccion(i, 'compra')}>
                        🛒 Compré
                      </button>
                      <button className="boton-accion es-frecuente" onClick={() => abrirAccion(i, 'ajuste')}>
                        📋 Conté
                      </button>
                      <button className="boton-accion es-merma" aria-label={`Registrar pérdida de ${i.nombre}`}
                              title="Se perdió" onClick={() => abrirAccion(i, 'merma')}>
                        🗑
                      </button>
                    </div>
                    <div className="insumo-tarjeta-pie">
                      <span>
                        {soles(i.costo_unitario)} el {i.unidad}
                        {i.stock_minimo > 0 && ` · avisa bajo ${i.stock_minimo} ${i.unidad}`}
                      </span>
                      <button className="enlace-historial" onClick={() => verMovimientosDe(i)}>
                        🧾 Movimientos
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {/* En tablet ancha se conserva la tabla */}
              <div className="tabla-despensa-envoltorio">
                <div className="tabla-desplazable"><table className="tabla-admin tabla-despensa tabla-editable">
                  <thead>
                    <tr>
                      <th>Insumo</th>
                      <th className="col-cantidad">Tengo</th>
                      <th className="col-cantidad" title="Avisar cuando el stock baje de aquí (vacío = sin aviso)">Avisar bajo</th>
                      <th className="col-cantidad">Costo / unidad</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {insumosFiltrados.map((i) => (
                      <tr key={i.id} className={i.bajo_minimo ? 'fila-por-agotarse' : ''}>
                        <td>{i.bajo_minimo && '⚠ '}{i.nombre} <span className="unidad-suave">({i.unidad})</span></td>
                        <td className={`col-cantidad ${i.stock_actual < 0 ? 'stock-negativo' : ''}`}>
                          <strong>{i.stock_actual}</strong> {i.unidad}
                        </td>
                        <td className="col-cantidad">
                          <input type="number" inputMode="decimal" min="0" className="input-minimo"
                                 defaultValue={i.stock_minimo || ''} placeholder="—"
                                 onBlur={(e) => guardarMinimo(i, e.target.value)} />
                          {minimoAcuse === i.id && (
                            <span className="acuse-guardado" aria-live="polite">✓ guardado</span>
                          )}
                        </td>
                        <td className="col-cantidad">{soles(i.costo_unitario)}</td>
                        <td className="celda-acciones">
                          <button className="boton-accion es-compra" onClick={() => abrirAccion(i, 'compra')}>🛒 Compré</button>
                          <button className="boton-accion" onClick={() => abrirAccion(i, 'ajuste')}>📋 Conté</button>
                          <button className="boton-accion" onClick={() => abrirAccion(i, 'merma')}>🗑 Se perdió</button>
                          <button className="boton-accion" title={`Movimientos de ${i.nombre}: cuándo se compró y cuándo se descontó`}
                                  aria-label={`Ver movimientos de ${i.nombre}`}
                                  onClick={() => verMovimientosDe(i)}>🧾</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table></div>
              </div>
            </>
          )}
          <p className="nota-admin">
            <strong>Compré</strong> suma stock y recalcula el costo promedio con lo que pagaste.
            <strong> Conté</strong> corrige el stock al número real que tienes (úsalo cada vez que
            hagas inventario). <strong>Se perdió</strong> registra merma. Las ventas descuentan
            solas según las recetas.
          </p>
        </>
      )}

      {seccion === 'consumo' && <SeccionConsumo onSesionVencida={onSesionVencida} />}

      {seccion === 'recetas' && (
        <div className="panel-recetas">
          {!recetaPlato ? (
            <>
              <div className="platos-progreso">
                <span className="cuenta">{platosConReceta.size}</span>
                <span>de {catalogo.length} platos con receta</span>
              </div>
              <div className="platos-barra">
                <i style={{ width: `${catalogo.length > 0 ? (platosConReceta.size / catalogo.length) * 100 : 0}%` }} />
              </div>
              <div className="admin-acciones despensa-filtros">
                <input className="buscador" placeholder="🔍 Buscar plato…" value={busquedaPlato}
                       onChange={(e) => setBusquedaPlato(e.target.value)} />
              </div>
              <div className="admin-acciones chips-filtro">
                <button className={`chip-filtro ${filtroReceta === 'sin' ? 'activa' : ''}`}
                        onClick={() => setFiltroReceta('sin')}>
                  Sin receta · {sinReceta}
                </button>
                <button className={`chip-filtro ${filtroReceta === 'con' ? 'activa' : ''}`}
                        onClick={() => setFiltroReceta('con')}>
                  Con receta
                </button>
                <button className={`chip-filtro ${filtroReceta === 'todos' ? 'activa' : ''}`}
                        onClick={() => setFiltroReceta('todos')}>
                  Todos
                </button>
              </div>
              <div className="platos-lista">
                {platosFiltrados.map((p) => (
                  <button className="plato-fila" key={p.id} onClick={() => irA(String(p.id))}>
                    <span className="insumo-ref">
                      <span>{platosConReceta.has(p.id) ? '✔ ' : ''}{p.nombre}</span>
                      <span className="meta">
                        {soles(p.precio)}{p.activo_hoy ? ' · en el menú de hoy' : ''}
                      </span>
                    </span>
                    {!platosConReceta.has(p.id) && (
                      <span className="etiqueta-receta-base">sin receta</span>
                    )}
                  </button>
                ))}
                {platosFiltrados.length === 0 && (
                  <p className="nota-admin platos-vacio">Ningún plato coincide con la búsqueda y el filtro.</p>
                )}
              </div>
              <p className="nota-admin">
                La receta dice cuánto insumo consume UNA porción: con eso cada venta descuenta
                stock sola y ves el costo y margen del plato.
              </p>
            </>
          ) : (
            <>
              <div className="admin-acciones">
                <button onClick={() => irA('')}>← Platos</button>
              </div>
              {platoElegido && (
                <div className="plato-cabecera">
                  <div className="fila">
                    <strong className="plato-cabecera-nombre">{platoElegido.nombre}</strong>
                    <span className="meta">se vende a {soles(platoElegido.precio)}</span>
                  </div>
                  <div className="cifras">
                    <div className="cifra">
                      <span>Costo</span>
                      <strong>{soles(costoVivo)}</strong>
                    </div>
                    {margenVivo !== null && (
                      <div className={`cifra ${claseMargen}`}>
                        <span>Te queda</span>
                        <strong>{soles(margenVivo)}</strong>
                      </div>
                    )}
                    {margenPct !== null && (
                      <div className={`cifra ${claseMargen}`}>
                        <span>Margen</span>
                        <strong>{Math.round(margenPct * 100)} %</strong>
                      </div>
                    )}
                  </div>
                </div>
              )}
              {sugerida?.encontrada && (
                <div className="sugerencia-menu">
                  <span>
                    ✨ Tengo una receta base de <strong>{sugerida.base}</strong> ({sugerida.items.length} insumos
                    {sugerida.items.some((s) => !s.existe) && '; los que no tengas se crean solos'}).
                  </span>
                  <button className="boton-grande boton-confirmar boton-sugerencia" onClick={usarSugerida}>
                    ✨ Usar receta base
                  </button>
                </div>
              )}
              {sugerida && !sugerida.encontrada && recetaItems.length === 0 && (
                <p className="nota-admin">No tengo una receta base para este plato: ármala insumo por insumo con "+ Buscar insumo".</p>
              )}
              <div className="receta-editor">
                {recetaItems.map((item, idx) => {
                  const ins = insumos.find((x) => x.id === item.insumo_id)
                  return (
                    <div className="receta-fila" key={`${item.insumo_id}-${idx}`}>
                      <span className="insumo-ref">
                        <span>{ins?.nombre ?? `Insumo #${item.insumo_id}`}</span>
                        {ins && <span className="costo">{soles(ins.costo_unitario)} el {ins.unidad}</span>}
                      </span>
                      <label className="cantidad">
                        <input type="number" inputMode="decimal" min="0" placeholder="0"
                               value={item.cantidad}
                               onChange={(e) => editarItemReceta(idx, e.target.value)} />
                        <span className="unidad-fija">{unidadDe(item.insumo_id)}</span>
                      </label>
                      <button className="quitar" aria-label={`Quitar ${ins?.nombre ?? 'insumo'}`}
                              onClick={() => quitarItemReceta(idx)}>✕</button>
                    </div>
                  )
                })}
                <div className="admin-acciones receta-acciones">
                  <button disabled={insumos.length === 0}
                          onClick={() => { setBuscandoInsumo(true); setBusquedaInsumo('') }}>
                    + Buscar insumo
                  </button>
                  <button className="boton-primario" onClick={guardarReceta} disabled={recetaItems.length === 0}>
                    💾 Guardar receta{recetaSucia ? ' *' : ''}
                  </button>
                </div>
                {insumos.length === 0 && (
                  <p className="nota-admin">Primero necesitas insumos: usa "Usar receta base" arriba o carga la despensa típica en la pestaña Despensa.</p>
                )}
              </div>
              {costoPorcion !== null && costoPorcion > 0 && (
                <div className="costo-porcion">
                  Costo guardado en el servidor: <strong>{soles(costoPorcion)}</strong> por porción.
                </div>
              )}
            </>
          )}
        </div>
      )}

      {seccion === 'historial' && (() => {
        const filtro = busquedaHistorial.trim().toLowerCase()
        const movsFiltrados = filtro
          ? movimientos.filter((m) => m.insumo.toLowerCase().includes(filtro))
          : movimientos
        return (
          <>
            <h3 className="subtitulo-resumen">
              Movimientos: cuándo se compró, se contó y se descontó por las ventas
            </h3>
            <div className="admin-acciones">
              {([['7', 'Últimos 7 días'], ['30', 'Últimos 30 días'], ['manual', 'Otras fechas']] as const).map(([valor, texto]) => (
                <button key={valor} className={histRango === valor ? 'boton-primario' : ''}
                        onClick={() => setHistRango(valor)}>
                  {texto}
                </button>
              ))}
              {histRango === 'manual' && (
                <span className="rango-manual">
                  <input type="date" value={histFechas.desde} max={histFechas.hasta}
                         onChange={(e) => e.target.value && setHistFechas((f) => ({ ...f, desde: e.target.value }))} />
                  <span>a</span>
                  <input type="date" value={histFechas.hasta} min={histFechas.desde}
                         onChange={(e) => e.target.value && setHistFechas((f) => ({ ...f, hasta: e.target.value }))} />
                </span>
              )}
            </div>
            <div className="admin-acciones despensa-filtros">
              {histInsumo ? (
                <button className="chip-filtro activa" onClick={() => setHistInsumo(null)}
                        title="Quitar el filtro y ver todos los insumos">
                  {histInsumo.nombre} ✕
                </button>
              ) : (
                <input className="buscador" placeholder="🔍 Filtrar por insumo…" value={busquedaHistorial}
                       onChange={(e) => setBusquedaHistorial(e.target.value)} />
              )}
            </div>
            <div className="tabla-desplazable"><table className="tabla-admin">
              <thead>
                <tr><th>Fecha</th><th>Hora</th><th>Insumo</th><th>Qué pasó</th><th className="col-cantidad">Cantidad</th><th>Detalle</th></tr>
              </thead>
              <tbody>
                {movsFiltrados.map((m) => (
                  <tr key={m.id}>
                    <td>{m.fecha}</td>
                    <td>{m.hora}</td>
                    <td>{m.insumo}</td>
                    <td>
                      {{ compra: '🛒 Compra', consumo: '🍽 Venta', merma: '🗑 Merma', ajuste: '📋 Conteo' }[m.tipo] ?? m.tipo}
                      {m.costo_total != null ? ` (${soles(m.costo_total)})` : ''}
                    </td>
                    <td className={`col-cantidad ${m.cantidad < 0 ? 'stock-negativo' : ''}`}>
                      {m.cantidad > 0 ? '+' : ''}{m.cantidad} {m.unidad}
                    </td>
                    <td>{m.referencia}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            {movsFiltrados.length === 0 && (
              <p className="nota-admin">
                {movimientos.length > 0
                  ? 'Ningún movimiento coincide con el filtro en estas fechas.'
                  : histInsumo
                    ? `${histInsumo.nombre} no tiene movimientos en estas fechas.`
                    : 'Sin movimientos en estas fechas. Aquí aparece cada "Compré", "Conté" y "Se perdió" de la despensa, y cada venta de un plato CON receta (con su número de orden), todos con fecha y hora.'}
              </p>
            )}
            <p className="nota-admin">
              "🍽 Venta" es el descuento automático por la receta del plato vendido (el detalle
              dice qué orden fue). Un stock en rojo significa que se vendió más de lo que el
              kardex tenía: corrígelo con "Conté" en la despensa.
            </p>
          </>
        )
      })()}

      {/* Hoja por movimiento (h. 14): color y verbo propios, efecto antes
          de confirmar. En celular sube desde abajo como hoja. */}
      {accion && insumoAccion && (
        <div className="modal-fondo hoja-abajo" onClick={() => setAccion(null)}>
          <div
            className={`modal hoja-movimiento ${
              accion.tipo === 'compra' ? 'mov-compra' : accion.tipo === 'ajuste' ? 'mov-conteo' : 'mov-merma'
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="hoja-movimiento-cabecera">
              <span className="tipo">
                {accion.tipo === 'compra' ? 'Compra' : accion.tipo === 'ajuste' ? 'Conteo de inventario' : 'Pérdida / merma'}
              </span>
              <span className="insumo">{insumoAccion.nombre}</span>
            </div>
            <div className="hoja-movimiento-cuerpo">
              <div className="campo-etiquetado">
                <label>
                  {accion.tipo === 'compra' ? '¿Cuánto compraste?'
                    : accion.tipo === 'ajuste' ? '¿Cuánto tienes EN TOTAL?'
                    : '¿Cuánto se perdió?'}
                </label>
                <div className="campo-cantidad">
                  <input type="number" inputMode="decimal" enterKeyHint="done" min="0" autoFocus
                         value={accionCantidad}
                         onChange={(e) => { setAccionCantidad(e.target.value); setConfirmandoCostoRaro(false) }}
                         onKeyDown={(e) => e.key === 'Enter' && confirmarAccion()} />
                  <span className="unidad-fija">{insumoAccion.unidad}</span>
                </div>
              </div>
              {accion.tipo === 'compra' && (
                <div className="campo-etiquetado">
                  <label>¿Cuánto pagaste en total?</label>
                  <div className="campo-cantidad">
                    <span className="unidad-fija">S/</span>
                    <input type="number" inputMode="decimal" enterKeyHint="done" min="0"
                           value={accionCosto}
                           onChange={(e) => { setAccionCosto(e.target.value); setConfirmandoCostoRaro(false) }}
                           onKeyDown={(e) => e.key === 'Enter' && confirmarAccion()} />
                  </div>
                </div>
              )}
              {accion.tipo === 'compra' && unitarioVivo !== null && (
                <div className={`linea-efecto ${costoRaro ? 'efecto-raro' : ''}`}>
                  Te queda a <strong>{soles(unitarioVivo)} el {insumoAccion.unidad}</strong>.
                  {desviacionCosto !== null && (
                    <> Antes pagabas {soles(insumoAccion.costo_unitario)} —{' '}
                    {desviacionCosto >= 0 ? 'sube' : 'baja'} {Math.abs(Math.round(desviacionCosto * 100))} %.</>
                  )}
                  {costoRaro && <strong> Revisa el monto antes de guardar.</strong>}
                </div>
              )}
              {cantidadNum > 0 && (
                <div className="linea-efecto">
                  {accion.tipo === 'compra' && (
                    <>Sumas {cantidadNum} {insumoAccion.unidad}. Quedas con{' '}
                    <strong>{redondear(insumoAccion.stock_actual + cantidadNum)} {insumoAccion.unidad}</strong>.</>
                  )}
                  {accion.tipo === 'ajuste' && (
                    <>El stock pasa de {insumoAccion.stock_actual} a{' '}
                    <strong>{cantidadNum} {insumoAccion.unidad}</strong>. Se registra un conteo, no una compra.</>
                  )}
                  {accion.tipo === 'merma' && (
                    <>Descuentas {cantidadNum} {insumoAccion.unidad}. Quedas con{' '}
                    <strong>{redondear(insumoAccion.stock_actual - cantidadNum)} {insumoAccion.unidad}</strong>.</>
                  )}
                </div>
              )}
              {accion.tipo === 'ajuste' && (
                <div className="campo-etiquetado">
                  <label>Avisar cuando quede menos de (opcional)</label>
                  <div className="campo-cantidad campo-cantidad-chico">
                    <input type="number" inputMode="decimal" min="0" placeholder="—"
                           value={accionMinimo} onChange={(e) => setAccionMinimo(e.target.value)} />
                    <span className="unidad-fija">{insumoAccion.unidad}</span>
                  </div>
                </div>
              )}
              <div className="campo-etiquetado">
                <label>Nota (opcional)</label>
                <input className="input-nota-hoja"
                       placeholder={accion.tipo === 'compra' ? 'dónde / a quién' : 'qué pasó'}
                       maxLength={200} value={accionNota}
                       onChange={(e) => setAccionNota(e.target.value)}
                       onKeyDown={(e) => e.key === 'Enter' && confirmarAccion()} />
              </div>
              {error && <div className="banner-error">{error}</div>}
              <div className="admin-acciones hoja-acciones">
                <button className="boton-primario" onClick={confirmarAccion}>
                  {confirmandoCostoRaro
                    ? 'Sí, pagué eso'
                    : accion.tipo === 'compra' ? 'Guardar compra'
                    : accion.tipo === 'ajuste' ? 'Guardar conteo'
                    : 'Registrar pérdida'}
                </button>
                <button onClick={() => setAccion(null)}>Cancelar</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Buscador de insumo para la receta (h. 19): excluye los ya usados
          y ofrece crear el que no existe */}
      {buscandoInsumo && (
        <div className="modal-fondo" onClick={() => setBuscandoInsumo(false)}>
          <div className="modal modal-buscar-insumo" onClick={(e) => e.stopPropagation()}>
            <h2>Agregar insumo a la receta</h2>
            <input className="buscador" autoFocus placeholder="🔍 ají amarillo, papa…"
                   value={busquedaInsumo} onChange={(e) => setBusquedaInsumo(e.target.value)} />
            <div className="platos-lista lista-insumos">
              {candidatosInsumo.map((i) => (
                <button className="plato-fila" key={i.id} onClick={() => agregarInsumoAReceta(i.id)}>
                  <span className="insumo-ref">
                    <span>{i.nombre}</span>
                    <span className="meta">{soles(i.costo_unitario)} el {i.unidad} · tienes {i.stock_actual}</span>
                  </span>
                </button>
              ))}
              {candidatosInsumo.length === 0 && busquedaInsumo.trim() !== '' && (
                <div className="crear-desde-buscador">
                  <p>No existe «{busquedaInsumo.trim()}» en tu despensa.</p>
                  <div className="chips-unidad">
                    {UNIDADES_INSUMO.map((u) => (
                      <button key={u} type="button" className="chip-unidad" aria-pressed={unidadNueva === u}
                              onClick={() => setUnidadNueva(u)}>
                        {u}
                      </button>
                    ))}
                  </div>
                  <button className="boton-primario" onClick={crearInsumoDesdeBuscador}>
                    Crear «{busquedaInsumo.trim()}» en {unidadNueva} y agregarlo
                  </button>
                </div>
              )}
              {candidatosInsumo.length === 0 && busquedaInsumo.trim() === '' && (
                <p className="nota-admin platos-vacio">Todos tus insumos ya están en esta receta.</p>
              )}
            </div>
            <button className="boton-grande boton-secundario" onClick={() => setBuscandoInsumo(false)}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Reemplazar por la receta base: hoja propia, no window.confirm (h. 21) */}
      {confirmandoBase && (
        <div className="modal-fondo" onClick={() => setConfirmandoBase(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>¿Usar la receta base?</h2>
            <p>
              {platoElegido?.nombre ?? 'Este plato'} ya tiene una receta con{' '}
              <strong>{recetaItems.length} insumo(s)</strong>. La base la reemplaza y lo que
              ajustaste a mano se pierde.
            </p>
            <div className="modal-botones">
              <button className="boton-grande boton-secundario" onClick={() => setConfirmandoBase(false)}>
                Cancelar
              </button>
              <button className="boton-grande boton-confirmar" onClick={aplicarBase}>
                Sí, usar la base
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cambios sin guardar (h. 22): nada se borra sin preguntar */}
      {saliendoA !== null && (
        <div className="modal-fondo">
          <div className="modal">
            <h2>Tienes cambios sin guardar</h2>
            <p>La receta de {platoElegido?.nombre ?? 'este plato'} tiene ajustes que no se guardaron.</p>
            <div className="modal-botones modal-botones-columna">
              <button
                className="boton-grande boton-confirmar"
                onClick={async () => {
                  const destino = saliendoA
                  setSaliendoA(null)
                  await guardarReceta()
                  cargarReceta(destino)
                }}
              >
                💾 Guardar y salir
              </button>
              <button
                className="boton-grande boton-secundario"
                onClick={() => {
                  const destino = saliendoA
                  setSaliendoA(null)
                  cargarReceta(destino)
                }}
              >
                Salir sin guardar
              </button>
              <button className="boton-grande boton-secundario" onClick={() => setSaliendoA(null)}>
                Seguir editando
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


// ---------- Agregados del menú (+presa, +refresco…) ----------

interface AgregadoEditable {
  id?: number
  nombre: string
  precio: string // como texto mientras se edita
  activo: boolean
}

function EditorAgregados({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [agregados, setAgregados] = useState<AgregadoEditable[]>([])
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.agregadosMenu()
      .then((r) => setAgregados(r.agregados.map((a) => ({ ...a, precio: a.precio.toFixed(2) }))))
      .catch((e) => setError(manejarError(e, onSesionVencida)))
  }, [onSesionVencida])

  const editar = (idx: number, cambios: Partial<AgregadoEditable>) => {
    setAgregados((prev) => prev.map((a, i) => (i === idx ? { ...a, ...cambios } : a)))
  }

  const guardar = async () => {
    setError('')
    const validos = agregados.filter((a) => a.nombre.trim() !== '')
    const sinPrecio = validos.filter((a) => !(parseFloat(a.precio) > 0))
    if (sinPrecio.length > 0) {
      setError(`Pon el precio de: ${sinPrecio.map((a) => a.nombre).join(', ')}.`)
      return
    }
    try {
      const r = await api.guardarAgregadosMenu(validos.map((a) => ({
        id: a.id, nombre: a.nombre.trim(), precio: parseFloat(a.precio), activo: a.activo,
      })))
      setAgregados(r.agregados.map((a) => ({ ...a, precio: a.precio.toFixed(2) })))
      setMensaje('Agregados guardados ✔')
      setTimeout(() => setMensaje(''), 3000)
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  return (
    <div className="editor-plantillas editor-agregados">
      <h2 className="titulo-categoria">Agregados del menú (+ presa, + refresco…)</h2>
      <p className="nota-admin">
        Porciones que el cliente puede sumar a cualquier menú, cada una con su precio. No son
        platos de la carta: la presa extra, más arroz, más ensalada. Apaga la que no quieras
        ofrecer hoy. Ojo: por ahora los agregados NO descuentan del kardex (no tienen receta);
        si vendes muchos, ajusta el stock con "Conté".
      </p>
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {error && <div className="banner-error">{error}</div>}
      {agregados.map((a, idx) => (
        <div className="fila-agregado" key={a.id ?? `nuevo-${idx}`}>
          <input
            value={a.nombre}
            onChange={(e) => editar(idx, { nombre: e.target.value })}
            placeholder="Nombre (ej. Presa)"
            maxLength={60}
          />
          <label>
            S/{' '}
            <input
              type="number" step="0.50" min="0" className="input-precio"
              value={a.precio}
              onChange={(e) => editar(idx, { precio: e.target.value })}
            />
          </label>
          <label className="check-agregado">
            <input
              type="checkbox"
              checked={a.activo}
              onChange={(e) => editar(idx, { activo: e.target.checked })}
            />{' '}
            se ofrece
          </label>
          <button
            className="boton-quitar"
            onClick={() => setAgregados((prev) => prev.filter((_, i) => i !== idx))}
          >
            ✕
          </button>
        </div>
      ))}
      <div className="admin-acciones">
        <button onClick={() => setAgregados((prev) => [...prev, { nombre: '', precio: '', activo: true }])}>
          + Nuevo agregado
        </button>
        <button className="boton-primario" onClick={guardar}>💾 Guardar agregados</button>
      </div>
    </div>
  )
}

// ---------- Consumo semanal del kardex ----------

type RangoConsumo = 'semana' | 'semana-pasada' | 'mes' | 'manual'

function lunesDe(d: Date): Date {
  return sumarDias(d, -((d.getDay() + 6) % 7)) // getDay(): 0 = domingo
}

function rangoConsumoDe(rango: RangoConsumo, hoy = new Date()): { desde: string; hasta: string } {
  if (rango === 'semana') return { desde: fechaIso(lunesDe(hoy)), hasta: fechaIso(hoy) }
  if (rango === 'semana-pasada') {
    const lunesPasado = sumarDias(lunesDe(hoy), -7)
    return { desde: fechaIso(lunesPasado), hasta: fechaIso(sumarDias(lunesPasado, 6)) }
  }
  return { desde: fechaIso(sumarDias(hoy, -29)), hasta: fechaIso(hoy) } // últimos 30 días
}

const DIA_CORTO = ['Do', 'Lu', 'Ma', 'Mi', 'Ju', 'Vi', 'Sá']

function etiquetaDia(fechaIso: string): string {
  const [a, m, d] = fechaIso.split('-').map(Number)
  const fecha = new Date(a, m - 1, d)
  return `${DIA_CORTO[fecha.getDay()]} ${d}`
}

function SeccionConsumo({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [rango, setRango] = useState<RangoConsumo>('semana')
  const [fechas, setFechas] = useState(() => rangoConsumoDe('semana'))
  const [datos, setDatos] = useState<ReporteConsumo | null>(null)
  // Cuántos platos alimentan de verdad este reporte: solo los CON receta
  // descuentan insumos al venderse. Sin esto, un "S/ 0.00" parece bug.
  const [cobertura, setCobertura] = useState<{ con: number; total: number } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api.catalogo(), api.platosConReceta()])
      .then(([cat, recetas]) => setCobertura({ con: recetas.plato_ids.length, total: cat.platos.length }))
      .catch(() => setCobertura(null)) // sin cobertura el reporte sigue sirviendo
  }, [])

  useEffect(() => {
    // Si el dueño cambia de rango antes de que llegue la respuesta anterior,
    // esa respuesta se descarta: si no, quedarían datos de otras fechas
    let vigente = true
    api.consumoKardex(fechas.desde, fechas.hasta)
      .then((r) => { if (vigente) { setDatos(r); setError('') } })
      .catch((e) => {
        if (!vigente) return
        setDatos(null)   // no dejar el reporte anterior bajo el aviso de error
        setError(manejarError(e, onSesionVencida))
      })
    return () => { vigente = false }
  }, [fechas, onSesionVencida])

  const elegirRango = (nuevo: RangoConsumo) => {
    setRango(nuevo)
    if (nuevo !== 'manual') setFechas(rangoConsumoDe(nuevo))
  }

  const descargar = async () => {
    try {
      await api.descargarConsumoCsv(fechas.desde, fechas.hasta)
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  const maximoDia = Math.max(1, ...(datos?.por_dia ?? []).map((d) => d.soles))
  // Con muchos días las barras se angostan y solo se rotula una de cada tres;
  // el valor exacto de cada día sale al tocarla.
  const compacto = (datos?.por_dia.length ?? 0) > 14

  // Un rango largo no cabe entero: se muestra pegado al final (los días
  // recientes), que es lo que el dueño mira primero.
  const barras = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (barras.current) barras.current.scrollLeft = barras.current.scrollWidth
  }, [datos])

  return (
    <>
      <div className="admin-acciones">
        {([['semana', 'Esta semana'], ['semana-pasada', 'Semana pasada'], ['mes', 'Últimos 30 días'],
           ['manual', 'Otras fechas']] as [RangoConsumo, string][]).map(([valor, texto]) => (
          <button key={valor} className={rango === valor ? 'boton-primario' : ''}
                  onClick={() => elegirRango(valor)}>
            {texto}
          </button>
        ))}
        {rango === 'manual' && (
          <span className="rango-manual">
            <input type="date" value={fechas.desde} max={fechas.hasta}
                   onChange={(e) => e.target.value && setFechas((f) => ({ ...f, desde: e.target.value }))} />
            <span>a</span>
            <input type="date" value={fechas.hasta} min={fechas.desde}
                   onChange={(e) => e.target.value && setFechas((f) => ({ ...f, hasta: e.target.value }))} />
          </span>
        )}
      </div>

      {error && <div className="banner-error">{error}</div>}
      {!datos && !error && <p className="nota-admin">Cargando…</p>}

      {cobertura && cobertura.con === 0 && cobertura.total > 0 && (
        <div className="banner-aviso">
          <strong>Ninguno de tus {cobertura.total} platos tiene receta todavía</strong>, así que
          las ventas no descuentan insumos ni suman soles aquí. Ármalas en la pestaña{' '}
          <strong>Recetas</strong> (con "✨ Usar receta base" es un toque por plato): desde ese
          momento cada plato vendido se calcula solo. Las ventas anteriores no se recalculan.
        </div>
      )}
      {cobertura && cobertura.con > 0 && cobertura.con < cobertura.total && (
        <div className="banner-aviso">
          Este cálculo cubre los platos CON receta: <strong>{cobertura.con} de{' '}
          {cobertura.total}</strong> la tienen. Lo vendido de los otros{' '}
          {cobertura.total - cobertura.con} no descuenta insumos ni suma aquí — complétalos en
          la pestaña <strong>Recetas</strong>. Cuenta desde que guardas la receta: las ventas
          de antes no se recalculan, lo de hoy aparece apenas vendas.
        </div>
      )}

      {datos && (
        <>
          <div className="tarjetas-consumo">
            <div className="tarjeta-consumo">
              <span className="tarjeta-consumo-rotulo">Compraste</span>
              <strong>{soles(datos.gasto_compras)}</strong>
              <span className="nota-admin">lo que pagaste por insumos</span>
            </div>
            <div className="tarjeta-consumo">
              <span className="tarjeta-consumo-rotulo">Se usó en los platos</span>
              <strong>{soles(datos.valor_consumo)}</strong>
              <span className="nota-admin">valorizado al costo de hoy</span>
            </div>
            <div className={`tarjeta-consumo ${datos.valor_mermas > 0 ? 'alerta' : ''}`}>
              <span className="tarjeta-consumo-rotulo">Se perdió</span>
              <strong>{soles(datos.valor_mermas)}</strong>
              <span className="nota-admin">mermas registradas</span>
            </div>
            <div className={`tarjeta-consumo ${datos.por_agotarse.length > 0 ? 'alerta' : ''}`}>
              <span className="tarjeta-consumo-rotulo">Por agotarse</span>
              <strong>{datos.por_agotarse.length}</strong>
              <span className="nota-admin">
                {datos.por_agotarse.length > 0 ? datos.por_agotarse.join(', ') : 'nada bajo el mínimo'}
              </span>
            </div>
          </div>

          <h3 className="subtitulo-resumen">Cuánto se usó cada día</h3>
          <div className="barras-horas" ref={barras}>
            {datos.por_dia.map((d, n) => (
              <div className={`barra-hora barra-dia ${compacto ? 'barra-dia-compacta' : ''}`}
                   key={d.fecha} title={`${d.fecha}: ${soles(d.soles)}`}>
                {/* Un número sobre cada barra estorba: en rangos largos se rotula el día más alto */}
                <span className="barra-hora-valor">
                  {d.soles > 0 && (!compacto || d.soles === maximoDia) ? soles(d.soles) : ''}
                </span>
                {d.soles > 0 && (
                  <div className="barra-hora-relleno" style={{ height: `${(d.soles / maximoDia) * 100}%` }} />
                )}
                <span className="barra-hora-etiqueta">
                  {!compacto || n % 3 === 0 || n === datos.por_dia.length - 1 ? etiquetaDia(d.fecha) : ''}
                </span>
              </div>
            ))}
          </div>

          <div className="admin-acciones">
            <button onClick={descargar}>📊 Descargar Excel (CSV)</button>
            <span className="nota-admin">
              Del {datos.desde} al {datos.hasta} ({datos.dias} {datos.dias === 1 ? 'día' : 'días'})
            </span>
          </div>

          <div className="tabla-desplazable">
            <table className="tabla-admin">
              <thead>
                <tr>
                  <th>Insumo</th>
                  <th className="col-cantidad">Se usó</th>
                  <th className="col-cantidad">Costo</th>
                  <th className="col-cantidad">Compraste</th>
                  <th className="col-cantidad">Pagaste</th>
                  <th className="col-cantidad">Se perdió</th>
                  <th className="col-cantidad">Queda hoy</th>
                  <th className="col-cantidad">Alcanza para</th>
                </tr>
              </thead>
              <tbody>
                {datos.insumos.map((i) => (
                  <tr key={i.id} className={i.bajo_minimo ? 'fila-alerta' : ''}>
                    <td>{i.nombre}</td>
                    <td className="col-cantidad">{i.consumido} {i.unidad}</td>
                    <td className="col-cantidad">{soles(i.consumido_soles)}</td>
                    <td className="col-cantidad">{i.comprado ? `${i.comprado} ${i.unidad}` : ''}</td>
                    <td className="col-cantidad">{i.comprado_soles ? soles(i.comprado_soles) : ''}</td>
                    <td className="col-cantidad">{i.merma ? `${i.merma} ${i.unidad}` : ''}</td>
                    <td className={`col-cantidad ${i.stock_actual < 0 ? 'stock-negativo' : ''}`}>
                      {i.stock_actual} {i.unidad}
                    </td>
                    <td className={`col-cantidad ${i.dias_stock != null && i.dias_stock < 2 ? 'stock-negativo' : ''}`}>
                      {i.dias_stock == null ? '—' : `${i.dias_stock} días`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {datos.insumos.length === 0 && (
            <p className="nota-admin">
              No hubo movimientos de insumos en estas fechas. Aparecen aquí las ventas de platos
              con receta, las compras, las mermas y los conteos.
            </p>
          )}
          <p className="nota-admin">
            "Queda hoy" y el resaltado son el stock de este momento, no el de esas fechas;
            "Alcanza para" proyecta ese stock con el ritmo de consumo del rango. Lo usado se
            valoriza al costo promedio de hoy: es una guía para comprar, no un número contable.
          </p>
        </>
      )}
    </>
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
      <div className="tabla-desplazable"><table className="tabla-admin">
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
      </table></div>
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
        Tanda de cocina: agrupar pedidos con hasta estos minutos de diferencia (0 = apagado)
        <input
          type="number"
          min="0"
          max="60"
          value={config.cocina_bulk_min}
          onChange={(e) => setConfig({ ...config, cocina_bulk_min: parseInt(e.target.value) || 0 })}
        />
      </label>
      <p className="nota-admin">
        En la tira "Por salir" de cocina, cada plato muestra además su <strong>tanda</strong>: las
        porciones del pedido más antiguo más los que llegaron en los siguientes minutos configurados.
        Al tocar el plato para tachar, esa cantidad viene sugerida.
      </p>
      <label>
        El táper cuesta S/ extra por porción (0 = gratis)
        <input
          type="number"
          min="0"
          step="0.50"
          value={config.precio_taper}
          onChange={(e) => setConfig({ ...config, precio_taper: parseFloat(e.target.value) || 0 })}
        />
      </label>
      <div className="config-empaques">
        <span>Empaques que se ofrecen (mesa siempre va):</span>
        {(['taper', 'bolsa', 'lonchera'] as Empaque[]).map((e) => (
          <label key={e} className="check-agregado">
            <input
              type="checkbox"
              checked={config.empaques_ofrecidos.includes(e)}
              onChange={(ev) => setConfig({
                ...config,
                empaques_ofrecidos: ev.target.checked
                  ? [...config.empaques_ofrecidos, e]
                  : config.empaques_ofrecidos.filter((x) => x !== e),
              })}
            />{' '}
            {NOMBRE_EMPAQUE[e]}
          </label>
        ))}
      </div>
      <p className="nota-admin">
        El cargo del táper sale como línea "Táper × N" en el ticket y entra al total; cocina no
        la ve. Los empaques apagados desaparecen de la terminal y de la caja.
      </p>
      <label>
        ¿Dónde se imprimen los tickets?
        <select
          value={config.modo_impresion}
          onChange={(e) =>
            setConfig({ ...config, modo_impresion: e.target.value as 'terminal' | 'estacion' | 'puente' })
          }
        >
          <option value="terminal">En la terminal del cliente (PC con impresora conectada)</option>
          <option value="estacion">Estación de impresión (/ticketera en la PC de la impresora)</option>
          <option value="puente">Puente del local → impresora de red (recomendado con tablets)</option>
        </select>
      </label>
      {config.modo_impresion === 'estacion' && (
        <p className="nota-admin">
          Modo para terminales tablet: abre <strong>/ticketera</strong> en la computadora que tiene
          la impresora conectada y déjala abierta. Los tickets de todas las terminales salen por ahí.
        </p>
      )}
      {config.modo_impresion === 'puente' && (
        <div className="panel-impresora">
          <p className="nota-admin">
            En este modo los tickets van DIRECTO a la impresora de red (como hacen las apps de
            POS): sin diálogos y con corte automático. Quién los manda, tú eliges:
            <strong> sin PC</strong> — abre <strong>/ticketera</strong> en una tablet con la app
            gratuita <strong>RawBT</strong> instalada y toca "Activar impresión en esta tablet";
            o <strong>con PC</strong> — corre <code>scripts\puente.bat</code> y déjalo abierto.
            Usa una de las dos, no ambas a la vez.
          </p>
          <label>
            IP de la impresora en la red del local (ej. 192.168.1.77)
            <input
              value={config.impresora_ip}
              placeholder="192.168.1.77"
              onChange={(e) => setConfig({ ...config, impresora_ip: e.target.value.trim() })}
            />
          </label>
          <label>
            Puerto (casi siempre 9100)
            <input
              type="number" min="1" max="65535"
              value={config.impresora_puerto}
              onChange={(e) => setConfig({ ...config, impresora_puerto: parseInt(e.target.value) || 9100 })}
            />
          </label>
          <label>
            Ancho del ticket en caracteres (48 o 42, según el modelo de 80 mm)
            <input
              type="number" min="24" max="64"
              value={config.impresora_columnas}
              onChange={(e) => setConfig({ ...config, impresora_columnas: parseInt(e.target.value) || 42 })}
            />
          </label>
          <button
            onClick={async () => {
              setMensaje('')
              setError('')
              try {
                // Guarda primero (para que el puente use la IP recién puesta)
                setConfig(await api.guardarConfig(config))
                await api.imprimirPrueba()
                setMensaje('Ticket de prueba encolado ✔ — debe salir en unos segundos si el puente está corriendo')
              } catch (e) {
                setError(manejarError(e, onSesionVencida))
              }
            }}
          >
            🖨 Imprimir ticket de prueba
          </button>
          <p className="nota-admin">
            ¿Dónde veo la IP de la impresora? Casi todas imprimen su configuración al prenderlas
            manteniendo el botón FEED apretado, o revisa la lista de equipos en tu router. Es la
            misma IP que usabas en Loyverse.
          </p>
        </div>
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
          checked={config.terminal_solo_menus}
          onChange={(e) => setConfig({ ...config, terminal_solo_menus: e.target.checked })}
        />
        🍽 Terminal y caja muestran SOLO los menús (sin lista de platos sueltos)
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
      <EmpezarLimpio onSesionVencida={onSesionVencida} />
    </div>
  )
}

// ---------- Asistente: crear el menú del día en un minuto ----------

// "quitar": cuánto baja el menú si el cliente lo quita ("sin sopa"),
// editable después en el editor — decisión del dueño: sí baja un poco
const TIEMPOS_POR_CATEGORIA: { categoria: string; rotulo: string; extra: string; quitar: string }[] = [
  { categoria: 'entrada', rotulo: 'Entrada o sopa', extra: '3.00', quitar: '1.00' },
  { categoria: 'fondo', rotulo: 'Segundo', extra: '', quitar: '' },
  { categoria: 'bebida', rotulo: 'Refresco', extra: '', quitar: '' },
  { categoria: 'postre', rotulo: 'Postre', extra: '', quitar: '' },
]

/**
 * Lo que se aprendió en sala: el dueño no arma el menú a mano tiempo por
 * tiempo. Aquí marca los platos de hoy por categoría, pone el precio y el
 * menú queda creado. El editor de abajo sigue para afinar.
 */
function AsistenteMenu({
  catalogo,
  yaHayMenus,
  onCrear,
}: {
  catalogo: Plato[]
  yaHayMenus: boolean
  onCrear: (nueva: PlantillaEditable) => Promise<boolean>
}) {
  const [abierto, setAbierto] = useState(!yaHayMenus)
  const [nombre, setNombre] = useState('Menú del día')
  const [precio, setPrecio] = useState('')
  const [extraEntrada, setExtraEntrada] = useState('3.00')
  const [marcados, setMarcados] = useState<Set<number>>(new Set())
  const [aviso, setAviso] = useState('')

  useEffect(() => {
    setAbierto(!yaHayMenus)
  }, [yaHayMenus])

  const activos = catalogo.filter((p) => p.activo_hoy)
  const alternar = (id: number) =>
    setMarcados((prev) => {
      const s = new Set(prev)
      if (s.has(id)) s.delete(id)
      else s.add(id)
      return s
    })
  const marcarCategoria = (categoria: string, valor: boolean) =>
    setMarcados((prev) => {
      const s = new Set(prev)
      for (const p of activos.filter((x) => x.categoria === categoria)) {
        if (valor) s.add(p.id)
        else s.delete(p.id)
      }
      return s
    })

  const crear = async () => {
    setAviso('')
    if (!(parseFloat(precio) > 0)) {
      setAviso('Pon el precio del menú (ej. 11.00).')
      return
    }
    const tiempos: TiempoEditable[] = TIEMPOS_POR_CATEGORIA
      .map((t) => ({
        rotulo: t.rotulo,
        obligatorio: true,
        precio_extra: t.categoria === 'entrada' ? extraEntrada : t.extra,
        descuento_quitar: t.quitar,
        alternativas: activos
          .filter((p) => p.categoria === t.categoria && marcados.has(p.id))
          .map((p) => ({ plato_id: p.id, recargo: '' })),
      }))
      .filter((t) => t.alternativas.length > 0)
    const tieneSegundo = tiempos.some((t) => t.rotulo === 'Segundo')
    if (tiempos.length < 2 || !tieneSegundo) {
      setAviso('Marca al menos un segundo y un acompañamiento (entrada o refresco).')
      return
    }
    const ok = await onCrear({ nombre: nombre.trim() || 'Menú del día', precio, activo_hoy: true, tiempos })
    if (ok) {
      setAbierto(false)
      setMarcados(new Set())
      setPrecio('')
    }
  }

  if (!abierto) {
    return (
      <button className="boton-asistente" onClick={() => setAbierto(true)}>
        ✨ Crear otro menú en un minuto
      </button>
    )
  }

  return (
    <div className="asistente-menu">
      <h3>✨ Crea tu menú del día en un minuto</h3>
      {activos.length === 0 && (
        <p className="nota-admin">
          Primero carga y guarda los platos de hoy en la tabla de arriba; después vuelve aquí y
          márcalos.
        </p>
      )}
      <div className="asistente-fila">
        <label>
          Nombre
          <input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Menú del día" />
        </label>
        <label>
          Precio del menú S/
          <input
            type="number" step="0.50" min="0" className="input-precio"
            value={precio} onChange={(e) => setPrecio(e.target.value)} placeholder="11.00"
          />
        </label>
        <label title="Precio de una entrada adicional pedida con el menú (vacío = no se ofrece)">
          Entrada extra S/
          <input
            type="number" step="0.50" min="0" className="input-precio"
            value={extraEntrada} onChange={(e) => setExtraEntrada(e.target.value)} placeholder="3.00"
          />
        </label>
      </div>
      {TIEMPOS_POR_CATEGORIA.map((t) => {
        const platos = activos.filter((p) => p.categoria === t.categoria)
        if (platos.length === 0) return null
        const todos = platos.every((p) => marcados.has(p.id))
        return (
          <div className="asistente-tiempo" key={t.categoria}>
            <div className="asistente-tiempo-cabecera">
              <strong>{t.rotulo}</strong>
              <button onClick={() => marcarCategoria(t.categoria, !todos)}>
                {todos ? 'Quitar todos' : 'Marcar todos'}
              </button>
            </div>
            <div className="asistente-chips">
              {platos.map((p) => (
                <label key={p.id} className={`chip-marcable ${marcados.has(p.id) ? 'marcado' : ''}`}>
                  <input type="checkbox" checked={marcados.has(p.id)} onChange={() => alternar(p.id)} />
                  {p.nombre}
                </label>
              ))}
            </div>
          </div>
        )
      })}
      {aviso && <div className="banner-error">{aviso}</div>}
      <div className="admin-acciones">
        <button className="boton-primario" onClick={crear} disabled={activos.length === 0}>
          ✅ Crear menú
        </button>
        {yaHayMenus && <button onClick={() => setAbierto(false)}>Cancelar</button>}
      </div>
      <p className="nota-admin">
        Se cobra el precio del menú, no la suma de los platos. Un tiempo con un solo plato marcado
        (ej. una sola chicha) sale como "incluido" sin preguntar. Abajo puedes afinar recargos y
        extras por plato.
      </p>
    </div>
  )
}

// ---------- Empezar limpio: borrar los datos de prueba ----------

/**
 * Tras las pruebas queda basura en la base (pedidos falsos, cierres de caja
 * de prueba). Si el local abre así, el Resumen del primer día real sale
 * contaminado. Esto borra SOLO el movimiento y conserva la configuración.
 */
function EmpezarLimpio({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [datos, setDatos] = useState<ResumenDatos | null>(null)
  const [abierto, setAbierto] = useState(false)
  const [confirmacion, setConfirmacion] = useState('')
  const [reiniciarStock, setReiniciarStock] = useState(true)
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')

  const cargar = useCallback(() => {
    api.resumenDatos().then(setDatos).catch(() => {})
  }, [])

  useEffect(() => {
    cargar()
  }, [cargar])

  const total = datos
    ? datos.ordenes + datos.cancelaciones + datos.cierres_caja + datos.movimientos_kardex
    : 0

  const borrar = async () => {
    setError('')
    setMensaje('')
    try {
      const r = await api.reiniciarDatos(confirmacion, reiniciarStock)
      setMensaje(
        `Listo: se borraron ${r.borrado.ordenes} pedido(s), ${r.borrado.cancelaciones} ` +
        `cancelación(es) y ${r.borrado.cierres_caja} cierre(s) de caja. ` +
        'El local queda como nuevo, con tu menú y tus mesas intactos.',
      )
      setAbierto(false)
      setConfirmacion('')
      cargar()
    } catch (e) {
      setError(manejarError(e, onSesionVencida))
    }
  }

  return (
    <div className="panel-peligro">
      <h3 className="subtitulo-resumen">🧹 Empezar limpio</h3>
      <p className="nota-admin">
        Borra los pedidos, cancelaciones, cierres de caja y kardex de las <strong>pruebas</strong>,
        para que tu primer día real arranque con números limpios y el pedido #001.
        <strong> No toca</strong> tu menú, tus menús encadenados, mesas, insumos, recetas ni la
        configuración. Esto no se puede deshacer.
      </p>
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {error && <div className="banner-error">{error}</div>}
      {datos && total === 0 && !mensaje && (
        <p className="nota-admin">No hay nada que borrar: la base ya está limpia. 🎉</p>
      )}
      {datos && total > 0 && !abierto && (
        <>
          <p className="nota-admin">
            Hoy hay <strong>{datos.ordenes}</strong> pedido(s), <strong>{datos.cancelaciones}</strong>{' '}
            cancelación(es), <strong>{datos.cierres_caja}</strong> registro(s) de caja y{' '}
            <strong>{datos.movimientos_kardex}</strong> movimiento(s) de kardex.
          </p>
          <button className="boton-borrar-datos" onClick={() => setAbierto(true)}>
            🧹 Borrar los datos de prueba…
          </button>
        </>
      )}
      {abierto && (
        <div className="confirmar-borrado">
          <label>
            <span>Escribe <strong>BORRAR</strong> para confirmar</span>
            <input
              value={confirmacion}
              onChange={(e) => setConfirmacion(e.target.value)}
              placeholder="BORRAR"
              autoFocus
            />
          </label>
          <label className="config-toggle">
            <input
              type="checkbox"
              checked={reiniciarStock}
              onChange={(e) => setReiniciarStock(e.target.checked)}
            />{' '}
            Dejar el stock de insumos en 0 (recomendado: luego haces tu conteo real)
          </label>
          <div className="modal-botones">
            <button className="boton-grande boton-secundario" onClick={() => { setAbierto(false); setConfirmacion('') }}>
              Cancelar
            </button>
            <button
              className="boton-grande boton-cancelar-rojo"
              disabled={confirmacion.trim().toUpperCase() !== 'BORRAR'}
              onClick={borrar}
            >
              Sí, borrar y empezar limpio
            </button>
          </div>
        </div>
      )}
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
