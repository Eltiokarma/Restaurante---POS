import { useCallback, useEffect, useState } from 'react'
import { api, NOMBRE_SERVICIO } from '../api'
import type { OrdenOut } from '../api'

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

// Formatea el tiempo de espera como temporizador: "4:37" o "1 h 12 m"
function formatearEspera(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos))
  if (s >= 3600) return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} m`
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function Cocina() {
  const [ordenes, setOrdenes] = useState<OrdenOut[]>([])
  const [error, setError] = useState(false)
  // Momento del último dato del servidor: el temporizador avanza en vivo
  // sumando el tiempo local transcurrido desde entonces
  const [traidoEn, setTraidoEn] = useState(Date.now())
  const [, setTick] = useState(0)

  const cargar = useCallback(async () => {
    try {
      const data = await api.ordenesHoy()
      setOrdenes(data.ordenes)
      setTraidoEn(Date.now())
      setError(false)
    } catch {
      setError(true)
    }
  }, [])

  // Polling simple cada 10 segundos (sin WebSockets en esta fase)
  useEffect(() => {
    cargar()
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
  }

  // Entregadas y anuladas desaparecen de la vista (quedan en BD)
  const activas = ordenes.filter((o) => o.estado !== 'entregado' && o.estado !== 'anulada')

  // Resumen para cocinar por tandas: total por plato de lo que falta salir
  const porSalir = new Map<string, number>()
  for (const o of activas) {
    if (o.estado === 'entregado') continue
    for (const item of o.items) {
      porSalir.set(item.nombre, (porSalir.get(item.nombre) ?? 0) + item.cantidad)
    }
  }
  const seleccionadasAvanzables = activas.filter(
    (o) => seleccion.has(o.id) && SIGUIENTE_ESTADO[o.estado],
  ).length

  return (
    <div className="pantalla-cocina">
      <header className="cocina-cabecera">
        <h1>🍳 Cocina</h1>
        <span className="cocina-contador">{activas.length} órdenes activas</span>
        {error && <span className="banner-error">Sin conexión con el sistema</span>}
      </header>

      {porSalir.size > 0 && (
        <div className="cocina-resumen-cola">
          <span className="cocina-resumen-titulo">Por salir:</span>
          {[...porSalir.entries()]
            .sort((a, b) => b[1] - a[1])
            .map(([nombre, cantidad]) => (
              <span key={nombre} className="cocina-resumen-item">
                <strong>{cantidad}×</strong> {nombre}
              </span>
            ))}
        </div>
      )}

      {activas.length === 0 && !error && <p className="cocina-vacia">Sin órdenes pendientes 🎉</p>}

      <div className="grilla-cocina">
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
                  ⏱ {formatearEspera(segundos)}
                </span>
              </div>
              <div className="tarjeta-orden-fila-estado">
                <span className={`etiqueta-estado etiqueta-${orden.estado}`}>{orden.estado.toUpperCase()}</span>
                {orden.tipo_servicio !== 'sala' && (
                  <span className="badge-servicio badge-servicio-cocina">
                    {NOMBRE_SERVICIO[orden.tipo_servicio]}
                  </span>
                )}
                <span className="tarjeta-orden-hora">pedido a las {orden.hora.slice(0, 5)}</span>
              </div>
              <ul className="tarjeta-orden-items">
                {orden.items.map((item, i) => (
                  <li key={i}>
                    <strong>{item.cantidad} ×</strong> {item.nombre}
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
    </div>
  )
}
