import { useCallback, useEffect, useRef, useState } from 'react'
import { api, esperadoEnCaja, EMPAQUES, NOMBRE_CATEGORIA, NOMBRE_EMPAQUE, NOMBRE_PAGO, NOMBRE_SERVICIO, soles, unidadesEnTaper } from '../api'
import type { CajaEstado, ConfigOut, DatosLocal, EgresoOut, Entrega, ImpresionPendiente, MenuHoy, MesaEstado, MetodoPago, OrdenOut, Plato } from '../api'

const METODOS: MetodoPago[] = ['efectivo', 'tarjeta', 'yape']
import { TarjetaMenuCarrito } from '../components/TarjetaMenuCarrito'
import { menusEnPedido, TarjetaOfertaMenu } from '../components/TarjetaOfertaMenu'
import { AvisoImpresion } from '../components/AvisoImpresion'
import { SugerenciaMenu } from '../components/SugerenciaMenu'
import { IconoBillete, IconoSilla } from '../components/Iconos'
import { TarjetaPlato } from '../components/TarjetaPlato'
import { Ticket, TicketCierre } from '../components/Ticket'
import {
  IconoAspa, IconoCandadoAbierto, IconoCandadoCerrado, IconoEgreso,
  IconoImpresora, IconoLapiz,
} from '../components/Iconos'
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
  const [config, setConfig] = useState<ConfigOut | null>(null)

  const [ordenes, setOrdenes] = useState<OrdenOut[]>([])
  const [totalVendido, setTotalVendido] = useState(0)
  const [impresion, setImpresion] = useState<ImpresionPendiente | undefined>()
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')
  // La conexión es un ESTADO (cintillo persistente), no un mensaje más
  const [sinConexion, setSinConexion] = useState(false)
  const [registrando, setRegistrando] = useState(false)
  const [ticket, setTicket] = useState<{ orden: OrdenOut; local: DatosLocal } | null>(null)
  const [estadoCaja, setEstadoCaja] = useState<CajaEstado | null>(null)
  const [montoCaja, setMontoCaja] = useState('')
  const [cerrandoCaja, setCerrandoCaja] = useState(false)
  // Doble check del cierre: primero se escribe el conteo, luego se confirma
  const [confirmandoCierre, setConfirmandoCierre] = useState(false)
  const [abriendoNueva, setAbriendoNueva] = useState(false)
  const [corrigiendoFondo, setCorrigiendoFondo] = useState(false)
  const [montoFondo, setMontoFondo] = useState('')
  // Egresos del turno ("salió plata del cajón")
  const [egresos, setEgresos] = useState<EgresoOut[]>([])
  const [agregandoEgreso, setAgregandoEgreso] = useState(false)
  const [conceptoEgreso, setConceptoEgreso] = useState('')
  const [montoEgreso, setMontoEgreso] = useState('')
  // Resumen de cierre que se imprime desde esta pantalla (modo no-puente)
  const [ticketCierre, setTicketCierre] = useState<{
    estado: CajaEstado; egresos: EgresoOut[]; local: DatosLocal
  } | null>(null)
  const [mesas, setMesas] = useState<MesaEstado[]>([])
  const [mesasNuevoPedido, setMesasNuevoPedido] = useState<number[]>([])
  // Orden a la que se le está eligiendo mesa (muestra los chips inline)
  const [asignandoMesa, setAsignandoMesa] = useState<number | null>(null)
  // Orden con el menú "⋯" desplegado (acciones secundarias)
  const [menuAbierto, setMenuAbierto] = useState<number | null>(null)
  // Orden a la que se le está registrando el vuelto ("¿pagó con cuánto?")
  const [vueltoAbierto, setVueltoAbierto] = useState<number | null>(null)
  const [pagoConTexto, setPagoConTexto] = useState('')

  // El "⋯" cierra con Escape y con un toque fuera
  useEffect(() => {
    if (menuAbierto === null) return
    const alTocarFuera = (ev: MouseEvent) => {
      if (!(ev.target as HTMLElement).closest('.menu-mas')) setMenuAbierto(null)
    }
    const alTeclear = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setMenuAbierto(null)
    }
    document.addEventListener('click', alTocarFuera)
    document.addEventListener('keydown', alTeclear)
    return () => {
      document.removeEventListener('click', alTocarFuera)
      document.removeEventListener('keydown', alTeclear)
    }
  }, [menuAbierto])

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
      setEgresos((await api.egresosTurno()).egresos)
    } catch {
      /* el banner de conexión ya lo maneja cargarOrdenes */
    }
  }, [])
  const totalEgresos = egresos.reduce((s, e) => s + e.monto, 0)

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
      setSinConexion(false)
    } catch {
      setSinConexion(true)
    }
  }, [])

  // El aviso de éxito se limpia solo; el de error espera una acción
  useEffect(() => {
    if (!mensaje) return
    const timer = window.setTimeout(() => setMensaje(''), 6_000)
    return () => window.clearTimeout(timer)
  }, [mensaje])

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
      if (mesaIds.length > 0) {
        // El ticket ya impreso no dice la mesa: se reimprime con ella
        // (pedido del dueño; el mozo sabe adónde llevarlo)
        const nombres = mesas.filter((m) => mesaIds.includes(m.id)).map((m) => m.nombre)
        await reimprimir({ ...orden, mesa_ids: mesaIds, mesas: nombres, mesa_liberada: false })
        setMensaje(
          `Ticket #${String(orden.numero_orden_dia).padStart(3, '0')} va de nuevo a imprimir con su mesa`,
        )
      }
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
      const resultado = await api.abrirCaja(monto)
      setEstadoCaja(resultado)
      setMontoCaja('')
      setAbriendoNueva(false)
      const n = resultado.turno ?? 1
      setMensaje(
        n > 1
          ? `Caja ${n} del día abierta con ${soles(monto)} de fondo`
          : `Caja abierta con ${soles(monto)} de fondo`,
      )
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo abrir la caja')
    }
  }

  // Paso 1 del cierre: valida el conteo y pide el doble check
  const revisarCierre = () => {
    const monto = parseFloat(montoCaja)
    if (!(monto >= 0)) {
      setError('Pon cuánto efectivo contaste en caja')
      return
    }
    setError('')
    setConfirmandoCierre(true)
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
      setConfirmandoCierre(false)
      const dif = resultado.diferencia ?? 0
      setMensaje(
        dif === 0
          ? 'Caja cerrada: cuadró exacto — imprimiendo el resumen'
          : dif > 0
            ? `Caja cerrada: sobran ${soles(dif)} — imprimiendo el resumen`
            : `Caja cerrada: faltan ${soles(-dif)} — imprimiendo el resumen`,
      )
      setError('')
      // El resumen impreso del cierre: en modo puente lo saca la
      // ticketera (lo encola el backend); si no, se imprime aquí mismo
      const cfg = config ?? (await api.config())
      if (cfg.modo_impresion !== 'puente') {
        setTicketCierre({
          estado: resultado,
          egresos,
          local: { nombre: cfg.nombre_local, direccion: cfg.direccion, ruc: cfg.ruc },
        })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cerrar la caja')
    }
  }

  const registrarEgreso = async () => {
    const monto = parseFloat(montoEgreso)
    if (!conceptoEgreso.trim() || !(monto > 0)) {
      setError('Pon en qué se gastó y cuánto salió del cajón')
      return
    }
    try {
      const datos = await api.registrarEgreso(conceptoEgreso.trim(), monto)
      setEgresos(datos.egresos)
      setConceptoEgreso('')
      setMontoEgreso('')
      setAgregandoEgreso(false)
      setMensaje(`Egreso registrado: −${soles(monto)}`)
      setError('')
      cargarCaja()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo registrar el egreso')
    }
  }

  const borrarEgreso = async (egreso: EgresoOut) => {
    if (!window.confirm(`¿Borrar el egreso "${egreso.concepto}" (−${soles(egreso.monto)})?`)) return
    try {
      const datos = await api.borrarEgreso(egreso.id)
      setEgresos(datos.egresos)
      cargarCaja()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo borrar el egreso')
    }
  }

  const reabrirCaja = async () => {
    try {
      setEstadoCaja(await api.reabrirCaja())
      setCerrandoCaja(false)
      setMensaje('Caja reabierta: el conteo se hace de nuevo al cierre de verdad')
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
      setMensaje(`Fondo inicial corregido a ${soles(monto)}`)
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

  // El resumen de cierre se imprime igual: montado oculto y print
  useEffect(() => {
    if (!ticketCierre) return
    const timer = window.setTimeout(() => {
      window.print()
      setTicketCierre(null)
    }, 150)
    return () => window.clearTimeout(timer)
  }, [ticketCierre])

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
        setMensaje(`ORDEN #${numero} registrada — imprimiendo ticket`)
      } else {
        setMensaje(`ORDEN #${numero} registrada — el ticket sale por la ticketera`)
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
    // Pagó: el método queda registrado y el "falta pagar" se levanta solo
    setOrdenes((prev) =>
      prev.map((o) =>
        o.id === orden.id ? { ...o, metodo_pago: metodo, pago_pendiente: false } : o,
      ),
    )
    try {
      await api.cobrarOrden(orden.id, metodo)
      cargarCaja()
    } catch {
      cargarOrdenes()
    }
  }

  // "Falta pagar": el ticket salió pero la plata no entró — mientras esté
  // marcado, el cierre no espera ese efectivo
  const alternarFaltaPagar = async (orden: OrdenOut) => {
    try {
      await api.marcarPagoPendiente(orden.id, !orden.pago_pendiente)
      setMensaje(
        orden.pago_pendiente
          ? `Ticket #${String(orden.numero_orden_dia).padStart(3, '0')}: se levantó el "falta pagar"`
          : `Ticket #${String(orden.numero_orden_dia).padStart(3, '0')} marcado FALTA PAGAR`,
      )
      setError('')
      cargarOrdenes()
      cargarCaja()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo marcar el ticket')
    }
  }

  // "Falta vuelto": pagó con billete grande; se registra con cuánto pagó
  // y el sistema calcula el vuelto que se le debe
  const guardarVuelto = async (orden: OrdenOut) => {
    const monto = parseFloat(pagoConTexto)
    if (!(monto > 0)) {
      setError('Pon con cuánto pagó el cliente')
      return
    }
    try {
      const r = await api.registrarVuelto(orden.id, monto)
      setVueltoAbierto(null)
      setPagoConTexto('')
      setMensaje(
        r.vuelto_pendiente
          ? `Ticket #${String(orden.numero_orden_dia).padStart(3, '0')}: FALTA VUELTO ${soles(r.vuelto_pendiente)}`
          : 'Pagó exacto: no queda vuelto pendiente',
      )
      setError('')
      cargarOrdenes()
      cargarCaja()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo registrar el vuelto')
    }
  }

  const vueltoEntregado = async (orden: OrdenOut) => {
    try {
      await api.registrarVuelto(orden.id, null)
      setMensaje(`Vuelto del ticket #${String(orden.numero_orden_dia).padStart(3, '0')} entregado`)
      setError('')
      cargarOrdenes()
      cargarCaja()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo registrar el vuelto')
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

  // Con "solo menús" encendido, la caja tampoco muestra los platos
  // sueltos (pedido del dueño): todo se vende como menú armado. Si hoy
  // no hay menú activo, la carta reaparece como respaldo.
  const soloMenus = (config?.terminal_solo_menus ?? true) && menusHoy.length > 0
  const categorias = soloMenus
    ? []
    : ['entrada', 'fondo', 'bebida', 'postre'].filter((c) =>
        platos.some((p) => p.categoria === c),
      )
  // Para la caja lo útil es lo más reciente arriba
  const ordenesRecientes = [...ordenes].reverse()

  return (
    <div className="pantalla-caja">
      <header className="caja-cabecera">
        <h1><IconoBillete tam={30} /> Caja</h1>
        <span className="caja-total-dia">Vendido hoy: <strong>{soles(totalVendido)}</strong></span>
      </header>

      {sinConexion && (
        <div className="cintillo-sin-conexion">Sin conexión con el sistema · reintentando…</div>
      )}
      {/* Franja con alto reservado: que aparezca un aviso no empuja lo
          que el cajero está tocando. Un solo aviso a la vez. */}
      <div className="franja-avisos" aria-live="polite">
        {error ? (
          <div className="banner-error">{error}</div>
        ) : mensaje ? (
          <div className="banner-ok">{mensaje}</div>
        ) : null}
      </div>

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
            <IconoCandadoAbierto tam={22} /> Abrir caja
          </button>
        </div>
      )}

      {estadoCaja?.abierta && (
        <div className="caja-panel caja-panel-tablero">
          {/* Tablero de cifras, no una frase: la que decide el cierre
              (esperado en efectivo) manda; el resto acompaña */}
          <div className="caja-panel-contexto">
            <span className="caja-panel-estado">
              <IconoCandadoAbierto tam={16} />
              {(estadoCaja.turno ?? 1) > 1
                ? `Caja ${estadoCaja.turno} abierta`
                : 'Caja abierta'} · {estadoCaja.hora_apertura?.slice(0, 5)}
            </span>
            <span className="caja-panel-dato">fondo {soles(estadoCaja.monto_apertura ?? 0)}</span>
            {estadoCaja.sin_registrar > 0 && (
              <span className="chip-aviso">
                {estadoCaja.sin_registrar} sin registrar → efectivo
              </span>
            )}
          </div>
          <div className="caja-cifra-principal">
            <span className="cifra-etiqueta">Esperado en efectivo</span>
            <span className="cifra-valor">{soles(esperadoEnCaja(estadoCaja))}</span>
          </div>
          <div className="caja-cifras-grid">
            <div className="caja-cifra">
              <span className="cifra-etiqueta">Egresos</span>
              <span className="cifra-chica cifra-egreso">−{soles(estadoCaja.egresos ?? 0)}</span>
            </div>
            <div className="caja-cifra">
              <span className="cifra-etiqueta">Tarjeta</span>
              <span className="cifra-chica">{soles(estadoCaja.ventas_tarjeta)}</span>
            </div>
            <div className="caja-cifra">
              <span className="cifra-etiqueta">Yape</span>
              <span className="cifra-chica">{soles(estadoCaja.ventas_yape)}</span>
            </div>
            {(estadoCaja.por_cobrar ?? 0) > 0 && (
              <div className="caja-cifra">
                <span className="cifra-etiqueta">Falta pagar</span>
                <span className="cifra-chica cifra-egreso">−{soles(estadoCaja.por_cobrar ?? 0)}</span>
              </div>
            )}
            {(estadoCaja.vueltos_pendientes ?? 0) > 0 && (
              <div className="caja-cifra">
                <span className="cifra-etiqueta">Vueltos por dar</span>
                <span className="cifra-chica cifra-vuelto">+{soles(estadoCaja.vueltos_pendientes ?? 0)}</span>
              </div>
            )}
          </div>
          <div className="caja-panel-acciones">
            {!cerrandoCaja && !corrigiendoFondo && (
              <>
                <button className="boton boton--md boton--culantro" onClick={() => setCerrandoCaja(true)}>
                  <IconoCandadoCerrado tam={20} /> Cerrar caja
                </button>
                <button className="boton boton--md boton--papel" onClick={() => setCorrigiendoFondo(true)}>
                  <IconoLapiz tam={20} /> Corregir fondo
                </button>
              </>
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
                <button className="boton boton--md boton--papel" onClick={() => setCorrigiendoFondo(false)}>Cancelar</button>
              </span>
            )}
            {cerrandoCaja && !confirmandoCierre && (
              <span className="caja-cierre-form">
                <label>
                  Efectivo contado
                  <input
                    type="number" step="0.10" min="0" autoFocus
                    value={montoCaja} onChange={(e) => setMontoCaja(e.target.value)}
                  />
                </label>
                <button className="boton-grande boton-confirmar" onClick={revisarCierre}>Confirmar cierre</button>
                <button className="boton boton--md boton--papel" onClick={() => setCerrandoCaja(false)}>Cancelar</button>
              </span>
            )}
          </div>
        </div>
      )}

      {/* Doble check del cierre: el MISMO resumen que va a salir impreso,
          en pantalla, para revisarlo antes de cerrar */}
      {confirmandoCierre && estadoCaja && (
        <div className="modal-fondo">
          <div className="modal modal-cierre">
            <h2>Revisa antes de cerrar</h2>
            <div className="vista-previa-cierre">
              <TicketCierre
                estado={{
                  ...estadoCaja,
                  cerrada: true,
                  hora_cierre: null,
                  monto_contado: parseFloat(montoCaja) || 0,
                  diferencia:
                    Math.round(((parseFloat(montoCaja) || 0) - esperadoEnCaja(estadoCaja)) * 100) / 100,
                }}
                egresos={egresos}
                local={{
                  nombre: config?.nombre_local ?? 'Restaurante',
                  direccion: config?.direccion ?? '',
                  ruc: config?.ruc ?? '',
                }}
              />
            </div>
            <p className="nota-admin">
              Si algo no cuadra, vuelve y corrige el conteo. Después de cerrar también
              puedes reabrir la caja o abrir una nueva.
            </p>
            {/* El banner del header queda tapado por el modal: el error va aquí */}
            {error && <div className="banner-error">{error}</div>}
            <div className="modal-botones">
              <button className="boton-grande boton-secundario" onClick={() => setConfirmandoCierre(false)}>
                ↩ Volver
              </button>
              <button className="boton-grande boton-confirmar" onClick={cerrarCaja}>
                ✅ SÍ, CERRAR CAJA
              </button>
            </div>
          </div>
        </div>
      )}

      {estadoCaja?.cerrada && (
        <div className={`caja-panel caja-panel-tablero ${estadoCaja.diferencia ? 'caja-panel-descuadre' : ''}`}>
          <div className="caja-panel-contexto">
            <span className="caja-panel-estado caja-panel-estado-neutro">
              <IconoCandadoCerrado tam={16} />
              {(estadoCaja.turno ?? 1) > 1
                ? `Caja ${estadoCaja.turno} cerrada`
                : 'Caja cerrada'} · {estadoCaja.hora_cierre?.slice(0, 5)}
            </span>
            <span className="caja-panel-dato">fondo {soles(estadoCaja.monto_apertura ?? 0)}</span>
            {estadoCaja.ventas_despues_del_cierre && (
              <span className="chip-aviso">ventas tras el cierre — corrige el conteo</span>
            )}
          </div>
          {/* El descuadre es LA cifra del cierre: grande y sin reconstruir signos */}
          {estadoCaja.descuadre && (
            <div className={`descuadre-grande descuadre-${estadoCaja.descuadre.tipo}`}>
              {estadoCaja.descuadre.tipo === 'exacta' ? (
                <>
                  <span className="descuadre-etiqueta">Cuadró</span>
                  <span className="descuadre-cifra">exacto</span>
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
          <div className="caja-cifras-grid">
            <div className="caja-cifra">
              <span className="cifra-etiqueta">Esperado</span>
              <span className="cifra-chica">{soles(esperadoEnCaja(estadoCaja))}</span>
            </div>
            <div className="caja-cifra">
              <span className="cifra-etiqueta">Contado</span>
              <span className="cifra-chica">{soles(estadoCaja.monto_contado ?? 0)}</span>
            </div>
            <div className="caja-cifra">
              <span className="cifra-etiqueta">Egresos</span>
              <span className="cifra-chica cifra-egreso">−{soles(estadoCaja.egresos ?? 0)}</span>
            </div>
            <div className="caja-cifra">
              <span className="cifra-etiqueta">Tarjeta</span>
              <span className="cifra-chica">{soles(estadoCaja.ventas_tarjeta)}</span>
            </div>
            <div className="caja-cifra">
              <span className="cifra-etiqueta">Yape</span>
              <span className="cifra-chica">{soles(estadoCaja.ventas_yape)}</span>
            </div>
            {(estadoCaja.por_cobrar ?? 0) > 0 && (
              <div className="caja-cifra">
                <span className="cifra-etiqueta">Falta pagar</span>
                <span className="cifra-chica cifra-egreso">−{soles(estadoCaja.por_cobrar ?? 0)}</span>
              </div>
            )}
            {(estadoCaja.vueltos_pendientes ?? 0) > 0 && (
              <div className="caja-cifra">
                <span className="cifra-etiqueta">Vueltos por dar</span>
                <span className="cifra-chica cifra-vuelto">+{soles(estadoCaja.vueltos_pendientes ?? 0)}</span>
              </div>
            )}
          </div>
          <div className="caja-panel-acciones">
            {!cerrandoCaja && !abriendoNueva && (
              <>
                <button className="boton boton--md boton--culantro" onClick={() => setCerrandoCaja(true)}>
                  <IconoLapiz tam={20} /> Corregir conteo
                </button>
                <button className="boton boton--md boton--papel" onClick={reabrirCaja}
                        title="Se cerró por error: deshace el cierre y el día sigue normal">
                  <IconoCandadoAbierto tam={20} /> Reabrir caja
                </button>
                <button className="boton boton--md boton--papel" onClick={() => setAbriendoNueva(true)}
                        title="Empieza otra caja hoy mismo: la cerrada queda cuadrada tal cual">
                  Abrir caja nueva
                </button>
              </>
            )}
            {cerrandoCaja && (
              <span className="caja-cierre-form">
                <label>
                  Efectivo contado
                  <input
                    type="number" step="0.10" min="0" autoFocus
                    value={montoCaja} onChange={(e) => setMontoCaja(e.target.value)}
                  />
                </label>
                <button className="boton-grande boton-confirmar" onClick={cerrarCaja}>Guardar corrección</button>
                <button className="boton boton--md boton--papel" onClick={() => setCerrandoCaja(false)}>Cancelar</button>
              </span>
            )}
            {abriendoNueva && (
              <span className="caja-cierre-form">
                <label>
                  Fondo inicial de la caja nueva
                  <input
                    type="number" step="0.50" min="0" autoFocus placeholder="50.00"
                    value={montoCaja} onChange={(e) => setMontoCaja(e.target.value)}
                  />
                </label>
                <button className="boton-grande boton-confirmar" onClick={abrirCaja}>
                  <IconoCandadoAbierto tam={20} /> Abrir caja nueva
                </button>
                <button className="boton boton--md boton--papel" onClick={() => setAbriendoNueva(false)}>Cancelar</button>
              </span>
            )}
          </div>
        </div>
      )}

      {estadoCaja && (estadoCaja.abierta || (estadoCaja.cerrada && egresos.length > 0)) && (
        <div className="caja-panel caja-egresos">
          <div className="caja-egresos-cabecera">
            <span className="caja-panel-estado caja-panel-estado-neutro">
              <IconoEgreso tam={16} /> Egresos del turno
            </span>
            {egresos.length > 0 ? (
              <span className="fila-egreso-monto">−{soles(totalEgresos)}</span>
            ) : (
              <span className="caja-panel-dato">salió plata del cajón: gas, verduras…</span>
            )}
            {estadoCaja.abierta && !agregandoEgreso && (
              <button className="boton boton--md boton--papel" onClick={() => setAgregandoEgreso(true)}>
                + Registrar egreso
              </button>
            )}
          </div>
          {/* Filas, no chips: los egresos se auditan de un barrido al cierre */}
          {egresos.map((e) => (
            <div className="fila-egreso" key={e.id}>
              <span className="fila-egreso-hora">{e.hora.slice(0, 5)}</span>
              <span className="fila-egreso-concepto">{e.concepto}</span>
              <span className="fila-egreso-monto">−{soles(e.monto)}</span>
              {estadoCaja.abierta && (
                <button
                  className="boton boton--peligro boton-aspa"
                  onClick={() => borrarEgreso(e)}
                  title="Borrar egreso" aria-label={`Borrar egreso ${e.concepto}`}
                >
                  <IconoAspa tam={20} />
                </button>
              )}
            </div>
          ))}
          {agregandoEgreso && (
            <span className="caja-cierre-form">
              <label>
                ¿En qué se gastó?
                <input
                  autoFocus placeholder="balón de gas" maxLength={120}
                  value={conceptoEgreso} onChange={(e) => setConceptoEgreso(e.target.value)}
                />
              </label>
              <label>
                S/
                <input
                  type="number" step="0.10" min="0" placeholder="20.00"
                  value={montoEgreso} onChange={(e) => setMontoEgreso(e.target.value)}
                />
              </label>
              <button className="boton-grande boton-confirmar" onClick={registrarEgreso}>Guardar</button>
              <button className="boton boton--md boton--papel" onClick={() => setAgregandoEgreso(false)}>Cancelar</button>
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
              <IconoSilla tam={18} /> {m.nombre}
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
                {/* Igual que la terminal: un toque agrega el menú completo
                    y abajo cada tarjeta se edita a su gusto */}
                {menusHoy.map((m) => (
                  <TarjetaOfertaMenu
                    key={m.id}
                    menu={m}
                    etiqueta={`➕ UN MENÚ — ${soles(m.precio)}`}
                    enPedido={menusEnPedido(carrito.menus, m.id)}
                    onAgregar={() => carrito.agregarMenuCompleto(m)}
                  />
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
              <div key={o.id} className={`caja-orden estado-${o.estado} ${o.estado === 'anulada' ? 'caja-orden-anulada' : ''}`}>
                <div className="caja-orden-info">
                  <span className="caja-orden-numero">#{String(o.numero_orden_dia).padStart(3, '0')}</span>
                  <span className={`etiqueta-estado etiqueta-${o.estado}`}>{o.estado}</span>
                  {o.tipo_servicio !== 'sala' && (
                    <span className="badge-servicio">{NOMBRE_SERVICIO[o.tipo_servicio]}</span>
                  )}
                  {o.mesas.length > 0 && !o.mesa_liberada && (
                    <span className="badge-mesa"><IconoSilla tam={15} /> {o.mesas.join(' + ')}</span>
                  )}
                  {(o.items.length + o.menus.length >= 2 || o.menus.length > 0) && (
                    <span className="badge-servicio">
                      {o.entrega === 'junto' ? 'Sale junto' : 'Por tiempos'}
                    </span>
                  )}
                  {o.pago_pendiente && (
                    <span className="chip-falta chip-falta-pagar">FALTA PAGAR</span>
                  )}
                  {(o.vuelto_pendiente ?? 0) > 0 && (
                    <span className="chip-falta chip-falta-vuelto">
                      FALTA VUELTO {soles(o.vuelto_pendiente ?? 0)}
                    </span>
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
                {o.estado !== 'anulada' && (
                  <div className="caja-orden-cobro">
                    {o.metodo_pago === null && !o.pago_pendiente && (
                      <span className="cobro-etiqueta">Cobrar:</span>
                    )}
                    {METODOS.map((m) => (
                      <button
                        key={m}
                        className={`boton-cobro ${o.metodo_pago === m ? 'cobro-activo' : ''}`}
                        onClick={() => cobrar(o, m)}
                      >
                        {NOMBRE_PAGO[m]}
                      </button>
                    ))}
                    <button
                      className={`boton-cobro ${o.pago_pendiente ? 'cobro-falta-activo' : ''}`}
                      onClick={() => alternarFaltaPagar(o)}
                      title="El ticket salió pero aún no pagan: el cierre no espera esa plata"
                    >
                      Falta pagar
                    </button>
                    {(o.vuelto_pendiente ?? 0) > 0 ? (
                      <button
                        className="boton boton--sm boton--culantro"
                        onClick={() => vueltoEntregado(o)}
                        title="Ya se le dio su vuelto"
                      >
                        Di el vuelto {soles(o.vuelto_pendiente ?? 0)}
                      </button>
                    ) : (
                      <button
                        className="boton-cobro"
                        onClick={() => {
                          setVueltoAbierto(vueltoAbierto === o.id ? null : o.id)
                          setPagoConTexto('')
                        }}
                        title="Pagó con billete grande y el vuelto queda debiendo"
                      >
                        Vuelto…
                      </button>
                    )}
                  </div>
                )}
                {vueltoAbierto === o.id && (
                  <div className="caja-orden-cobro fila-vuelto">
                    <label className="etiqueta-vuelto">
                      ¿Pagó con cuánto?
                      <input
                        type="number" step="0.10" min="0" autoFocus placeholder="50.00"
                        value={pagoConTexto} onChange={(e) => setPagoConTexto(e.target.value)}
                      />
                    </label>
                    {parseFloat(pagoConTexto) > o.total && (
                      <span className="vuelto-calculado">
                        vuelto: <strong>{soles(parseFloat(pagoConTexto) - o.total)}</strong>
                      </span>
                    )}
                    <button className="boton boton--sm boton--culantro" onClick={() => guardarVuelto(o)}>
                      Guardar
                    </button>
                    <button className="boton boton--sm boton--papel" onClick={() => setVueltoAbierto(null)}>
                      Cancelar
                    </button>
                  </div>
                )}
                <div className="caja-orden-botones">
                  {SIGUIENTE_ESTADO[o.estado] && (
                    <button
                      className="boton-avanzar"
                      onClick={() => avanzar(o)}
                    >▶ {SIGUIENTE_ESTADO[o.estado]}</button>
                  )}
                  <button onClick={() => reimprimir(o)}><IconoImpresora tam={18} /> Ticket</button>
                  {o.estado !== 'anulada' && (
                    <div className="menu-mas">
                      <button
                        className="boton-mas"
                        aria-haspopup="menu"
                        aria-expanded={menuAbierto === o.id}
                        aria-label="Más acciones"
                        onClick={() => setMenuAbierto(menuAbierto === o.id ? null : o.id)}
                      >
                        ⋯
                      </button>
                      {menuAbierto === o.id && (
                        <div className="popover-mas" role="menu">
                          <button role="menuitem" onClick={() => {
                            setMenuAbierto(null)
                            setAsignandoMesa(asignandoMesa === o.id ? null : o.id)
                          }}>
                            <IconoSilla tam={18} /> Mesa
                          </button>
                          {o.mesas.length > 0 && !o.mesa_liberada && (
                            <button role="menuitem" onClick={() => { setMenuAbierto(null); seFue(o) }}>
                              <IconoSilla tam={18} /> Se fue (liberar mesa)
                            </button>
                          )}
                          {(o.items.length + o.menus.length >= 2 || o.menus.length > 0) && (
                            <button role="menuitem" onClick={() => {
                              setMenuAbierto(null)
                              corregirEntrega(o, o.entrega === 'junto' ? 'separado' : 'junto')
                            }}>
                              Cambiar a {o.entrega === 'junto' ? 'por tiempos' : 'todo junto'}
                            </button>
                          )}
                          {o.estado !== 'entregado' && (
                            <button role="menuitem" className="popover-peligro"
                                    onClick={() => { setMenuAbierto(null); anular(o) }}>
                              <IconoAspa tam={18} /> Anular
                            </button>
                          )}
                        </div>
                      )}
                    </div>
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

      {ticket && (
        <div className="solo-impresion">
          <Ticket orden={ticket.orden} local={ticket.local} />
        </div>
      )}

      {ticketCierre && (
        <div className="solo-impresion">
          <TicketCierre
            estado={ticketCierre.estado}
            egresos={ticketCierre.egresos}
            local={ticketCierre.local}
          />
        </div>
      )}
    </div>
  )
}
