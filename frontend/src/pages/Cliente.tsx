import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, NOMBRE_CATEGORIA, NOMBRE_SERVICIO, soles } from '../api'
import type { ConfigOut, DatosLocal, OrdenOut, Plato, TipoServicio } from '../api'
import { BarraCarrito } from '../components/BarraCarrito'
import { CountdownCancel } from '../components/CountdownCancel'
import { TarjetaPlato } from '../components/TarjetaPlato'
import { Ticket } from '../components/Ticket'
import { useCarrito } from '../hooks/useCarrito'
import { useInactividad } from '../hooks/useInactividad'

type Pantalla = 'inicio' | 'menu' | 'resumen' | 'countdown' | 'final'

export function Cliente() {
  const [pantalla, setPantalla] = useState<Pantalla>('inicio')
  const [platos, setPlatos] = useState<Plato[]>([])
  const [config, setConfig] = useState<ConfigOut | null>(null)
  const carrito = useCarrito()

  const [confirmandoCancelarTodo, setConfirmandoCancelarTodo] = useState(false)
  const [mensajeInicio, setMensajeInicio] = useState('')
  const [errorConexion, setErrorConexion] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [ordenFinal, setOrdenFinal] = useState<{ orden: OrdenOut; local: DatosLocal } | null>(null)
  const [tipoServicio, setTipoServicio] = useState<TipoServicio>('sala')

  const { sincronizarConMenu, vaciar } = carrito
  const cargarMenu = useCallback(async () => {
    try {
      const data = await api.menuHoy()
      setPlatos(data.platos)
      // Si el admin cambió un precio a mitad de pedido, el carrito se
      // actualiza para que el total mostrado coincida con lo que se cobra.
      sincronizarConMenu(data.platos)
    } catch {
      // Si el polling falla se mantiene el último menú conocido
    }
  }, [sincronizarConMenu])

  useEffect(() => {
    api.config().then(setConfig).catch(() => {})
    cargarMenu()
  }, [cargarMenu])

  // Si un plato se agota, el admin lo desactiva y desaparece de la terminal
  // en el siguiente refresco: polling cada 30s mientras se arma el pedido.
  useEffect(() => {
    if (pantalla !== 'menu') return
    const intervalo = window.setInterval(cargarMenu, 30_000)
    return () => window.clearInterval(intervalo)
  }, [pantalla, cargarMenu])

  const volverAlInicio = useCallback(
    (mensaje = '') => {
      vaciar()
      setConfirmandoCancelarTodo(false)
      setErrorConexion('')
      setMensajeInicio(mensaje)
      setTipoServicio('sala')
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

  const empezarPedido = () => {
    setMensajeInicio('')
    inicioPedidoTs.current = Date.now()
    cargarMenu() // refresco al iniciar un pedido nuevo
    setPantalla('menu')
  }

  const cancelarPedidoEnVentana = async () => {
    const items = carrito.items.map((i) => ({
      nombre: i.plato.nombre,
      precio: i.plato.precio,
      cantidad: i.cantidad,
    }))
    const total = carrito.totalSoles
    volverAlInicio('Pedido cancelado')
    try {
      await api.registrarCancelacion(items, total)
    } catch {
      // El log de cancelaciones es solo para análisis; si falla no
      // bloqueamos al cliente.
    }
  }

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
      const resultado = await api.crearOrden(
        carrito.items.map((i) => ({ plato_id: i.plato.id, cantidad: i.cantidad })),
        duracion,
        tipoServicio,
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
          const disponibles = new Set(menu.platos.map((p) => p.id))
          const agotados = carrito.items
            .filter((i) => !disponibles.has(i.plato.id))
            .map((i) => i.plato.nombre)
          carrito.eliminarNoDisponibles(disponibles)
          setErrorConexion(
            agotados.length > 0
              ? `Se agotó: ${agotados.join(', ')}. Lo quitamos de tu pedido; revisa y confirma de nuevo.`
              : e.message,
          )
        } catch {
          setErrorConexion(e.message)
        }
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
  // hoja en blanco. En modo "estacion" no se imprime aquí: el ticket sale
  // por la PC que tiene abierta /ticketera.
  const imprimeAqui = config?.modo_impresion !== 'estacion'
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
          {carrito.items.map((i) => (
            <div key={i.plato.id}>
              {i.cantidad} × {i.plato.nombre}
            </div>
          ))}
          <div className="resumen-breve-total">Total: {soles(carrito.totalSoles)}</div>
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
        <h1>Tu pedido</h1>
        {errorConexion && <div className="banner-error">{errorConexion}</div>}
        <div className="lista-resumen">
          {carrito.items.map((i) => (
            <div className="linea-resumen" key={i.plato.id}>
              <span>
                {i.cantidad} × {i.plato.nombre}
              </span>
              <span className="linea-resumen-precios">
                {soles(i.plato.precio)} c/u — <strong>{soles(i.plato.precio * i.cantidad)}</strong>
              </span>
            </div>
          ))}
        </div>
        <div className="total-grande">TOTAL: {soles(carrito.totalSoles)}</div>
        <div className="selector-servicio">
          <span className="selector-servicio-titulo">¿Cómo lo quieres?</span>
          <div className="selector-servicio-botones">
            {(['sala', 'llevar', 'mixto'] as TipoServicio[]).map((t) => (
              <button
                key={t}
                className={`boton-servicio ${tipoServicio === t ? 'servicio-activo' : ''}`}
                onClick={() => setTipoServicio(t)}
              >
                {NOMBRE_SERVICIO[t]}
              </button>
            ))}
          </div>
        </div>
        <div className="botones-resumen">
          <button className="boton-grande boton-secundario" onClick={() => setPantalla('menu')}>
            ← Modificar
          </button>
          <button
            className="boton-grande boton-confirmar"
            disabled={carrito.totalItems === 0 || guardando}
            onClick={() => setPantalla('countdown')}
          >
            ✅ CONFIRMAR PEDIDO
          </button>
        </div>
        <AvisoInactividad {...inactividad} />
      </div>
    )
  }

  // pantalla === 'menu'
  const categoriasConPlatos = ['entrada', 'fondo', 'bebida', 'postre'].filter((c) =>
    platos.some((p) => p.categoria === c),
  )

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
      </div>

      <div className="contenido-menu">
        {platos.length === 0 && (
          <p className="menu-vacio">Todavía no hay menú cargado. Pregunta en caja, por favor.</p>
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
                    onCambiar={(delta) => carrito.cambiarCantidad(p, delta)}
                  />
                ))}
            </div>
          </section>
        ))}
      </div>

      <BarraCarrito
        totalItems={carrito.totalItems}
        totalSoles={carrito.totalSoles}
        onVerPedido={() => setPantalla('resumen')}
      />

      {confirmandoCancelarTodo && (
        <div className="modal-fondo">
          <div className="modal">
            <h2>¿Cancelar todo el pedido?</h2>
            <div className="modal-botones">
              <button className="boton-grande boton-secundario" onClick={() => setConfirmandoCancelarTodo(false)}>
                No, seguir pidiendo
              </button>
              <button className="boton-grande boton-cancelar-rojo" onClick={() => volverAlInicio()}>
                Sí, cancelar todo
              </button>
            </div>
          </div>
        </div>
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
