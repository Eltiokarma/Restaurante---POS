import { useCallback, useEffect, useRef, useState } from 'react'
import { api, EMPAQUES, NOMBRE_CATEGORIA, NOMBRE_EMPAQUE, NOMBRE_PAGO, NOMBRE_SERVICIO, soles, unidadesEnTaper } from '../api'
import type { CajaEstado, ConfigOut, DatosLocal, Entrega, ImpresionPendiente, MenuHoy, MesaEstado, MetodoPago, OrdenOut, Plato } from '../api'

const METODOS: MetodoPago[] = ['efectivo', 'tarjeta', 'yape']
import { ArmadoMenu } from '../components/ArmadoMenu'
import { TarjetaMenuCarrito } from '../components/TarjetaMenuCarrito'
import { AvisoImpresion } from '../components/AvisoImpresion'
import { SugerenciaMenu } from '../components/SugerenciaMenu'
import { IconoBillete, IconoSilla } from '../components/Iconos'
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
  const [menusHoy, setMenusHoy] = useState<MenuHoy[]>([])
  const [armandoMenu, setArmandoMenu] = useState<MenuHoy | null>(null)
  const [config, setConfig] = useState<ConfigOut | null>(null)

  const [ordenes, setOrdenes] = useState<OrdenOut[]>([])
  const [totalVendido, setTotalVendido] = useState(0)
  const [impresion, setImpresion] = useState<ImpresionPendiente | undefined>()
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')
  const [registrando, setRegistrando] = useState(false)
  const [ticket, setTicket] = useState<{ orden: OrdenOut; local: DatosLocal } | null>(null)
  const [estadoCaja, setEstadoCaja] = useState<CajaEstado | null>(null)
  const [montoCaja, setMontoCaja] = useState('')
  const [cerrandoCaja, setCerrandoCaja] = useState(false)
  const [corrigiendoFondo, setCorrigiendoFondo] = useState(false)
  const [montoFondo, setMontoFondo] = useState('')
  const [mesas, setMesas] = useState<MesaEstado[]>([])
  const [mesasNuevoPedido, setMesasNuevoPedido] = useState<number[]>([])
  // Orden a la que se le está eligiendo mesa (muestra los chips inline)
  const [asignandoMesa, setAsignandoMesa] = useState<number | null>(null)

  const cargarMesas = useCallback(async () => {
    try {
      setMesas((await api.mesas()).mesas)
    } catch {
      /* sin conexión: se mantiene lo último */
    }
  }, [])
  const carrito = useCarrito()
  const empaquesOfrecidos = config?.empaques_ofrecidos ?? EMPAQUES
  const precioTaper = config?.precio_taper ?? 0
  const cargoTaper = precioTaper * unidadesEnTaper(carrito.items, carrito.menus)
  const totalConCargos = carrito.totalSoles + cargoTaper
  const { sincronizarConMenu } = carrito

  const cargarCaja = useCallback(async () => {
    try {
      setEstadoCaja(await api.cajaHoy())
    } catch {
      /* el banner de conexión ya lo maneja cargarOrdenes */
    }
  }, [])

  const cargarMenu = useCallback(async () => {
    try {
      const data = await api.menuHoy()
      setPlatos(data.platos)
      setMenusHoy(data.menus)
      sincronizarConMenu(data.platos, data.menus)
    } catch {
      /* mantiene el último menú conocido */
    }
  }, [sincronizarConMenu])

  const cargarOrdenes = useCallback(async () => {
    try {
      const data = await api.ordenesHoy()
      setOrdenes(data.ordenes)
      setTotalVendido(data.total_vendido)
      setImpresion(data.impresion_pendiente)
      setError('')
    } catch {
      setError('Sin conexión con el sistema')
    }
  }, [])

  useEffect(() => {
    api.config().then(setConfig).catch(() => {})
    cargarMenu()
    cargarOrdenes()
    cargarCaja()
    cargarMesas()
    const iMenu = window.setInterval(cargarMenu, 30_000)
    const iOrdenes = window.setInterval(cargarOrdenes, 10_000)
    const iMesas = window.setInterval(cargarMesas, 10_000)
    return () => {
      window.clearInterval(iMenu)
      window.clearInterval(iOrdenes)
      window.clearInterval(iMesas)
    }
  }, [cargarMenu, cargarOrdenes, cargarCaja, cargarMesas])

  const liberarMesa = async (mesa: MesaEstado) => {
    const aviso =
      mesa.ordenes.length > 1
        ? `¿Liberar la ${mesa.nombre} COMPLETA? Se liberan TODOS sus tickets (#${mesa.ordenes.join(', #')}). ` +
          'Si solo se fue un grupo, usa "🪑 Se fue" en su ticket.'
        : `¿Liberar la ${mesa.nombre}? (ticket #${mesa.ordenes.join(', #')})`
    if (!window.confirm(aviso)) return
    try {
      await api.liberarMesa(mesa.id)
      setMensaje(`${mesa.nombre} liberada`)
      cargarMesas()
      cargarOrdenes()
    } catch {
      setError('No se pudo liberar la mesa')
    }
  }

  const corregirEntrega = async (orden: OrdenOut, entrega: Entrega) => {
    try {
      await api.corregirEntrega(orden.id, entrega)
      cargarOrdenes()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cambiar la entrega')
    }
  }

  const seFue = async (orden: OrdenOut) => {
    try {
      await api.liberarMesaDeTicket(orden.id)
      setMensaje(`Mesa del ticket #${String(orden.numero_orden_dia).padStart(3, '0')} liberada`)
      cargarOrdenes()
      cargarMesas()
    } catch {
      setError('No se pudo liberar la mesa del ticket')
    }
  }

  const asignarMesasAOrden = async (orden: OrdenOut, mesaIds: number[]) => {
    try {
      await api.asignarMesas(orden.id, mesaIds)
      setAsignandoMesa(null)
      cargarOrdenes()
      cargarMesas()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo asignar la mesa')
    }
  }

  const abrirCaja = async () => {
    const monto = parseFloat(montoCaja)
    if (!(monto >= 0)) {
      setError('Pon el fondo inicial de caja (puede ser 0)')
      return
    }
    try {
      setEstadoCaja(await api.abrirCaja(monto))
      setMontoCaja('')
      setMensaje(`✔ Caja abierta con ${soles(monto)} de fondo`)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo abrir la caja')
    }
  }

  const cerrarCaja = async () => {
    const monto = parseFloat(montoCaja)
    if (!(monto >= 0)) {
      setError('Pon cuánto efectivo contaste en caja')
      return
    }
    try {
      const resultado = await api.cerrarCaja(monto)
      setEstadoCaja(resultado)
      setMontoCaja('')
      setCerrandoCaja(false)
      const dif = resultado.diferencia ?? 0
      setMensaje(
        dif === 0
          ? '✔ Caja cerrada: cuadró exacto 🎯'
          : dif > 0
            ? `✔ Caja cerrada: sobran ${soles(dif)}`
            : `✔ Caja cerrada: faltan ${soles(-dif)}`,
      )
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cerrar la caja')
    }
  }

  const reabrirCaja = async () => {
    try {
      setEstadoCaja(await api.reabrirCaja())
      setCerrandoCaja(false)
      setMensaje('✔ Caja reabierta: el conteo se hace de nuevo al cierre de verdad')
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo reabrir la caja')
    }
  }

  const corregirFondo = async () => {
    const monto = parseFloat(montoFondo)
    if (!(monto >= 0)) {
      setError('Pon el fondo inicial correcto (puede ser 0)')
      return
    }
    try {
      setEstadoCaja(await api.corregirFondoCaja(monto))
      setMontoFondo('')
      setCorrigiendoFondo(false)
      setMensaje(`✔ Fondo inicial corregido a ${soles(monto)}`)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo corregir el fondo')
    }
  }

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

  const imprimeAqui = (config?.modo_impresion ?? 'terminal') === 'terminal'

  // Igual que en la terminal: un plato al momento (también dentro de un
  // menú) obliga a registrar con entrega separada; la caja puede corregirla
  const hayAlMomento =
    carrito.items.some((i) => i.plato.sale_al_momento) ||
    carrito.menus.some((m) =>
      m.menu.tiempos
        .flatMap((t) => t.alternativas)
        .some(
          (a) =>
            a.sale_al_momento &&
            (Object.values(m.elecciones).includes(a.plato_id) ||
              m.extras.some((e) => e.plato_id === a.plato_id)),
        ),
    )

  const registrandoRef = useRef(false)
  const registrar = async () => {
    if (registrandoRef.current || carrito.totalItems === 0) return
    registrandoRef.current = true
    setRegistrando(true)
    setError('')
    setMensaje('')
    try {
      const resultado = await api.crearOrden(
        carrito.items.map((i) => ({
          plato_id: i.plato.id, cantidad: i.cantidad, empaque: i.empaque, nota: i.nota.trim(),
        })),
        undefined,
        'tactil',
        mesasNuevoPedido,
        hayAlMomento ? 'separado' : 'junto',
        carrito.menus.map((m) => ({
          menu_id: m.menu.id, cantidad: m.cantidad, elecciones: m.elecciones,
          extras: m.extras, omitidos: m.omitidos, empaques: m.empaques,
          agregados: m.agregados.map((a) => ({ agregado_id: a.agregado.id, cantidad: a.cantidad })),
          empaque: m.empaque, nota: m.nota.trim(),
        })),
      )
      carrito.vaciar()
      setMesasNuevoPedido([])
      cargarOrdenes()
      cargarCaja()
      cargarMesas()
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
      cargarCaja()
    } catch {
      setError('No se pudo anular, intenta de nuevo')
    }
  }

  const cobrar = async (orden: OrdenOut, metodo: MetodoPago) => {
    setOrdenes((prev) =>
      prev.map((o) => (o.id === orden.id ? { ...o, metodo_pago: metodo } : o)),
    )
    try {
      await api.cobrarOrden(orden.id, metodo)
      cargarCaja()
    } catch {
      cargarOrdenes()
    }
  }

  const reimprimir = async (orden: OrdenOut) => {
    try {
      const cfg = config ?? (await api.config())
      if (cfg.modo_impresion !== 'terminal') {
        // Reencolar: lo imprime la ticketera o el puente, según el modo
        await api.reimprimirOrden(orden.id)
        setMensaje(`Ticket #${String(orden.numero_orden_dia).padStart(3, '0')} enviado a imprimir`)
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
        <h1><IconoBillete tam={30} /> Caja</h1>
        <span className="caja-total-dia">Vendido hoy: <strong>{soles(totalVendido)}</strong></span>
        {mensaje && <span className="banner-ok caja-banner">{mensaje}</span>}
        {error && <span className="banner-error caja-banner">{error}</span>}
      </header>

      <AvisoImpresion estado={impresion} />

      {estadoCaja && !estadoCaja.abierta && !estadoCaja.cerrada && (
        <div className="caja-panel caja-panel-apertura">
          <strong>La caja de hoy no está abierta.</strong>
          <label>
            Fondo inicial (sencillo para vueltos)
            <input
              type="number" step="0.50" min="0" placeholder="50.00"
              value={montoCaja} onChange={(e) => setMontoCaja(e.target.value)}
            />
          </label>
          <button className="boton-grande boton-confirmar" onClick={abrirCaja}>
            🔓 Abrir caja
          </button>
        </div>
      )}

      {estadoCaja?.abierta && (
        <div className="caja-panel">
          <span>
            🔓 Caja abierta a las {estadoCaja.hora_apertura?.slice(0, 5)} con{' '}
            <strong>{soles(estadoCaja.monto_apertura ?? 0)}</strong> de fondo · esperado en
            EFECTIVO: <strong>{soles((estadoCaja.monto_apertura ?? 0) + estadoCaja.ventas_efectivo)}</strong>
            {' '}· 💳 {soles(estadoCaja.ventas_tarjeta)} · 📱 {soles(estadoCaja.ventas_yape)}
            {estadoCaja.sin_registrar > 0 && (
              <em> · {estadoCaja.sin_registrar} sin registrar (se asumen efectivo)</em>
            )}
          </span>
          {!cerrandoCaja && !corrigiendoFondo && (
            <button className="boton-cerrar-caja" onClick={() => setCorrigiendoFondo(true)}>
              ✏️ Corregir fondo
            </button>
          )}
          {corrigiendoFondo && (
            <span className="caja-cierre-form">
              <label>
                Fondo inicial correcto
                <input
                  type="number" step="0.10" min="0" autoFocus
                  value={montoFondo} onChange={(e) => setMontoFondo(e.target.value)}
                />
              </label>
              <button className="boton-grande boton-confirmar" onClick={corregirFondo}>Guardar</button>
              <button className="boton-cerrar-caja" onClick={() => setCorrigiendoFondo(false)}>Cancelar</button>
            </span>
          )}
          {!cerrandoCaja && !corrigiendoFondo ? (
            <button className="boton-cerrar-caja" onClick={() => setCerrandoCaja(true)}>
              🔒 Cerrar caja
            </button>
          ) : cerrandoCaja ? (
            <span className="caja-cierre-form">
              <label>
                Efectivo contado
                <input
                  type="number" step="0.10" min="0" autoFocus
                  value={montoCaja} onChange={(e) => setMontoCaja(e.target.value)}
                />
              </label>
              <button className="boton-grande boton-confirmar" onClick={cerrarCaja}>Confirmar cierre</button>
              <button className="boton-cerrar-caja" onClick={() => setCerrandoCaja(false)}>Cancelar</button>
            </span>
          ) : null}
        </div>
      )}

      {estadoCaja?.cerrada && (
        <div className={`caja-panel ${estadoCaja.diferencia ? 'caja-panel-descuadre' : ''}`}>
          {/* El descuadre es LA cifra del cierre: grande y sin reconstruir signos */}
          {estadoCaja.descuadre && (
            <div className={`descuadre-grande descuadre-${estadoCaja.descuadre.tipo}`}>
              {estadoCaja.descuadre.tipo === 'exacta' ? (
                <>
                  <span className="descuadre-etiqueta">Cuadró</span>
                  <span className="descuadre-cifra">exacto 🎯</span>
                </>
              ) : (
                <>
                  <span className="descuadre-etiqueta">
                    {estadoCaja.descuadre.tipo === 'sobra' ? 'Sobran' : 'Faltan'}
                  </span>
                  <span className="descuadre-cifra">{soles(estadoCaja.descuadre.monto)}</span>
                </>
              )}
            </div>
          )}
          <span>
            🔒 Caja cerrada a las {estadoCaja.hora_cierre?.slice(0, 5)} — efectivo esperado:{' '}
            <strong>{soles((estadoCaja.monto_apertura ?? 0) + estadoCaja.ventas_efectivo)}</strong>{' '}
            · contado: <strong>{soles(estadoCaja.monto_contado ?? 0)}</strong>{' '}
            · 💳 {soles(estadoCaja.ventas_tarjeta)} · 📱 {soles(estadoCaja.ventas_yape)}
            {estadoCaja.ventas_despues_del_cierre && (
              <strong> · ⚠ hubo ventas o cambios después del cierre: corrige el conteo</strong>
            )}
          </span>
          {!cerrandoCaja && (
            <button className="boton-cerrar-caja" onClick={reabrirCaja}
                    title="Se cerró por error: deshace el cierre y el día sigue normal">
              🔓 Reabrir caja
            </button>
          )}
          {!cerrandoCaja ? (
            <button className="boton-cerrar-caja" onClick={() => setCerrandoCaja(true)}>
              Corregir conteo
            </button>
          ) : (
            <span className="caja-cierre-form">
              <label>
                Efectivo contado
                <input
                  type="number" step="0.10" min="0" autoFocus
                  value={montoCaja} onChange={(e) => setMontoCaja(e.target.value)}
                />
              </label>
              <button className="boton-grande boton-confirmar" onClick={cerrarCaja}>Guardar corrección</button>
              <button className="boton-cerrar-caja" onClick={() => setCerrandoCaja(false)}>Cancelar</button>
            </span>
          )}
        </div>
      )}

      {mesas.filter((m) => m.activa).length === 0 && (
        <div className="panel-mesas panel-mesas-vacio">
          🪑 Todavía no hay mesas configuradas. Créalas en <strong>Admin → Configuración →
          "Mesas del local"</strong> para poder asignarlas a los tickets.
        </div>
      )}
      {mesas.length > 0 && (
        <div className="panel-mesas">
          <span className="panel-mesas-titulo">Mesas:</span>
          {mesas.filter((m) => m.activa).map((m) => (
            <button
              key={m.id}
              className={`chip-mesa ${m.ocupada ? 'mesa-ocupada' : 'mesa-libre'}`}
              onClick={() => (m.ocupada ? liberarMesa(m) : undefined)}
              title={m.ocupada ? `Ocupada por #${m.ordenes.join(', #')} — toca para liberar` : 'Libre'}
            >
              🪑 {m.nombre}
              {m.ocupada && <span className="chip-mesa-tickets"> #{m.ordenes.join(' #')}</span>}
            </button>
          ))}
        </div>
      )}

      <div className="caja-columnas">
        <section className="caja-nuevo">
          <h2>Nuevo pedido</h2>
          {platos.length === 0 && menusHoy.length === 0 && (
            <p className="nota-admin">No hay menú cargado (Admin → Menú del día).</p>
          )}
          {menusHoy.length > 0 && (
            <div>
              <h3 className="titulo-categoria">Menús</h3>
              <div className="combo-lista">
                {menusHoy.map((m) => (
                  <div className="combo" key={m.id}>
                    <div className="combo-cabecera">
                      <span className="combo-titulo">{m.nombre}</span>
                      <span className="combo-precio">{soles(m.precio)}</span>
                    </div>
                    <button className="boton-armar" onClick={() => setArmandoMenu(m)}>
                      🍽 ARMAR MENÚ
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
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
          {(carrito.items.length > 0 || carrito.menus.length > 0) && (
            <div className="caja-carrito">
              <h3 className="titulo-categoria">Pedido en armado</h3>
              <SugerenciaMenu items={carrito.items} menus={menusHoy} onConvertir={carrito.convertirEnMenu} />
              {carrito.menus.map((m, idx) => (
                <TarjetaMenuCarrito
                  key={`menu-${idx}`}
                  linea={m}
                  numero={idx + 1}
                  onCambiarEleccion={(t, p) => carrito.cambiarEleccion(idx, t, p)}
                  onAlternarOmitido={(t) => carrito.alternarOmitido(idx, t)}
                  onCambiarAgregado={(a, d) => carrito.cambiarAgregado(idx, a, d)}
                  onCambiarExtra={(t, pl, d) => carrito.cambiarExtraMenu(idx, t, pl, d)}
                  onCambiarCantidad={(d) => carrito.cambiarCantidadMenu(idx, d)}
                  onDuplicar={() => carrito.duplicarMenu(idx)}
                  onCambiarEmpaque={(e) => carrito.cambiarEmpaqueMenu(idx, e)}
                  onCambiarEmpaqueTiempo={(t, e) => carrito.cambiarEmpaqueTiempo(idx, t, e)}
                  onCambiarNota={(n) => carrito.cambiarNotaMenu(idx, n)}
                  empaquesOfrecidos={empaquesOfrecidos}
                  precioTaper={precioTaper}
                />
              ))}
              {carrito.items.map((i) => (
                <div className="caja-carrito-item" key={i.plato.id}>
                  <span className="caja-carrito-nombre">
                    {i.cantidad} × {i.plato.nombre}
                  </span>
                  <input
                    className="input-nota-plato input-nota-caja"
                    placeholder="📝 sin frijoles, con huevo frito…"
                    maxLength={150}
                    value={i.nota}
                    onChange={(e) => carrito.cambiarNota(i.plato.id, e.target.value)}
                  />
                  <div className="empaques-linea">
                    {empaquesOfrecidos.map((e) => (
                      <button
                        key={e}
                        className={`boton-servicio boton-empaque boton-empaque-caja ${i.empaque === e ? 'servicio-activo' : ''}`}
                        onClick={() => carrito.cambiarEmpaque(i.plato.id, e)}
                      >
                        {NOMBRE_EMPAQUE[e]}
                        {e === 'taper' && precioTaper > 0 && <small> +{soles(precioTaper)}</small>}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          {mesas.some((m) => m.activa) && carrito.totalItems > 0 && (
            <div className="caja-mesas-nuevo">
              <span className="cobro-etiqueta">Mesa (elige varias para combinar):</span>
              <div className="empaques-linea">
                {mesas.filter((m) => m.activa).map((m) => (
                  <button
                    key={m.id}
                    className={`boton-servicio boton-empaque boton-empaque-caja ${mesasNuevoPedido.includes(m.id) ? 'servicio-activo' : ''} ${m.ocupada && !mesasNuevoPedido.includes(m.id) ? 'mesa-chip-ocupada' : ''}`}
                    onClick={() =>
                      setMesasNuevoPedido((prev) =>
                        prev.includes(m.id) ? prev.filter((x) => x !== m.id) : [...prev, m.id],
                      )
                    }
                  >
                    {m.nombre}{m.ocupada ? ' •' : ''}
                  </button>
                ))}
              </div>
            </div>
          )}
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
                  : `✅ REGISTRAR — ${soles(totalConCargos)}`}
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
                  {o.tipo_servicio !== 'sala' && (
                    <span className="badge-servicio">{NOMBRE_SERVICIO[o.tipo_servicio]}</span>
                  )}
                  {o.mesas.length > 0 && !o.mesa_liberada && (
                    <span className="badge-mesa"><IconoSilla tam={15} /> {o.mesas.join(' + ')}</span>
                  )}
                  <span className="caja-orden-hora">{o.hora.slice(0, 5)}</span>
                  <span className="caja-orden-total">{soles(o.total)}</span>
                </div>
                <div className="caja-orden-items">
                  {o.menus.length > 0 && (
                    <span>
                      {o.menus
                        .map(
                          (m) =>
                            `${m.cantidad}× ${m.nombre} (${[
                              ...m.omitidos.map((x) => `SIN ${x.rotulo.toLowerCase()}`),
                              ...m.items.map((i) =>
                                i.es_agregado
                                  ? `+${i.cantidad} ${i.nombre}`
                                  : i.es_extra
                                    ? `+${i.cantidad} ${i.nombre} extra`
                                    : i.nombre,
                              ),
                            ].join(' + ')})`,
                        )
                        .join(', ')}
                      {o.items.length > 0 && ', '}
                    </span>
                  )}
                  {o.items.map((i, idx) => (
                    <span key={idx}>
                      {idx > 0 && ', '}
                      {i.cantidad}× {i.nombre}
                      {i.nota && <em className="nota-item"> ({i.nota})</em>}
                    </span>
                  ))}
                </div>
                {o.estado !== 'anulada' && (o.items.length + o.menus.length >= 2 || o.menus.length > 0) && (
                  <div className="caja-orden-cobro">
                    <span className="cobro-etiqueta">Sale:</span>
                    {(['junto', 'separado'] as Entrega[]).map((e) => (
                      <button
                        key={e}
                        className={`boton-cobro ${o.entrega === e ? 'cobro-activo' : ''}`}
                        onClick={() => corregirEntrega(o, e)}
                      >
                        {e === 'junto' ? '🍽 Junto' : '⏱ Por tiempos'}
                      </button>
                    ))}
                  </div>
                )}
                {o.estado !== 'anulada' && (
                  <div className="caja-orden-cobro">
                    {o.metodo_pago === null && <span className="cobro-etiqueta">Cobrar:</span>}
                    {METODOS.map((m) => (
                      <button
                        key={m}
                        className={`boton-cobro ${o.metodo_pago === m ? 'cobro-activo' : ''}`}
                        onClick={() => cobrar(o, m)}
                      >
                        {NOMBRE_PAGO[m]}
                      </button>
                    ))}
                  </div>
                )}
                <div className="caja-orden-botones">
                  {SIGUIENTE_ESTADO[o.estado] && (
                    <button onClick={() => avanzar(o)}>▶ {SIGUIENTE_ESTADO[o.estado]}</button>
                  )}
                  <button onClick={() => reimprimir(o)}>🖨️ Ticket</button>
                  {o.estado !== 'anulada' && (
                    <button onClick={() => setAsignandoMesa(asignandoMesa === o.id ? null : o.id)}>
                      🪑 Mesa
                    </button>
                  )}
                  {o.estado !== 'anulada' && o.mesas.length > 0 && !o.mesa_liberada && (
                    <button onClick={() => seFue(o)} title="Libera solo la mesa de este ticket">
                      🪑✔ Se fue
                    </button>
                  )}
                  {o.estado !== 'anulada' && o.estado !== 'entregado' && (
                    <button className="boton-anular" onClick={() => anular(o)}>✖ Anular</button>
                  )}
                </div>
                {asignandoMesa === o.id && mesas.filter((m) => m.activa).length === 0 && (
                  <p className="nota-admin">
                    No hay mesas creadas todavía: ve a Admin → Configuración → "Mesas del local".
                  </p>
                )}
                {asignandoMesa === o.id && (
                  <div className="empaques-linea">
                    {mesas.filter((m) => m.activa).map((m) => (
                      <button
                        key={m.id}
                        className={`boton-servicio boton-empaque boton-empaque-caja ${o.mesa_ids.includes(m.id) && !o.mesa_liberada ? 'servicio-activo' : ''}`}
                        onClick={() => {
                          const actuales = o.mesa_liberada ? [] : o.mesa_ids
                          const nuevas = actuales.includes(m.id)
                            ? actuales.filter((x) => x !== m.id)
                            : [...actuales, m.id]
                          asignarMesasAOrden(o, nuevas)
                        }}
                      >
                        {m.nombre}{m.ocupada && !o.mesa_ids.includes(m.id) ? ' •' : ''}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {ordenes.length === 0 && <p className="nota-admin">Todavía no hay pedidos hoy.</p>}
          </div>
        </section>
      </div>

      {armandoMenu && (
        <ArmadoMenu
          menu={armandoMenu}
          onAgregar={(linea) => {
            carrito.agregarMenu(linea)
            setArmandoMenu(null)
          }}
          onCerrar={() => setArmandoMenu(null)}
        />
      )}

      {ticket && (
        <div className="solo-impresion">
          <Ticket orden={ticket.orden} local={ticket.local} />
        </div>
      )}
    </div>
  )
}
