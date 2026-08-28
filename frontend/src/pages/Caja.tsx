import { useCallback, useEffect, useRef, useState } from 'react'
import { api, NOMBRE_CATEGORIA, soles } from '../api'
import type { ConfigOut, DatosLocal, OrdenOut, Plato } from '../api'
import { TarjetaPlato } from '../components/TarjetaPlato'
import { Ticket } from '../components/Ticket'
import { useCarrito } from '../hooks/useCarrito'

const SIGUIENTE_ESTADO: Record<string, string> = {
  pendiente: 'preparando',
  preparando: 'listo',
  listo: 'entregado',
}

/**
 * Vista de caja: el cajero registra pedidos de quienes no usan la
 * terminal (sin ventana de cancelación: el cajero confirma en persona)
 * y gestiona los pedidos del día — avanzar estado, reimprimir, anular.
 */
export function Caja() {
  const [platos, setPlatos] = useState<Plato[]>([])
  const [config, setConfig] = useState<ConfigOut | null>(null)
  const [ordenes, setOrdenes] = useState<OrdenOut[]>([])
  const [totalVendido, setTotalVendido] = useState(0)
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')
  const [registrando, setRegistrando] = useState(false)
  const [ticket, setTicket] = useState<{ orden: OrdenOut; local: DatosLocal } | null>(null)
  const carrito = useCarrito()
  const { sincronizarConMenu } = carrito

  const cargarMenu = useCallback(async () => {
    try {
      const data = await api.menuHoy()
      setPlatos(data.platos)
      sincronizarConMenu(data.platos)
    } catch {
      /* mantiene el último menú conocido */
    }
  }, [sincronizarConMenu])

  const cargarOrdenes = useCallback(async () => {
    try {
      const data = await api.ordenesHoy()
      setOrdenes(data.ordenes)
      setTotalVendido(data.total_vendido)
      setError('')
    } catch {
      setError('Sin conexión con el sistema')
    }
  }, [])

  useEffect(() => {
    api.config().then(setConfig).catch(() => {})
    cargarMenu()
    cargarOrdenes()
    const iMenu = window.setInterval(cargarMenu, 30_000)
    const iOrdenes = window.setInterval(cargarOrdenes, 10_000)
    return () => {
      window.clearInterval(iMenu)
      window.clearInterval(iOrdenes)
    }
  }, [cargarMenu, cargarOrdenes])

  // Impresión local (modo "terminal"): igual que en admin, el ticket se
  // monta oculto y se imprime cuando está en el DOM
  useEffect(() => {
    if (!ticket) return
    const timer = window.setTimeout(() => {
      window.print()
      setTicket(null)
    }, 150)
    return () => window.clearTimeout(timer)
  }, [ticket])

  const imprimeAqui = config?.modo_impresion !== 'estacion'

  const registrandoRef = useRef(false)
  const registrar = async () => {
    if (registrandoRef.current || carrito.totalItems === 0) return
    registrandoRef.current = true
    setRegistrando(true)
    setError('')
    setMensaje('')
    try {
      const resultado = await api.crearOrden(
        carrito.items.map((i) => ({ plato_id: i.plato.id, cantidad: i.cantidad })),
      )
      carrito.vaciar()
      cargarOrdenes()
      const numero = String(resultado.orden.numero_orden_dia).padStart(3, '0')
      if (imprimeAqui) {
        setTicket(resultado)
        setMensaje(`✔ ORDEN #${numero} registrada — imprimiendo ticket`)
      } else {
        setMensaje(`✔ ORDEN #${numero} registrada — el ticket sale por la ticketera`)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error de conexión, intenta de nuevo')
      cargarMenu() // por si el error fue un plato recién agotado
    } finally {
      registrandoRef.current = false
      setRegistrando(false)
    }
  }

  const avanzar = async (orden: OrdenOut) => {
    const siguiente = SIGUIENTE_ESTADO[orden.estado]
    if (!siguiente) return
    setOrdenes((prev) => prev.map((o) => (o.id === orden.id ? { ...o, estado: siguiente } : o)))
    try {
      await api.cambiarEstado(orden.id, siguiente)
    } catch {
      cargarOrdenes()
    }
  }

  const anular = async (orden: OrdenOut) => {
    const numero = String(orden.numero_orden_dia).padStart(3, '0')
    if (!window.confirm(`¿Anular la orden #${numero} (${soles(orden.total)})? No contará como venta.`)) return
    try {
      await api.cambiarEstado(orden.id, 'anulada')
      setMensaje(`Orden #${numero} anulada`)
      cargarOrdenes()
    } catch {
      setError('No se pudo anular, intenta de nuevo')
    }
  }

  const reimprimir = async (orden: OrdenOut) => {
    try {
      const cfg = config ?? (await api.config())
      if (cfg.modo_impresion === 'estacion') {
        await api.reimprimirOrden(orden.id)
        setMensaje(`Ticket #${String(orden.numero_orden_dia).padStart(3, '0')} enviado a la ticketera`)
      } else {
        setTicket({
          orden,
          local: { nombre: cfg.nombre_local, direccion: cfg.direccion, ruc: cfg.ruc },
        })
      }
    } catch {
      setError('No se pudo reimprimir')
    }
  }

  const categorias = ['entrada', 'fondo', 'bebida', 'postre'].filter((c) =>
    platos.some((p) => p.categoria === c),
  )
  // Para la caja lo útil es lo más reciente arriba
  const ordenesRecientes = [...ordenes].reverse()

  return (
    <div className="pantalla-caja">
      <header className="caja-cabecera">
        <h1>💵 Caja</h1>
        <span className="caja-total-dia">Vendido hoy: <strong>{soles(totalVendido)}</strong></span>
        {mensaje && <span className="banner-ok caja-banner">{mensaje}</span>}
        {error && <span className="banner-error caja-banner">{error}</span>}
      </header>

      <div className="caja-columnas">
        <section className="caja-nuevo">
          <h2>Nuevo pedido</h2>
          {platos.length === 0 && <p className="nota-admin">No hay menú cargado (Admin → Menú del día).</p>}
          {categorias.map((cat) => (
            <div key={cat}>
              <h3 className="titulo-categoria">{NOMBRE_CATEGORIA[cat] ?? cat}</h3>
              <div className="grilla-platos grilla-caja">
                {platos
                  .filter((p) => p.categoria === cat)
                  .map((p) => (
                    <TarjetaPlato
                      key={p.id}
                      plato={p}
                      cantidad={carrito.cantidadDe(p.id)}
                      onCambiar={(delta) => carrito.cambiarCantidad(p, delta)}
                    />
                  ))}
              </div>
            </div>
          ))}
          <div className="caja-acciones">
            <button
              className="boton-grande boton-secundario"
              disabled={carrito.totalItems === 0}
              onClick={() => carrito.vaciar()}
            >
              Limpiar
            </button>
            <button
              className="boton-grande boton-confirmar caja-registrar"
              disabled={carrito.totalItems === 0 || registrando}
              onClick={registrar}
            >
              {registrando
                ? 'Registrando…'
                : carrito.totalItems === 0
                  ? 'REGISTRAR PEDIDO'
                  : `✅ REGISTRAR — ${soles(carrito.totalSoles)}`}
            </button>
          </div>
        </section>

        <section className="caja-ordenes">
          <h2>Pedidos de hoy ({ordenes.length})</h2>
          <div className="caja-lista">
            {ordenesRecientes.map((o) => (
              <div key={o.id} className={`caja-orden ${o.estado === 'anulada' ? 'caja-orden-anulada' : ''}`}>
                <div className="caja-orden-info">
                  <span className="caja-orden-numero">#{String(o.numero_orden_dia).padStart(3, '0')}</span>
                  <span className={`etiqueta-estado etiqueta-${o.estado}`}>{o.estado}</span>
                  <span className="caja-orden-hora">{o.hora.slice(0, 5)}</span>
                  <span className="caja-orden-total">{soles(o.total)}</span>
                </div>
                <div className="caja-orden-items">
                  {o.items.map((i) => `${i.cantidad}× ${i.nombre}`).join(', ')}
                </div>
                <div className="caja-orden-botones">
                  {SIGUIENTE_ESTADO[o.estado] && (
                    <button onClick={() => avanzar(o)}>▶ {SIGUIENTE_ESTADO[o.estado]}</button>
                  )}
                  <button onClick={() => reimprimir(o)}>🖨️ Ticket</button>
                  {o.estado !== 'anulada' && o.estado !== 'entregado' && (
                    <button className="boton-anular" onClick={() => anular(o)}>✖ Anular</button>
                  )}
                </div>
              </div>
            ))}
            {ordenes.length === 0 && <p className="nota-admin">Todavía no hay pedidos hoy.</p>}
          </div>
        </section>
      </div>

      {ticket && (
        <div className="solo-impresion">
          <Ticket orden={ticket.orden} local={ticket.local} />
        </div>
      )}
    </div>
  )
}
