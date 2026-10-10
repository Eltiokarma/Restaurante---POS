import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, EMPAQUES, NOMBRE_CATEGORIA, NOMBRE_EMPAQUE, NOMBRE_ENTREGA, menuAPayload, precioUnitarioMenu, soles, subtotalMenu, tiemposPendientes, unidadesEnTaper } from '../api'
import type { Bebida, ConfigOut, DatosLocal, Entrega, MenuCarrito, MenuHoy, MesaEstado, OrdenOut, PagoTerminal, Plato, StockPlato, VozItemResuelto } from '../api'
import { describirMenu } from '../components/describirMenu'
import { menusEnPedido, TarjetaOfertaMenu } from '../components/TarjetaOfertaMenu'
import {
  BarraPersonas, guardarDefectos, HojaDefecto, leerDefectos, useTicketsPersonas,
} from '../components/RepartoMenu'
import { SugerenciaMenu } from '../components/SugerenciaMenu'
import { BarraCarrito } from '../components/BarraCarrito'
import { CountdownCancel } from '../components/CountdownCancel'
import { GaseosasTerminal } from '../components/GaseosasTerminal'
import { StockHoy } from '../components/StockHoy'
import { ModificarPedido } from '../components/ModificarPedido'
import { AnularPedido } from '../components/AnularPedido'
import { PedidoPorVoz } from '../components/PedidoPorVoz'
import type { ExtrasVoz } from '../components/PedidoPorVoz'
import { TarjetaPlato } from '../components/TarjetaPlato'
import { Ticket } from '../components/Ticket'
import { menuVacio, useCarrito } from '../hooks/useCarrito'
import { useInactividad } from '../hooks/useInactividad'

function ModalCancelarTodo({ onSeguir, onCancelar }: { onSeguir: () => void; onCancelar: () => void }) {
  return (
    <div className="modal-fondo">
      <div className="modal">
        <h2>¿Cancelar todo el pedido?</h2>
        <div className="modal-botones">
          <button className="boton-grande boton-secundario" onClick={onSeguir}>
            No, seguir pidiendo
          </button>
          <button className="boton-grande boton-cancelar-rojo" onClick={onCancelar}>
            Sí, cancelar todo
          </button>
        </div>
      </div>
    </div>
  )
}

type Pantalla = 'inicio' | 'menu' | 'resumen' | 'countdown' | 'final' | 'modificar'

// Cómo pagó, dicho al confirmar (pedido del dueño: antes un solo "OK y
// pagó" asumía efectivo y el Yape descuadraba la caja)
const PAGOS_TERMINAL: { pago: Exclude<PagoTerminal, 'pendiente'>; texto: string; corto: string }[] = [
  { pago: 'efectivo', texto: '💵 Pagó efectivo', corto: 'Efectivo' },
  { pago: 'yape', texto: '📱 Pagó Yape', corto: 'Yape' },
  { pago: 'mixto', texto: '💵📱 Pagó mixto', corto: 'Mixto' },
]

export function Cliente() {
  const [pantalla, setPantalla] = useState<Pantalla>('inicio')
  // Número que tendrá este pedido (pedido del dueño: tener clara la
  // numeración mientras se arma). Vista previa: el definitivo lo pone el
  // backend al guardar; se refresca por si otra terminal ganó el número
  const [numeroPrevio, setNumeroPrevio] = useState<number | null>(null)
  useEffect(() => {
    if (pantalla !== 'resumen' && pantalla !== 'countdown' && pantalla !== 'menu') return
    let vivo = true
    const pedir = () => api.siguienteNumero().then((r) => { if (vivo) setNumeroPrevio(r.numero) }).catch(() => {})
    pedir()
    const t = window.setInterval(pedir, 10000)
    return () => { vivo = false; window.clearInterval(t) }
  }, [pantalla])
  const rotuloTicket = numeroPrevio !== null && (
    <span className="numero-previo">Ticket #{String(numeroPrevio).padStart(3, '0')}</span>
  )
  const [platos, setPlatos] = useState<Plato[]>([])
  const [menusHoy, setMenusHoy] = useState<MenuHoy[]>([])
  const [gaseosas, setGaseosas] = useState<Bebida[]>([])
  const [stock, setStock] = useState<StockPlato[]>([])
  // Menú encadenado que se está armando (abre el modal de tiempos)
  // Menú recién agregado con "Un menú": el botón confirma un momento
  const [menuRecien, setMenuRecien] = useState<number | null>(null)
  useEffect(() => {
    if (menuRecien === null) return
    const timer = setTimeout(() => setMenuRecien(null), 1600)
    return () => clearTimeout(timer)
  }, [menuRecien])
  const [config, setConfig] = useState<ConfigOut | null>(null)
  const carrito = useCarrito()

  const [confirmandoCancelarTodo, setConfirmandoCancelarTodo] = useState(false)
  const [mensajeInicio, setMensajeInicio] = useState('')
  const [errorConexion, setErrorConexion] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [ordenFinal, setOrdenFinal] = useState<{ orden: OrdenOut; local: DatosLocal } | null>(null)
  // "Anular este pedido" desde la pantalla final (se arrepintió / duplicado)
  const [anulando, setAnulando] = useState(false)
  const [anulada, setAnulada] = useState(false)
  const [vozAbierta, setVozAbierta] = useState(false)
  const [entrega, setEntrega] = useState<Entrega>('separado')
  // Mesa elegida al tomar el pedido (opcional): si no eligen, el ticket
  // sale "SIN MESA" y en caja la asignan después
  const [mesas, setMesas] = useState<MesaEstado[]>([])
  const [mesasElegidas, setMesasElegidas] = useState<number[]>([])
  // Con 30+ mesas la parrilla come la pantalla: vive plegada y lo elegido
  // se ve en la cabecera del pliegue
  const [mostrarMesas, setMostrarMesas] = useState(false)
  // Guía de lo que falta (4b): la barra de abajo nombra el hueco y "IR AHÍ"
  // abre las opciones de ese plato en el ticket de la persona
  // La flecha de "IR AHÍ" rebota SOLO si la tarjeta pendiente quedó fuera
  // de vista (detalle del handoff: movimiento permanente en táctil cansa)
  const [pendienteALaVista, setPendienteALaVista] = useState(true)

  // Lo que el backend reclamaría con un 422 al final, dicho desde el
  // principio y con el mismo lenguaje (espejo de la validación)
  const pendientesMenus = carrito.menus.flatMap((m, idx) =>
    tiemposPendientes(m).map((t) => ({
      idx, rotulo: t.rotulo, orden: t.orden,
      // Mismo número que dice el ticket: se cuenta dentro de su menú
      numero: carrito.menus.slice(0, idx + 1).filter((x) => x.menu.id === m.menu.id).length,
    })),
  )

  const primerPendienteIdx = carrito.menus.findIndex((m) => tiemposPendientes(m).length > 0)

  useEffect(() => {
    if (primerPendienteIdx < 0) return
    const objetivo = document.getElementById(`ticket-persona-${primerPendienteIdx}`)
    if (!objetivo || typeof IntersectionObserver === 'undefined') return
    const observador = new IntersectionObserver(
      ([entrada]) => setPendienteALaVista(entrada.isIntersecting),
      { threshold: 0.4 },
    )
    observador.observe(objetivo)
    return () => observador.disconnect()
  }, [primerPendienteIdx, pantalla])

  const irAlPendiente = () => {
    const primero = pendientesMenus[0]
    if (!primero) return
    // "IR AHÍ": lleva al ticket de esa persona y abre las opciones del
    // plato que le falta, listas para tocar
    document
      .getElementById(`ticket-persona-${primero.idx}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    tickets.abrirTiempo(primero.idx, primero.orden)
  }
  // Para el campo origen de la orden: qué canales llenaron el carrito
  const usoVoz = useRef(false)
  const usoTactil = useRef(false)
  // Candado: si el local exige apertura de caja, la terminal no vende
  // hasta que el cajero registre el fondo inicial
  const [cajaLista, setCajaLista] = useState(true)

  useEffect(() => {
    if (pantalla !== 'inicio' || !config?.exigir_caja_abierta) {
      setCajaLista(true)
      return
    }
    const revisar = () =>
      api.cajaHoy()
        .then((c) => setCajaLista(c.abierta || c.cerrada))
        .catch(() => setCajaLista(true)) // sin conexión: no bloquear de más
    revisar()
    const intervalo = window.setInterval(revisar, 15_000)
    return () => window.clearInterval(intervalo)
  }, [pantalla, config?.exigir_caja_abierta])

  const { sincronizarConMenu, vaciar } = carrito
  const cargarMenu = useCallback(async () => {
    try {
      const data = await api.menuHoy()
      setPlatos(data.platos)
      setMenusHoy(data.menus)
      setStock(data.stock ?? [])
      // Gaseosas de la lista fija; si falla, la terminal sigue sin ellas
      api.bebidas().then((d) => setGaseosas(d.bebidas.filter((b) => b.activa))).catch(() => {})
      // Si el admin cambió un precio a mitad de pedido, el carrito se
      // actualiza para que el total mostrado coincida con lo que se cobra.
      sincronizarConMenu(data.platos, data.menus)
      return data.menus
    } catch {
      // Si el polling falla se mantiene el último menú conocido
      return undefined
    }
  }, [sincronizarConMenu])

  useEffect(() => {
    api.config().then(setConfig).catch(() => {})
    cargarMenu()
  }, [cargarMenu])

  // Las mesas se refrescan mientras se arma el pedido (ocupación al día)
  useEffect(() => {
    const cargarMesas = () => api.mesas().then((d) => setMesas(d.mesas)).catch(() => {})
    cargarMesas()
    if (pantalla !== 'resumen') return
    const intervalo = window.setInterval(cargarMesas, 30_000)
    return () => window.clearInterval(intervalo)
  }, [pantalla])

  // Si un plato se agota, el admin lo desactiva y desaparece de la terminal
  // en el siguiente refresco: polling cada 30s mientras se arma el pedido.
  useEffect(() => {
    // También en el inicio: ahí se ve cuántos quedan de cada plato
    if (pantalla !== 'menu' && pantalla !== 'resumen' && pantalla !== 'inicio') return
    const intervalo = window.setInterval(cargarMenu, 30_000)
    return () => window.clearInterval(intervalo)
  }, [pantalla, cargarMenu])

  const volverAlInicio = useCallback(
    (mensaje = '') => {
      vaciar()
      setConfirmandoCancelarTodo(false)
      setErrorConexion('')
      setMensajeInicio(mensaje)
      setVozAbierta(false)
      setEntrega('separado')
      setMesasElegidas([])
      setCopias(1)
      setPagoElegido(undefined)
      setMostrarMesas(false)
      usoVoz.current = false
      usoTactil.current = false
      setPantalla('inicio')
    },
    [vaciar],
  )

  // Timeout de inactividad solo mientras se arma el pedido
  const inactividadActiva = pantalla === 'menu' || pantalla === 'resumen'
  const inactividad = useInactividad(
    inactividadActiva,
    config?.timeout_inactividad_seg ?? 90,
    15,
    () => volverAlInicio(),
  )

  // Para medir cuánto demora un cliente de punta a punta (métrica del admin)
  const inicioPedidoTs = useRef<number | null>(null)

  // Pedido del dueño: con solo menús, UNA pantalla — el botón "UN MENÚ"
  // arriba y las tarjetas editables abajo (sin pantalla intermedia de carta).
  // Si hoy no hay ningún menú activo, la carta aparece como respaldo.
  const soloMenusConfig = config?.terminal_solo_menus ?? true
  // Regla del local: qué empaques se ofrecen hoy y cuánto cuesta el táper
  const empaquesOfrecidos = config?.empaques_ofrecidos ?? EMPAQUES
  const precioTaper = config?.precio_taper ?? 0
  // "Platos por defecto" de ESTA terminal (pedido del dueño, por ahora):
  // cada persona nueva arranca con ellos
  const [defectos, setDefectos] = useState(leerDefectos)
  // Comandas a imprimir: 1, o 2 con el botón chico "×2" (una para la guía)
  const [copias, setCopias] = useState(1)
  const [editandoDefecto, setEditandoDefecto] = useState<MenuHoy | null>(null)
  // "Va a esperar" también en la terminal (pedido del dueño): la entrada
  // ahora y el segundo después
  const tickets = useTicketsPersonas(carrito, { empaques: empaquesOfrecidos, precioTaper, conEspera: true })
  const tapers = unidadesEnTaper(carrito.items, carrito.menus)
  const cargoTaper = precioTaper * tapers
  const totalConCargos = carrito.totalSoles + cargoTaper
  // Mientras el carrito tenga menús, la pantalla única no cambia de forma
  // aunque el menú del día se agote a mitad de pedido
  const soloMenus = soloMenusConfig && (menusHoy.length > 0 || carrito.menus.length > 0)

  // La voz solo SUMA al carrito (platos y tickets por persona); todo lo
  // demás es el flujo de siempre
  const agregarItemsVoz = (items: VozItemResuelto[], menus: MenuCarrito[], extras: ExtrasVoz) => {
    for (const item of items) {
      const plato = platos.find((p) => p.id === item.plato_id)
      if (plato) carrito.cambiarCantidad(plato, item.cantidad)
    }
    if (menus.length > 0) carrito.quitarMenusVacios()
    for (const menu of menus) carrito.agregarMenu(menu)
    for (const g of extras.gaseosas) carrito.cambiarBebida(g.bebida, g.cantidad)
    // "Para la mesa 2B": la mesa se suma a las ya elegidas
    if (extras.mesa) {
      const id = extras.mesa.id
      setMesasElegidas((prev) => (prev.includes(id) ? prev : [...prev, id]))
    }
    if (items.length > 0 || menus.length > 0 || extras.gaseosas.length > 0) usoVoz.current = true
  }

  // Dictado sin dudas sobre un pedido recién empezado: directo a la ventana
  // de cancelación (ahí se ve, se cancela o se vuelve a corregir). Si ya
  // había algo armado a mano, se verifica como siempre
  const carritoVirgen = carrito.items.length === 0 && carrito.bebidas.length === 0
    && carrito.menus.every(menuVacio)
  const vozDirecta = (items: VozItemResuelto[], menus: MenuCarrito[], extras: ExtrasVoz) => {
    agregarItemsVoz(items, menus, extras)
    setVozAbierta(false)
    setCopias(1)
    setPagoElegido(undefined)
    setPantalla('countdown')
  }

  // El botón vive dentro del área táctil de inicio: un toque dispara los
  // dos onClick. Sin este candado entraban dos menús en vez de uno
  const empezando = useRef(false)
  const empezarPedido = async () => {
    if (empezando.current) return
    empezando.current = true
    setMensajeInicio('')
    inicioPedidoTs.current = Date.now()
    // Se espera el menú fresco: así la primera pantalla se decide con datos
    // reales aunque la tablet recién cargue la página
    const menus = (await cargarMenu()) ?? menusHoy
    const directoAlPedido = soloMenusConfig && menus.length > 0
    // Pedido por personas: se arranca con UNA (el + suma más)
    if (directoAlPedido) carrito.agregarMenuCompleto(menus[0], false, defectos[menus[0].id])
    setPantalla(directoAlPedido ? 'resumen' : 'menu')
    empezando.current = false
  }

  const cancelarPedidoEnVentana = async () => {
    const items = [
      ...carrito.menus.map((m) => ({
        nombre: `${m.menu.nombre} (${describirMenu(m)})`,
        precio: precioUnitarioMenu(m),
        cantidad: m.cantidad,
      })),
      ...carrito.items.map((i) => ({
        nombre: i.plato.nombre,
        precio: i.plato.precio,
        cantidad: i.cantidad,
      })),
      ...carrito.bebidas.map((b) => ({
        nombre: b.bebida.nombre,
        precio: b.bebida.precio,
        cantidad: b.cantidad,
      })),
    ]
    const total = totalConCargos
    volverAlInicio('Pedido cancelado')
    try {
      await api.registrarCancelacion(items, total)
    } catch {
      // El log de cancelaciones es solo para análisis; si falla no
      // bloqueamos al cliente.
    }
  }

  // Un plato "al momento" (bistec frito) obliga a entrega separada.
  const alMomentoEnItems = carrito.items.find((i) => i.plato.sale_al_momento)
  const nombreAlMomento = alMomentoEnItems?.plato.nombre
  const hayAlMomento = nombreAlMomento !== undefined
  const entregaEfectiva: Entrega = hayAlMomento ? 'separado' : entrega

  // Las gaseosas van CON un pedido: solas se venden desde caja
  const sinPlatos = carrito.menus.length === 0 && carrito.items.length === 0

  const guardandoRef = useRef(false)
  // "Pagó efectivo / Yape / mixto" o "No pagó" dicho antes de la ventana
  // (seguir sin elegir): al vencer la ventana se confirma con eso
  const [pagoElegido, setPagoElegido] = useState<PagoTerminal | undefined>(undefined)
  const irAVentana = (pago?: PagoTerminal) => {
    setCopias(1)
    setPagoElegido(pago)
    setPantalla('countdown')
  }

  // pago: "Pagó efectivo / Yape / mixto" / "OK y no pagó"; si la ventana
  // vence sola, no se dice
  const confirmarDefinitivo = async (pago?: PagoTerminal) => {
    if (guardandoRef.current) return
    guardandoRef.current = true
    setGuardando(true)
    setErrorConexion('')
    try {
      const duracion = inicioPedidoTs.current
        ? Math.min(3600, Math.round((Date.now() - inicioPedidoTs.current) / 1000))
        : undefined
      const origen = usoVoz.current && usoTactil.current ? 'mixto' : usoVoz.current ? 'voz' : 'tactil'
      const resultado = await api.crearOrden(
        carrito.items.map((i) => ({
          plato_id: i.plato.id, cantidad: i.cantidad, empaque: i.empaque, nota: i.nota.trim(),
        })),
        duracion,
        origen,
        mesasElegidas,
        entregaEfectiva,
        carrito.menus.map(menuAPayload),
        copias,
        carrito.bebidas.map((b) => ({ bebida_id: b.bebida.id, cantidad: b.cantidad })),
        pago,
      )
      setOrdenFinal(resultado)
      setAnulada(false)
      carrito.vaciar()
      setPantalla('final')
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // Un plato se agotó entre que lo agregó y confirmó: lo quitamos del
        // carrito para que el pedido no quede atascado.
        try {
          const menu = await api.menuHoy()
          setPlatos(menu.platos)
          setMenusHoy(menu.menus)
          const disponibles = new Set(menu.platos.map((p) => p.id))
          const menusDisponibles = new Set(menu.menus.map((m) => m.id))
          const agotados = [
            ...carrito.items
              .filter((i) => !disponibles.has(i.plato.id))
              .map((i) => i.plato.nombre),
            ...carrito.menus
              .filter(
                (m) =>
                  !menusDisponibles.has(m.menu.id) ||
                  !Object.values(m.elecciones).every((id) => disponibles.has(id)),
              )
              .map((m) => m.menu.nombre),
          ]
          carrito.eliminarNoDisponibles(disponibles, menusDisponibles)
          setErrorConexion(
            agotados.length > 0
              ? `Se agotó: ${agotados.join(', ')}. Lo quitamos de tu pedido; revisa y confirma de nuevo.`
              : e.message,
          )
        } catch {
          setErrorConexion(e.message)
        }
      } else if (e instanceof ApiError && e.status === 422) {
        // El backend explica qué falta ("Falta elegir Segundo del Menú del
        // día"): mostrarlo tal cual es más útil que un error genérico
        setErrorConexion(e.message)
      } else if (e instanceof ApiError) {
        setErrorConexion(e.message)
      } else {
        // Robustez offline parcial: no se pierde el carrito
        setErrorConexion('Error de conexión, intenta de nuevo')
      }
      setPantalla('resumen')
    } finally {
      guardandoRef.current = false
      setGuardando(false)
    }
  }

  // Imprimir el ticket cuando ya está montado en el DOM. Con cleanup: si el
  // cliente toca la pantalla y sale antes de que dispare, no se imprime una
  // hoja en blanco. En "estacion" imprime la PC con /ticketera; en "puente"
  // el puente del local manda ESC/POS directo a la impresora de red.
  const imprimeAqui = (config?.modo_impresion ?? 'terminal') === 'terminal'
  useEffect(() => {
    if (pantalla !== 'final' || !ordenFinal || !imprimeAqui) return
    const timer = window.setTimeout(() => window.print(), 200)
    return () => window.clearTimeout(timer)
  }, [pantalla, ordenFinal, imprimeAqui])

  // Pantalla final: volver al inicio a los 10 segundos (no mientras se
  // está anulando el pedido)
  useEffect(() => {
    if (pantalla !== 'final' || anulando) return
    const timer = window.setTimeout(() => {
      setOrdenFinal(null)
      volverAlInicio()
    }, 10_000)
    return () => window.clearTimeout(timer)
  }, [pantalla, volverAlInicio, anulando])

  // ---------- Pantallas ----------

  if (pantalla === 'inicio') {
    if (!cajaLista) {
      return (
        <div className="pantalla pantalla-inicio">
          <h1 className="logo-restaurante">{config?.nombre_local || 'Restaurante'}</h1>
          <div className="aviso-cancelado">🕐 Un momentito, aún estamos abriendo la caja…</div>
          <p className="texto-toca">La terminal se habilita sola cuando la caja abra</p>
        </div>
      )
    }
    // "Toca la pantalla para empezar": cualquier toque inicia el pedido
    return (
      <div className="pantalla pantalla-inicio" onClick={empezarPedido}>
        {mensajeInicio && <div className="aviso-cancelado">{mensajeInicio}</div>}
        <h1 className="logo-restaurante">{config?.nombre_local || 'Restaurante'}</h1>
        <button className="boton-hacer-pedido" onClick={empezarPedido}>
          🍽️ HACER MI PEDIDO
        </button>
        <p className="texto-toca">Toca la pantalla para empezar</p>
        <StockHoy stock={stock} />
        {/* Cambios a un pedido ya confirmado (pedido del dueño, que hoy
            atiende desde la terminal): no debe disparar un pedido nuevo */}
        <button
          className="boton-modificar-pedido"
          onClick={(e) => { e.stopPropagation(); setPantalla('modificar') }}
        >
          ✏️ Modificar un pedido
        </button>
      </div>
    )
  }

  if (pantalla === 'modificar') {
    return (
      <ModificarPedido
        menusHoy={menusHoy}
        gaseosas={gaseosas}
        empaques={empaquesOfrecidos}
        local={{ nombre: config?.nombre_local ?? '', direccion: config?.direccion ?? '', ruc: config?.ruc ?? '' }}
        onCerrar={() => setPantalla('inicio')}
      />
    )
  }

  if (pantalla === 'final' && ordenFinal) {
    return (
      <div className="pantalla pantalla-final" onClick={() => {
        if (anulando) return
        setOrdenFinal(null)
        setAnulada(false)
        volverAlInicio()
      }}>
        <div className={`numero-orden-gigante ${anulada ? 'orden-anulada' : ''}`}>
          ORDEN #{String(ordenFinal.orden.numero_orden_dia).padStart(3, '0')}
        </div>
        {anulada && <p className="texto-final">🗑 Pedido anulado</p>}
        <p className="texto-final">Paga en caja mostrando este ticket. ¡Gracias!</p>
        <button
          className="boton-grande boton-secundario"
          onClick={(e) => {
            e.stopPropagation()
            if (imprimeAqui) {
              window.print()
            } else {
              // Reencola el ticket para que /ticketera lo vuelva a imprimir
              api.reimprimirOrden(ordenFinal.orden.id).catch(() => {})
            }
          }}
        >
          🖨️ Imprimir de nuevo
        </button>
        {/* Pedido del dueño: el cliente se arrepiente al toque (aunque ya
            haya pagado) o el pedido salió dos veces */}
        {!anulada && (
          <button
            className="boton-grande boton-anular-pedido"
            onClick={(e) => { e.stopPropagation(); setAnulando(true) }}
          >
            🗑 Anular este pedido
          </button>
        )}
        <p className="texto-toca">Volviendo al inicio…</p>
        {!anulada && <Ticket orden={ordenFinal.orden} local={ordenFinal.local} />}
        {anulando && (
          <AnularPedido
            orden={ordenFinal.orden}
            local={ordenFinal.local}
            onAnulado={() => setAnulada(true)}
            onCerrar={() => setAnulando(false)}
          />
        )}
      </div>
    )
  }

  if (pantalla === 'countdown') {
    return (
      <div className="pantalla pantalla-countdown">
        <h1>¿Estás seguro?</h1>
        {numeroPrevio !== null && (
          <div className="numero-previo-grande">Ticket #{String(numeroPrevio).padStart(3, '0')}</div>
        )}
        <p className="texto-countdown">Tienes {config?.ventana_cancelacion_seg ?? 30} segundos para cancelar.</p>
        {copias > 1 && <p className="aviso-dos-comandas">🖨 Saldrán {copias} comandas</p>}
        <CountdownCancel
          duracionSeg={config?.ventana_cancelacion_seg ?? 30}
          onTerminado={() => confirmarDefinitivo(pagoElegido)}
        />
        <div className="resumen-breve">
          {carrito.menus.map((m, idx) => (
            <div key={`menu-${idx}`}>
              {m.cantidad} × {m.menu.nombre} ({describirMenu(m)})
            </div>
          ))}
          {carrito.items.map((i) => (
            <div key={i.plato.id}>
              {i.cantidad} × {i.plato.nombre}
            </div>
          ))}
          {carrito.bebidas.map((b) => (
            <div key={`gaseosa-${b.bebida.id}`}>
              {b.cantidad} × {b.bebida.nombre}
            </div>
          ))}
          {mesasElegidas.length > 0 && (
            <div>
              🪑 Mesa:{' '}
              {mesas.filter((m) => mesasElegidas.includes(m.id)).map((m) => m.nombre).join(' + ')}
            </div>
          )}
          <div className="resumen-breve-total">Total: {soles(totalConCargos)}</div>
        </div>
        <button className="boton-grande boton-cancelar-rojo" onClick={cancelarPedidoEnVentana} disabled={guardando}>
          🛑 CANCELAR PEDIDO
        </button>
        {/* Volver sin cancelar: faltaba el camino "me equivoqué en algo" */}
        <button className="boton-grande boton-secundario" onClick={() => setPantalla('resumen')} disabled={guardando}>
          ↩ VOLVER A CORREGIR
        </button>
        {/* Confirman ya y dicen si pagó y cómo: sale en la comanda; si
            pagó, además la precuenta con el método (pedido del dueño). El
            mixto no pide montos: cuánto fue por Yape lo pone la caja */}
        <div className="botones-pago">
          {PAGOS_TERMINAL.map(({ pago, texto }) => (
            <button
              key={pago}
              className={`boton-grande boton-confirmar ${pagoElegido === pago ? 'pago-elegido' : ''}`}
              onClick={() => confirmarDefinitivo(pago)}
              disabled={guardando}
            >
              {guardando ? 'Guardando…' : texto}
            </button>
          ))}
          <button
            className={`boton-grande boton-secundario ${pagoElegido === 'pendiente' ? 'pago-elegido' : ''}`}
            onClick={() => confirmarDefinitivo('pendiente')}
            disabled={guardando}
          >
            OK y no pagó
          </button>
        </div>
      </div>
    )
  }

  if (pantalla === 'resumen') {
    return (
      <div className="pantalla pantalla-resumen">
        {soloMenus ? (
          <div className="cabecera-menu cabecera-en-pedido cabecera-compacta">
            <button className="boton-cancelar-todo" onClick={() => setConfirmandoCancelarTodo(true)}>
              ← Cancelar todo
            </button>
            <h1>Tu pedido {rotuloTicket}</h1>
            {config?.voz_disponible && (
              <button className="boton-pedir-voz" onClick={() => setVozAbierta(true)}>
                🎤 PEDIR POR VOZ
              </button>
            )}
          </div>
        ) : (
          <h1>Tu pedido {rotuloTicket}</h1>
        )}
        {/* Sin riel de pasos (pedido del dueño): el espacio es para los tickets */}
        {errorConexion && <div className="banner-error">{errorConexion}</div>}
        <StockHoy stock={stock} />
        {soloMenus && (
          <div className="oferta-menus">
            {/* Una tarjeta = una persona: + y − grandes y el monto a la vista */}
            {menusHoy.map((m) => (
              <div key={m.id} className="combo">
                <BarraPersonas
                  menu={m}
                  personas={menusEnPedido(carrito.menus, m.id)}
                  total={menusHoy.length > 1
                    ? carrito.menus.filter((x) => x.menu.id === m.id).reduce((s, x) => s + subtotalMenu(x), 0)
                    : totalConCargos}
                  onMas={() => { usoTactil.current = true; carrito.agregarMenuCompleto(m, false, defectos[m.id]) }}
                  onDefecto={() => setEditandoDefecto(m)}
                  onAplicarDefecto={defectos[m.id] ? () => carrito.aplicarDefecto(m.id, defectos[m.id]) : undefined}
                  onMenos={() => carrito.quitarUltimoMenu(m.id)}
                />
              </div>
            ))}
            {carrito.totalItems === 0 && (
              <p className="nota-oferta">
                Toca el botón por cada menú que quieras; abajo puedes cambiar cada uno a su
                gusto (sin sopa, para llevar, con una presa más…).
              </p>
            )}
          </div>
        )}
        <SugerenciaMenu items={carrito.items} menus={menusHoy} onConvertir={carrito.convertirEnMenu} />
        {/* Sin "¿Cómo va cada plato? Todos:" (pedido del dueño): el empaque se
            elige en la letra de cada plato del ticket, para una o para todas */}
        <div className="lista-resumen">
          {/* Un ticket vertical por persona (boceto del dueño) */}
          {tickets.grilla}
          {carrito.items.map((i) => (
            <div className="linea-resumen linea-con-empaque" key={i.plato.id}>
              <div className="linea-resumen-fila">
                <span>
                  {i.cantidad} × {i.plato.nombre}
                </span>
                <span className="linea-resumen-precios">
                  {soles(i.plato.precio)} c/u — <strong>{soles(i.plato.precio * i.cantidad)}</strong>
                </span>
              </div>
              <div className="empaques-linea">
                {empaquesOfrecidos.map((e) => (
                  <button
                    key={e}
                    className={`boton-servicio boton-empaque ${i.empaque === e ? 'servicio-activo' : ''}`}
                    onClick={() => carrito.cambiarEmpaque(i.plato.id, e)}
                  >
                    {NOMBRE_EMPAQUE[e]}
                    {e === 'taper' && precioTaper > 0 && <small> +{soles(precioTaper)}</small>}
                  </button>
                ))}
              </div>
              <input
                className="input-nota-plato"
                placeholder="📝 Algún cambio: sin arroz, sin frijoles, con huevo frito…"
                maxLength={150}
                value={i.nota}
                onChange={(e) => carrito.cambiarNota(i.plato.id, e.target.value)}
              />
            </div>
          ))}
        </div>
        <GaseosasTerminal
          lista={gaseosas}
          enCarrito={carrito.bebidas}
          onCambiar={(b, delta) => { usoTactil.current = true; carrito.cambiarBebida(b, delta) }}
        />
        {carrito.totalItems > 0 && mesas.some((m) => m.activa) && (
          <div className="selector-servicio pliegue-extras">
            <button className="pliegue-cabecera" onClick={() => setMostrarMesas((v) => !v)}>
              <span className="pliegue-titulo">
                🪑 ¿En qué mesa van a estar? <small className="titulo-opcional">(opcional)</small>
              </span>
              {mesasElegidas.length > 0 && (
                <span className="pliegue-resumen">
                  {mesas.filter((m) => mesasElegidas.includes(m.id)).map((m) => m.nombre).join(' + ')}
                </span>
              )}
              <span className="tarjeta-menu-flecha">{mostrarMesas ? '▲' : '▼'}</span>
            </button>
            {mostrarMesas && (
              <>
                <div className="empaques-linea mesas-terminal">
                  {mesas.filter((m) => m.activa).map((m) => (
                    <button
                      key={m.id}
                      className={`boton-servicio boton-empaque ${mesasElegidas.includes(m.id) ? 'servicio-activo' : ''}`}
                      onClick={() =>
                        setMesasElegidas((prev) =>
                          prev.includes(m.id) ? prev.filter((x) => x !== m.id) : [...prev, m.id],
                        )
                      }
                    >
                      {m.nombre}
                      {m.ocupada ? ' •' : ''}
                    </button>
                  ))}
                </div>
                <p className="aviso-entrega">
                  {mesasElegidas.length > 0
                    ? 'Puedes marcar varias si van a juntar mesas.'
                    : 'Si aún no eligen mesa, sigue nomás: en caja te la asignan.'}
                </p>
              </>
            )}
          </div>
        )}
        {(carrito.items.length >= 2 || hayAlMomento) && (
          <div className="selector-servicio">
            <span className="selector-servicio-titulo">
              {carrito.menus.length > 0 ? '¿Cómo salen los platos sueltos?' : '¿Cómo sale tu pedido?'}
            </span>
            <div className="selector-entrega">
              {(['junto', 'separado'] as Entrega[]).map((e) => (
                <button
                  key={e}
                  className={`boton-entrega ${entregaEfectiva === e ? 'entrega-activa' : ''}`}
                  disabled={e === 'junto' && hayAlMomento}
                  onClick={() => setEntrega(e)}
                >
                  {NOMBRE_ENTREGA[e].titulo}
                  <small>{NOMBRE_ENTREGA[e].detalle}</small>
                </button>
              ))}
            </div>
            {hayAlMomento && (
              <p className="aviso-entrega">
                {nombreAlMomento} se prepara al momento, así que tu pedido saldrá
                por tiempos: lo demás llega primero.
              </p>
            )}
          </div>
        )}
        {carrito.totalItems > 0 && (
          <>
            {cargoTaper > 0 && (
              <div className="linea-cargo-taper">
                {tapers} {tapers === 1 ? 'táper' : 'táperes'} × {soles(precioTaper)} ={' '}
                <strong>{soles(cargoTaper)}</strong>
              </div>
            )}
            <div className="total-grande">TOTAL: {soles(totalConCargos)}</div>
          </>
        )}
        <div className="pie-resumen">
          {carrito.menus.length > 0 && carrito.totalItems > 0 && (
            <div className={`barra-guia ${pendientesMenus.length > 0 ? 'guia-falta' : 'guia-lista'}`}>
              {pendientesMenus.length > 0 ? (
                <>
                  <span className="barra-guia-texto">
                    <span className="guia-kicker">
                      Falta {pendientesMenus.length} cosa{pendientesMenus.length === 1 ? '' : 's'}
                    </span>
                    Elegir {pendientesMenus[0].rotulo.toLowerCase()} de la Persona {pendientesMenus[0].numero}
                  </span>
                  <button className="boton-ir-ahi" onClick={irAlPendiente}>
                    IR AHÍ <span className={pendienteALaVista ? '' : 'flecha-rebota'} aria-hidden="true">↓</span>
                  </button>
                  {/* Pedido del dueño: el ticket puede salir sin elegirlo
                      (sale "FALTA ELEGIR") y de una se dice si pagó */}
                  <div className="sin-elegir-pago" role="group" aria-label="Seguir sin elegir">
                    <span className="sin-elegir-rotulo">Así nomás:</span>
                    {PAGOS_TERMINAL.map(({ pago, corto }) => (
                      <button key={pago} className="boton-sin-elegir-pago pagado" onClick={() => irAVentana(pago)}>
                        {corto}
                      </button>
                    ))}
                    <button className="boton-sin-elegir-pago pendiente" onClick={() => irAVentana('pendiente')}>
                      No pagó
                    </button>
                  </div>
                </>
              ) : (
                <span className="barra-guia-texto">
                  <span className="guia-kicker">Ya no falta nada</span>
                  ✓ Todo elegido: confirma cuando quieras
                </span>
              )}
            </div>
          )}
          <div className="botones-resumen">
            {!soloMenus && (
              <button className="boton-grande boton-secundario" onClick={() => setPantalla('menu')}>
                ← Modificar
              </button>
            )}
            <button
              className="boton-grande boton-confirmar"
              disabled={sinPlatos || guardando}
              onClick={() => {
                setCopias(1)
                // Con huecos pendientes, confirmar LLEVA al hueco: el 422
                // del final deja de existir
                if (pendientesMenus.length > 0) irAlPendiente()
                else { setPagoElegido(undefined); setPantalla('countdown') }
              }}
            >
              ✅ CONFIRMAR PEDIDO
            </button>
            {/* Chiquito: confirma e imprime 2 comandas (una para la guía) */}
            <button
              className="boton-dos-comandas"
              disabled={sinPlatos || guardando}
              onClick={() => {
                setCopias(2)
                if (pendientesMenus.length > 0) irAlPendiente()
                else { setPagoElegido(undefined); setPantalla('countdown') }
              }}
              title="Confirmar e imprimir 2 comandas"
            >
              ✅ ×2<small>comandas</small>
            </button>
          </div>
        </div>
        {confirmandoCancelarTodo && (
          <ModalCancelarTodo
            onSeguir={() => setConfirmandoCancelarTodo(false)}
            onCancelar={() => volverAlInicio()}
          />
        )}
        {vozAbierta && (
          <PedidoPorVoz
            platos={platos}
            menus={menusHoy}
            gaseosasLista={gaseosas}
            onContinuar={(items, menus, extras) => { agregarItemsVoz(items, menus, extras); setVozAbierta(false) }}
            onUsarBotones={(items, menus, extras) => { agregarItemsVoz(items, menus, extras); setVozAbierta(false) }}
            onDirecto={carritoVirgen ? vozDirecta : undefined}
            onCerrar={() => setVozAbierta(false)}
          />
        )}
        {tickets.hojas}
        {editandoDefecto && (
          <HojaDefecto
            menu={editandoDefecto}
            defecto={defectos[editandoDefecto.id] ?? { elecciones: {}, omitidos: [], empaques: {} }}
            empaques={empaquesOfrecidos}
            personas={menusEnPedido(carrito.menus, editandoDefecto.id)}
            onCerrar={() => setEditandoDefecto(null)}
            onGuardar={(d, aplicar) => {
              const nuevos = { ...defectos, [editandoDefecto.id]: d }
              setDefectos(nuevos)
              guardarDefectos(nuevos)
              if (aplicar) carrito.aplicarDefecto(editandoDefecto.id, d)
              setEditandoDefecto(null)
            }}
          />
        )}
        <AvisoInactividad {...inactividad} />
      </div>
    )
  }

  // pantalla === 'menu'
  // Pedido del dueño: repetir abajo los platos sueltos (entradas, segundos…)
  // confundía — el cliente pide "un menú" y lo edita. Los platos sueltos se
  // venden en caja; el interruptor vive en Admin → Configuración.
  const categoriasConPlatos = soloMenus
    ? []
    : ['entrada', 'fondo', 'bebida', 'postre'].filter((c) => platos.some((p) => p.categoria === c))

  const marcarTactil = (plato: Plato, delta: number) => {
    usoTactil.current = true
    carrito.cambiarCantidad(plato, delta)
  }

  return (
    <div className="pantalla pantalla-menu">
      <div className="cabecera-menu">
        <button
          className="boton-cancelar-todo"
          onClick={() => setConfirmandoCancelarTodo(true)}
        >
          ← Cancelar todo
        </button>
        <h1>Menú de hoy</h1>
        {config?.voz_disponible && (
          <button className="boton-pedir-voz" onClick={() => setVozAbierta(true)}>
            🎤 PEDIR POR VOZ
          </button>
        )}
      </div>

      <div className="contenido-menu">
        {(soloMenus ? menusHoy.length === 0 : platos.length === 0 && menusHoy.length === 0) && (
          <p className="menu-vacio">Todavía no hay menú cargado. Pregunta en caja, por favor.</p>
        )}
        {menusHoy.length > 0 && (
          <section>
            <h2 className="titulo-categoria">Menús</h2>
            <div className="combo-lista">
              {menusHoy.map((m) => (
                <TarjetaOfertaMenu
                  key={m.id}
                  menu={m}
                  etiqueta={menuRecien === m.id ? '✔ ¡Agregado! Toca para otro' : `🍽 UN MENÚ — ${soles(m.precio)}`}
                  enPedido={menusEnPedido(carrito.menus, m.id)}
                  onAgregar={() => { usoTactil.current = true; carrito.agregarMenuCompleto(m); setMenuRecien(m.id) }}
                />
              ))}
            </div>
          </section>
        )}
        {categoriasConPlatos.map((cat) => (
          <section key={cat}>
            <h2 className="titulo-categoria">{NOMBRE_CATEGORIA[cat] ?? cat}</h2>
            <div className="grilla-platos">
              {platos
                .filter((p) => p.categoria === cat)
                .map((p) => (
                  <TarjetaPlato
                    key={p.id}
                    plato={p}
                    cantidad={carrito.cantidadDe(p.id)}
                    onCambiar={(delta) => marcarTactil(p, delta)}
                  />
                ))}
            </div>
          </section>
        ))}
      </div>

      <BarraCarrito
        totalItems={carrito.totalItems}
        totalSoles={totalConCargos}
        onVerPedido={() => setPantalla('resumen')}
      />

      {confirmandoCancelarTodo && (
        <ModalCancelarTodo
          onSeguir={() => setConfirmandoCancelarTodo(false)}
          onCancelar={() => volverAlInicio()}
        />
      )}


      {vozAbierta && (
        <PedidoPorVoz
          platos={platos}
          menus={menusHoy}
          gaseosasLista={gaseosas}
          onContinuar={(items, menus, extras) => {
            agregarItemsVoz(items, menus, extras)
            setVozAbierta(false)
            setPantalla('resumen')
          }}
          onUsarBotones={(items, menus, extras) => {
            agregarItemsVoz(items, menus, extras)
            setVozAbierta(false)
          }}
          onDirecto={carritoVirgen ? vozDirecta : undefined}
          onCerrar={() => setVozAbierta(false)}
        />
      )}

      <AvisoInactividad {...inactividad} />
    </div>
  )
}

function AvisoInactividad({
  avisoVisible,
  segundosRestantes,
  seguirAqui,
}: {
  avisoVisible: boolean
  segundosRestantes: number
  seguirAqui: () => void
}) {
  if (!avisoVisible) return null
  return (
    <div className="modal-fondo">
      <div className="modal">
        <h2>¿Sigues ahí?</h2>
        <p className="texto-countdown">Tu pedido se borrará en {segundosRestantes} segundos.</p>
        <button className="boton-grande boton-primario" onClick={seguirAqui}>
          ¡Sí, sigo aquí!
        </button>
      </div>
    </div>
  )
}
