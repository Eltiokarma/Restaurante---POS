import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, clearAdminToken, getAdminToken, setAdminToken, soles, NOMBRE_CATEGORIA } from '../api'
import type { ConfigOut, DatosLocal, OrdenOut, Plato } from '../api'
import { Ticket } from '../components/Ticket'

type Tab = 'menu' | 'ordenes' | 'cancelaciones' | 'config'

interface PlatoEditable {
  id?: number
  nombre: string
  categoria: string
  precio: string // como texto mientras se edita
  activo_hoy: boolean
}

export function Admin() {
  const [logueado, setLogueado] = useState(() => getAdminToken() !== '')
  const [tab, setTab] = useState<Tab>('menu')

  if (!logueado) {
    return <AdminLogin onOk={() => setLogueado(true)} />
  }

  return (
    <div className="pantalla-admin">
      <header className="admin-cabecera">
        <h1>⚙️ Administración</h1>
        <nav className="admin-tabs">
          <button className={tab === 'menu' ? 'activa' : ''} onClick={() => setTab('menu')}>Menú del día</button>
          <button className={tab === 'ordenes' ? 'activa' : ''} onClick={() => setTab('ordenes')}>Órdenes de hoy</button>
          <button className={tab === 'cancelaciones' ? 'activa' : ''} onClick={() => setTab('cancelaciones')}>Cancelaciones</button>
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
        {tab === 'menu' && <TabMenu onSesionVencida={() => setLogueado(false)} />}
        {tab === 'ordenes' && <TabOrdenes />}
        {tab === 'cancelaciones' && <TabCancelaciones onSesionVencida={() => setLogueado(false)} />}
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
    setPlatos((prev) => [...prev, { nombre: '', categoria: 'fondo', precio: '', activo_hoy: true }])
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
    </div>
  )
}

// ---------- Órdenes de hoy ----------

function TabOrdenes() {
  const [ordenes, setOrdenes] = useState<OrdenOut[]>([])
  const [totalVendido, setTotalVendido] = useState(0)
  const [ticket, setTicket] = useState<{ orden: OrdenOut; local: DatosLocal } | null>(null)

  useEffect(() => {
    const cargar = () =>
      api.ordenesHoy().then((data) => {
        setOrdenes(data.ordenes)
        setTotalVendido(data.total_vendido)
      }).catch(() => {})
    cargar()
    const intervalo = window.setInterval(cargar, 15_000)
    return () => window.clearInterval(intervalo)
  }, [])

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
      <div className="total-dia">Total vendido hoy: <strong>{soles(totalVendido)}</strong> ({ordenes.length} órdenes)</div>
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
              <td>{o.items.map((i) => `${i.cantidad}× ${i.nombre}`).join(', ')}</td>
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
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {error && <div className="banner-error">{error}</div>}
      <button className="boton-grande boton-primario" onClick={guardar}>💾 Guardar configuración</button>
    </div>
  )
}
