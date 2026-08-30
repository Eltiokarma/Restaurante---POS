import { useCallback, useEffect, useState } from 'react'
import { api, NOMBRE_EMPAQUE, NOMBRE_SERVICIO } from '../api'
import type { EstadoItem, ImpresionPendiente, OrdenOut } from '../api'
import { AvisoImpresion } from '../components/AvisoImpresion'
import { IconoProhibido, IconoReloj, IconoSarten, IconoSilla } from '../components/Iconos'

const SIGUIENTE_ESTADO: Record<string, string> = {
  pendiente: 'preparando',
  preparando: 'listo',
  listo: 'entregado',
}

const TEXTO_AVANCE: Record<string, string> = {
  pendiente: '▶ Empezar a preparar',
  preparando: '✔ Marcar listo',
  listo: '📤 Entregado',
}

// Un ítem "por salir" es el que aún no está listo
const RANGO_ESTADO: Record<EstadoItem, number> = {
  pendiente: 0, preparando: 1, listo: 2, entregado: 3,
}

// Formatea el tiempo de espera como temporizador: "4:37" o "1 h 12 m"
function formatearEspera(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos))
  if (s >= 3600) return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} m`
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function Cocina() {
  const [ordenes, setOrdenes] = useState<OrdenOut[]>([])
  const [impresion, setImpresion] = useState<ImpresionPendiente | undefined>()
  const [error, setError] = useState(false)
  // Ventana de la tanda (minutos): resalta lo que va junto en el bulk
  const [ventanaMin, setVentanaMin] = useState(0)
  // Momento del último dato del servidor: el temporizador avanza en vivo
  // sumando el tiempo local transcurrido desde entonces
  const [traidoEn, setTraidoEn] = useState(Date.now())
  const [, setTick] = useState(0)

  const cargar = useCallback(async () => {
    try {
      const data = await api.ordenesHoy()
      setOrdenes(data.ordenes)
      setImpresion(data.impresion_pendiente)
      setTraidoEn(Date.now())
      setError(false)
    } catch {
      setError(true)
    }
  }, [])

  // Polling simple cada 10 segundos (sin WebSockets en esta fase)
  useEffect(() => {
    cargar()
    api.config().then((c) => setVentanaMin(c.cocina_bulk_min)).catch(() => {})
    const intervalo = window.setInterval(cargar, 10_000)
    return () => window.clearInterval(intervalo)
  }, [cargar])

  // Tic de 1 segundo para que los temporizadores corran entre polls
  useEffect(() => {
    const intervalo = window.setInterval(() => setTick((t) => t + 1), 1_000)
    return () => window.clearInterval(intervalo)
  }, [])

  const esperaSegundos = (orden: OrdenOut) =>
    orden.minutos_espera * 60 + (Date.now() - traidoEn) / 1000

  // Selección múltiple: la cocina despacha por tandas de 2-3 pedidos
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set())

  const alternarSeleccion = (id: number) => {
    setSeleccion((prev) => {
      const nueva = new Set(prev)
      if (nueva.has(id)) nueva.delete(id)
      else nueva.add(id)
      return nueva
    })
  }

  const avanzarSeleccionadas = async () => {
    const elegidas = ordenes.filter((o) => seleccion.has(o.id) && SIGUIENTE_ESTADO[o.estado])
    // Optimista: todas avanzan a su siguiente estado de una vez
    setOrdenes((prev) =>
      prev.map((o) =>
        seleccion.has(o.id) && SIGUIENTE_ESTADO[o.estado]
          ? { ...o, estado: SIGUIENTE_ESTADO[o.estado] }
          : o,
      ),
    )
    setSeleccion(new Set())
    await Promise.allSettled(
      elegidas.map((o) => api.cambiarEstado(o.id, SIGUIENTE_ESTADO[o.estado])),
    )
    cargar()
  }

  const avanzar = async (orden: OrdenOut) => {
    const siguiente = SIGUIENTE_ESTADO[orden.estado]
    if (!siguiente) return
    // Optimista: la cocina no debe esperar al servidor para ver el cambio
    setOrdenes((prev) => prev.map((o) => (o.id === orden.id ? { ...o, estado: siguiente } : o)))
    try {
      await api.cambiarEstado(orden.id, siguiente)
    } catch {
      cargar()
    }
    cargar()
  }

  // Entregadas y anuladas desaparecen de la vista (quedan en BD)
  const activas = ordenes.filter((o) => o.estado !== 'entregado' && o.estado !== 'anulada')

  // Cintillo de anulada (§4): una orden recién anulada se queda 60 s en
  // pantalla con "NO PREPARAR", para que la cocina no la siga cocinando.
  // El reloj corre con los segundos del servidor + lo transcurrido local.
  const anuladasRecientes = ordenes.filter(
    (o) =>
      o.estado === 'anulada' &&
      o.anulada_hace_seg !== null &&
      o.anulada_hace_seg + (Date.now() - traidoEn) / 1000 < 60,
  )

  // ---------- "Por salir": tachar bulks (§3) ----------

  // Total por plato de lo que AÚN NO ESTÁ LISTO, con desglose por empaque
  // y la "tanda": las porciones de la orden más antigua de ese plato más
  // los pedidos que llegaron en los siguientes X minutos (configurable).
  const porSalir = new Map<string, {
    total: number
    // Solo las porciones sin empezar: son las únicas que pueden pasar a
    // "en preparación" (el backend nunca retrocede un estado)
    pendientes: number
    tanda: number
    empaques: Map<string, number>
    esperaMax: number
  }>()
  for (const o of activas) {
    const lineas = [...o.items, ...o.menus.flatMap((m) => m.items)]
    const espera = esperaSegundos(o)
    for (const item of lineas) {
      if (RANGO_ESTADO[item.estado] >= RANGO_ESTADO.listo) continue
      const acumulado = porSalir.get(item.nombre) ??
        { total: 0, pendientes: 0, tanda: 0, empaques: new Map(), esperaMax: espera }
      acumulado.total += item.cantidad
      if (item.estado === 'pendiente') acumulado.pendientes += item.cantidad
      // Las órdenes vienen ordenadas de la más antigua a la más nueva:
      // la primera aparición fija el inicio de la tanda de este plato
      if (ventanaMin > 0 && espera >= acumulado.esperaMax - ventanaMin * 60) {
        acumulado.tanda += item.cantidad
      }
      acumulado.empaques.set(item.empaque, (acumulado.empaques.get(item.empaque) ?? 0) + item.cantidad)
      porSalir.set(item.nombre, acumulado)
    }
  }

  // Panel de despacho: plato elegido de la tira y cuántas porciones tachar
  const [bulk, setBulk] = useState<{ nombre: string; cantidad: number } | null>(null)
  const [bulkError, setBulkError] = useState('')
  const [despachando, setDespachando] = useState(false)

  const abrirBulk = (nombre: string) => {
    const info = porSalir.get(nombre)
    if (!info) return
    setBulkError('')
    setBulk({ nombre, cantidad: ventanaMin > 0 && info.tanda > 0 ? info.tanda : info.total })
  }

  const despacharBulk = async (destino: EstadoItem) => {
    if (!bulk || despachando) return
    setDespachando(true)
    setBulkError('')
    try {
      const r = await api.despacharBulk(
        [{ plato_nombre: bulk.nombre, cantidad: bulk.cantidad }], destino,
      )
      // Refresco inmediato con las órdenes que cambiaron, sin esperar el poll
      setOrdenes((prev) =>
        prev.map((o) => r.ordenes.find((n) => n.id === o.id) ?? o),
      )
      setBulk(null)
    } catch (e) {
      setBulkError(e instanceof Error ? e.message : 'No se pudo despachar, intenta de nuevo')
      cargar()
    } finally {
      setDespachando(false)
    }
  }

  const claseItem = (estado: EstadoItem) =>
    RANGO_ESTADO[estado] >= RANGO_ESTADO.listo
      ? 'item-tachado'
      : estado === 'preparando'
        ? 'item-preparando'
        : ''

  const seleccionadasAvanzables = activas.filter(
    (o) => seleccion.has(o.id) && SIGUIENTE_ESTADO[o.estado],
  ).length

  return (
    <div className="pantalla-cocina">
      <header className="cocina-cabecera">
        <h1><IconoSarten tam={30} /> Cocina</h1>
        <span className="cocina-contador">{activas.length} órdenes activas</span>
        {error && <span className="banner-error">Sin conexión con el sistema</span>}
      </header>

      <AvisoImpresion estado={impresion} />

      {porSalir.size > 0 && (
        <div className="cocina-resumen-cola">
          <span className="cocina-resumen-titulo">Por salir:</span>
          {[...porSalir.entries()]
            .sort((a, b) => b[1].total - a[1].total)
            .map(([nombre, info]) => (
              <button
                key={nombre}
                className="cocina-resumen-item bulk-tachable"
                onClick={() => abrirBulk(nombre)}
                title="Toca para tachar porciones de este plato"
              >
                <strong>{info.total}×</strong> {nombre}
                {ventanaMin > 0 && info.tanda < info.total && (
                  <span className="bulk-tanda">tanda: {info.tanda}</span>
                )}
                {(info.empaques.size > 1 || !info.empaques.has('mesa')) && (
                  <span className="cocina-resumen-empaques">
                    {' '}({[...info.empaques.entries()].map(([e, n]) => `${n} ${e}`).join(' · ')})
                  </span>
                )}
              </button>
            ))}
        </div>
      )}

      {activas.length === 0 && anuladasRecientes.length === 0 && !error && (
        <p className="cocina-vacia">Sin órdenes pendientes 🎉</p>
      )}

      <div className="grilla-cocina">
        {anuladasRecientes.map((orden) => (
          <div key={`anulada-${orden.id}`} className="tarjeta-orden tarjeta-anulada">
            <div className="cintillo-anulada">
              <IconoProhibido tam={22} /> ANULADA — NO PREPARAR
            </div>
            <div className="tarjeta-orden-cabecera">
              <span className="tarjeta-orden-numero">
                #{String(orden.numero_orden_dia).padStart(3, '0')}
              </span>
              <span className="tarjeta-orden-hora">pedido a las {orden.hora.slice(0, 5)}</span>
            </div>
            <ul className="tarjeta-orden-items">
              {orden.menus.map((menu, m) => (
                <li key={`menu-${m}`} className="item-tachado">
                  <strong>{menu.cantidad} ×</strong> {menu.nombre}
                </li>
              ))}
              {orden.items.map((item, i) => (
                <li key={i} className="item-tachado">
                  <strong>{item.cantidad} ×</strong> {item.nombre}
                </li>
              ))}
            </ul>
          </div>
        ))}
        {activas.map((orden) => {
          const segundos = esperaSegundos(orden)
          const urgente = orden.estado === 'pendiente' && segundos > 600
          const seleccionada = seleccion.has(orden.id)
          return (
            <div
              key={orden.id}
              className={`tarjeta-orden estado-${orden.estado} ${urgente ? 'urgente' : ''} ${seleccionada ? 'seleccionada' : ''}`}
            >
              <div className="tarjeta-orden-cabecera">
                <button
                  className={`boton-seleccion ${seleccionada ? 'marcada' : ''}`}
                  onClick={() => alternarSeleccion(orden.id)}
                  aria-label={`Seleccionar orden ${orden.numero_orden_dia}`}
                >
                  {seleccionada ? '☑' : '☐'}
                </button>
                <span className="tarjeta-orden-numero">#{String(orden.numero_orden_dia).padStart(3, '0')}</span>
                <span className={`tarjeta-orden-timer ${urgente ? 'timer-urgente' : ''}`}>
                  <IconoReloj tam={18} /> {formatearEspera(segundos)}
                </span>
              </div>
              <div className="tarjeta-orden-fila-estado">
                <span className={`etiqueta-estado etiqueta-${orden.estado}`}>{orden.estado.toUpperCase()}</span>
                {orden.tipo_servicio !== 'sala' && (
                  <span className="badge-servicio badge-servicio-cocina">
                    {NOMBRE_SERVICIO[orden.tipo_servicio]}
                  </span>
                )}
                {orden.mesas.length > 0 && !orden.mesa_liberada && (
                  <span className="badge-mesa badge-servicio-cocina">
                    <IconoSilla tam={16} /> {orden.mesas.join(' + ')}
                  </span>
                )}
                {orden.items.length + orden.menus.length >= 2 || orden.menus.length > 0 ? (
                  <span className="badge-servicio badge-servicio-cocina">
                    {orden.entrega === 'separado' ? '⏱ POR TIEMPOS' : '🍽 TODO JUNTO'}
                  </span>
                ) : null}
                <span className="tarjeta-orden-hora">pedido a las {orden.hora.slice(0, 5)}</span>
              </div>
              <ul className="tarjeta-orden-items">
                {orden.menus.map((menu, m) => (
                  <li key={`menu-${m}`} className="item-menu-bloque">
                    <span className="item-menu-titulo">
                      <strong>{menu.cantidad} ×</strong> {menu.nombre}
                    </span>
                    <ul>
                      {menu.items.map((item, i) => (
                        <li key={i} className={claseItem(item.estado)}>
                          {item.cantidad} × {item.nombre}
                          {item.es_extra && <span className="item-extra-tag">extra</span>}
                          {item.empaque !== 'mesa' && (
                            <span className="item-empaque">{NOMBRE_EMPAQUE[item.empaque]}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                    {menu.nota && <div className="nota-cocina">⚠ {menu.nota}</div>}
                  </li>
                ))}
                {orden.items.map((item, i) => (
                  <li key={i} className={claseItem(item.estado)}>
                    <strong>{item.cantidad} ×</strong> {item.nombre}
                    {item.empaque !== 'mesa' && (
                      <span className="item-empaque">{NOMBRE_EMPAQUE[item.empaque]}</span>
                    )}
                    {item.nota && <div className="nota-cocina">⚠ {item.nota}</div>}
                  </li>
                ))}
              </ul>
              <button className="boton-grande boton-avance" onClick={() => avanzar(orden)}>
                {TEXTO_AVANCE[orden.estado]}
              </button>
            </div>
          )
        })}
      </div>

      {seleccion.size > 0 && (
        <div className="barra-tanda">
          <span>{seleccion.size} seleccionada{seleccion.size > 1 ? 's' : ''}</span>
          <button
            className="boton-grande boton-avance-tanda"
            disabled={seleccionadasAvanzables === 0}
            onClick={avanzarSeleccionadas}
          >
            ▶▶ Avanzar la tanda ({seleccionadasAvanzables})
          </button>
          <button className="boton-grande boton-cancelar-tanda" onClick={() => setSeleccion(new Set())}>
            Deseleccionar
          </button>
        </div>
      )}

      {bulk && (
        <div className="modal-fondo" onClick={() => setBulk(null)}>
          <div className="modal modal-bulk" onClick={(e) => e.stopPropagation()}>
            <h2>{bulk.nombre}</h2>
            <p className="bulk-detalle">
              Quedan <strong>{porSalir.get(bulk.nombre)?.total ?? 0}</strong> porciones por salir
              {(porSalir.get(bulk.nombre)?.pendientes ?? 0) < (porSalir.get(bulk.nombre)?.total ?? 0) && (
                <> (<strong>{porSalir.get(bulk.nombre)?.pendientes}</strong> sin empezar, el resto
                ya en preparación)</>
              )}. Se tachan de la orden más antigua a la más nueva.
              {ventanaMin > 0 && (porSalir.get(bulk.nombre)?.tanda ?? 0) < (porSalir.get(bulk.nombre)?.total ?? 0) && (
                <> La tanda de ahora (pedidos con hasta {ventanaMin} min de diferencia) es de{' '}
                <strong>{porSalir.get(bulk.nombre)?.tanda}</strong>.</>
              )}
            </p>
            {bulkError && <div className="banner-error">{bulkError}</div>}
            <div className="armado-cantidad bulk-cantidad">
              <button
                className="boton-cantidad"
                onClick={() => setBulk((b) => b && { ...b, cantidad: Math.max(1, b.cantidad - 1) })}
                disabled={bulk.cantidad <= 1}
                aria-label="Una porción menos"
              >−</button>
              <strong>{bulk.cantidad}</strong>
              <button
                className="boton-cantidad boton-mas"
                onClick={() =>
                  setBulk((b) => b && {
                    ...b,
                    cantidad: Math.min(porSalir.get(b.nombre)?.total ?? b.cantidad, b.cantidad + 1),
                  })
                }
                disabled={bulk.cantidad >= (porSalir.get(bulk.nombre)?.total ?? 0)}
                aria-label="Una porción más"
              >+</button>
            </div>
            <div className="modal-botones">
              <button
                className="boton-grande boton-secundario"
                disabled={despachando || bulk.cantidad > (porSalir.get(bulk.nombre)?.pendientes ?? 0)}
                title={
                  bulk.cantidad > (porSalir.get(bulk.nombre)?.pendientes ?? 0)
                    ? `Solo ${porSalir.get(bulk.nombre)?.pendientes ?? 0} sin empezar: el resto ya está en preparación`
                    : undefined
                }
                onClick={() => despacharBulk('preparando')}
              >
                ▶ En preparación
              </button>
              <button
                className="boton-grande boton-confirmar"
                disabled={despachando}
                onClick={() => despacharBulk('listo')}
              >
                {despachando ? 'Tachando…' : `✔ Listos (${bulk.cantidad})`}
              </button>
            </div>
            <button className="boton-grande boton-cancelar-tanda" onClick={() => setBulk(null)}>
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
