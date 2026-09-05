import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, EMPAQUES, NOMBRE_CATEGORIA, NOMBRE_EMPAQUE, NOMBRE_ENTREGA, precioUnitarioMenu, soles, unidadesEnTaper } from '../api'
import type { ConfigOut, DatosLocal, Entrega, MenuHoy, MesaEstado, OrdenOut, Plato, VozItemResuelto } from '../api'
import { describirMenu } from '../components/ArmadoMenu'
import { TarjetaMenuCarrito } from '../components/TarjetaMenuCarrito'
import { SugerenciaMenu } from '../components/SugerenciaMenu'
import { BarraCarrito } from '../components/BarraCarrito'
import { CountdownCancel } from '../components/CountdownCancel'
import { PedidoPorVoz } from '../components/PedidoPorVoz'
import { TarjetaPlato } from '../components/TarjetaPlato'
import { Ticket } from '../components/Ticket'
import { useCarrito } from '../hooks/useCarrito'
import { useInactividad } from '../hooks/useInactividad'

// La tarjeta que ofrece el menú del día (pantalla única y pantalla de carta)
function TarjetaOfertaMenu({ menu, etiqueta, onAgregar }: {
  menu: MenuHoy
  etiqueta: string
  onAgregar: () => void
}) {
  return (
    <div className="combo">
      <div className="combo-cabecera">
        <span className="combo-titulo">{menu.nombre}</span>
        <span className="combo-precio">{soles(menu.precio)}</span>
      </div>
      <div className="combo-resumen-tiempos">
        {menu.tiempos.map((t) => (
          <div key={t.orden}>
            <strong>{t.rotulo}:</strong>{' '}
            {t.alternativas.length === 1
              ? `${t.alternativas[0].nombre} (incluido)`
              : t.alternativas.map((a) => a.nombre).join(' / ')}
          </div>
        ))}
      </div>
      <button className="boton-armar" onClick={onAgregar}>
        {etiqueta}
      </button>
    </div>
  )
}

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

type Pantalla = 'inicio' | 'menu' | 'resumen' | 'countdown' | 'final'

export function Cliente() {
  const [pantalla, setPantalla] = useState<Pantalla>('inicio')
  const [platos, setPlatos] = useState<Plato[]>([])
  const [menusHoy, setMenusHoy] = useState<MenuHoy[]>([])
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
  const [vozAbierta, setVozAbierta] = useState(false)
  const [entrega, setEntrega] = useState<Entrega>('junto')
  // Mesa elegida al tomar el pedido (opcional): si no eligen, el ticket
  // sale "SIN MESA" y en caja la asignan después
  const [mesas, setMesas] = useState<MesaEstado[]>([])
  const [mesasElegidas, setMesasElegidas] = useState<number[]>([])
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
    if (pantalla !== 'menu' && pantalla !== 'resumen') return
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
      setEntrega('junto')
      setMesasElegidas([])
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
  const tapers = unidadesEnTaper(carrito.items, carrito.menus)
  const cargoTaper = precioTaper * tapers
  const totalConCargos = carrito.totalSoles + cargoTaper
  // Mientras el carrito tenga menús, la pantalla única no cambia de forma
  // aunque el menú del día se agote a mitad de pedido
  const soloMenus = soloMenusConfig && (menusHoy.length > 0 || carrito.menus.length > 0)

  // La voz solo SUMA items al carrito; todo lo demás es el flujo de siempre
  const agregarItemsVoz = (items: VozItemResuelto[]) => {
    for (const item of items) {
      const plato = platos.find((p) => p.id === item.plato_id)
      if (plato) carrito.cambiarCantidad(plato, item.cantidad)
    }
    if (items.length > 0) usoVoz.current = true
  }

  const empezarPedido = async () => {
    setMensajeInicio('')
    inicioPedidoTs.current = Date.now()
    // Se espera el menú fresco: así la primera pantalla se decide con datos
    // reales aunque la tablet recién cargue la página
    const menus = (await cargarMenu()) ?? menusHoy
    setPantalla(soloMenusConfig && menus.length > 0 ? 'resumen' : 'menu')
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

  // Un plato "al momento" (bistec frito) obliga a entrega separada — también
  // si es la alternativa elegida (o un extra) dentro de un menú
  const platoAlMomentoDe = (m: (typeof carrito.menus)[number]) =>
    m.menu.tiempos
      .flatMap((t) => t.alternativas)
      .find(
        (a) =>
          a.sale_al_momento &&
          (Object.values(m.elecciones).includes(a.plato_id) ||
            m.extras.some((e) => e.plato_id === a.plato_id)),
      )
  const alMomentoEnMenus = carrito.menus.map(platoAlMomentoDe).find(Boolean)
  const alMomentoEnItems = carrito.items.find((i) => i.plato.sale_al_momento)
  const nombreAlMomento = alMomentoEnItems?.plato.nombre ?? alMomentoEnMenus?.nombre
  const hayAlMomento = nombreAlMomento !== undefined
  const entregaEfectiva: Entrega = hayAlMomento ? 'separado' : entrega

  const guardandoRef = useRef(false)
  const confirmarDefinitivo = async () => {
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
        carrito.menus.map((m) => ({
          menu_id: m.menu.id, cantidad: m.cantidad, elecciones: m.elecciones,
          extras: m.extras, omitidos: m.omitidos, empaques: m.empaques,
          agregados: m.agregados.map((a) => ({ agregado_id: a.agregado.id, cantidad: a.cantidad })),
          empaque: m.empaque, nota: m.nota.trim(),
        })),
      )
      setOrdenFinal(resultado)
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

  // Pantalla final: volver al inicio a los 10 segundos
  useEffect(() => {
    if (pantalla !== 'final') return
    const timer = window.setTimeout(() => {
      setOrdenFinal(null)
      volverAlInicio()
    }, 10_000)
    return () => window.clearTimeout(timer)
  }, [pantalla, volverAlInicio])

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
      </div>
    )
  }

  if (pantalla === 'final' && ordenFinal) {
    return (
      <div className="pantalla pantalla-final" onClick={() => { setOrdenFinal(null); volverAlInicio() }}>
        <div className="numero-orden-gigante">
          ORDEN #{String(ordenFinal.orden.numero_orden_dia).padStart(3, '0')}
        </div>
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
        <p className="texto-toca">Volviendo al inicio…</p>
        <Ticket orden={ordenFinal.orden} local={ordenFinal.local} />
      </div>
    )
  }

  if (pantalla === 'countdown') {
    return (
      <div className="pantalla pantalla-countdown">
        <h1>¿Estás seguro?</h1>
        <p className="texto-countdown">Tienes {config?.ventana_cancelacion_seg ?? 30} segundos para cancelar.</p>
        <CountdownCancel
          duracionSeg={config?.ventana_cancelacion_seg ?? 30}
          onTerminado={confirmarDefinitivo}
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
        <button className="boton-grande boton-secundario" onClick={confirmarDefinitivo} disabled={guardando}>
          {guardando ? 'Guardando…' : 'Confirmar ahora (saltar espera)'}
        </button>
      </div>
    )
  }

  if (pantalla === 'resumen') {
    return (
      <div className="pantalla pantalla-resumen">
        {soloMenus ? (
          <div className="cabecera-menu cabecera-en-pedido">
            <button className="boton-cancelar-todo" onClick={() => setConfirmandoCancelarTodo(true)}>
              ← Cancelar todo
            </button>
            <h1>Tu pedido</h1>
            {config?.voz_disponible && (
              <button className="boton-pedir-voz" onClick={() => setVozAbierta(true)}>
                🎤 PEDIR POR VOZ
              </button>
            )}
          </div>
        ) : (
          <h1>Tu pedido</h1>
        )}
        {errorConexion && <div className="banner-error">{errorConexion}</div>}
        {soloMenus && (
          <div className="oferta-menus">
            {menusHoy.map((m) => (
              <TarjetaOfertaMenu
                key={m.id}
                menu={m}
                etiqueta={`➕ UN MENÚ — ${soles(m.precio)}`}
                onAgregar={() => { usoTactil.current = true; carrito.agregarMenuCompleto(m) }}
              />
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
        {carrito.totalItems > 0 && (
        <div className="selector-servicio">
          <span className="selector-servicio-titulo">¿Cómo va cada plato?</span>
          <div className="selector-servicio-botones fila-todos">
            <span className="etiqueta-todos">Todos:</span>
            {empaquesOfrecidos.map((e) => (
              <button key={e} className="boton-servicio boton-empaque" onClick={() => carrito.empaqueParaTodos(e)}>
                {NOMBRE_EMPAQUE[e]}
                {e === 'taper' && precioTaper > 0 && <small> +{soles(precioTaper)}</small>}
              </button>
            ))}
          </div>
        </div>
        )}
        <div className="lista-resumen">
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
        {carrito.totalItems > 0 && mesas.some((m) => m.activa) && (
          <div className="selector-servicio">
            <span className="selector-servicio-titulo">🪑 ¿En qué mesa van a estar?</span>
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
          </div>
        )}
        {(carrito.items.length >= 2 || carrito.menus.length > 0 || hayAlMomento) && (
          <div className="selector-servicio">
            <span className="selector-servicio-titulo">¿Cómo sale tu pedido?</span>
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
        <div className="botones-resumen">
          {!soloMenus && (
            <button className="boton-grande boton-secundario" onClick={() => setPantalla('menu')}>
              ← Modificar
            </button>
          )}
          <button
            className="boton-grande boton-confirmar"
            disabled={carrito.totalItems === 0 || guardando}
            onClick={() => setPantalla('countdown')}
          >
            ✅ CONFIRMAR PEDIDO
          </button>
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
            onContinuar={(items) => { agregarItemsVoz(items); setVozAbierta(false) }}
            onUsarBotones={(items) => { agregarItemsVoz(items); setVozAbierta(false) }}
            onCerrar={() => setVozAbierta(false)}
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
          onContinuar={(items) => {
            agregarItemsVoz(items)
            setVozAbierta(false)
            setPantalla('resumen')
          }}
          onUsarBotones={(items) => {
            agregarItemsVoz(items)
            setVozAbierta(false)
          }}
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
