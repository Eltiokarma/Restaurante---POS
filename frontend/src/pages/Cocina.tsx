import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
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

  return (
    <div className="pantalla-cocina">
      <header className="cocina-cabecera">
        <h1>🍳 Cocina</h1>
        <span className="cocina-contador">{activas.length} órdenes activas</span>
        {error && <span className="banner-error">Sin conexión con el sistema</span>}
      </header>

      {activas.length === 0 && !error && <p className="cocina-vacia">Sin órdenes pendientes 🎉</p>}

      <div className="grilla-cocina">
        {activas.map((orden) => {
          const segundos = esperaSegundos(orden)
          const urgente = orden.estado === 'pendiente' && segundos > 600
          return (
            <div key={orden.id} className={`tarjeta-orden estado-${orden.estado} ${urgente ? 'urgente' : ''}`}>
              <div className="tarjeta-orden-cabecera">
                <span className="tarjeta-orden-numero">#{String(orden.numero_orden_dia).padStart(3, '0')}</span>
                <span className={`tarjeta-orden-timer ${urgente ? 'timer-urgente' : ''}`}>
                  ⏱ {formatearEspera(segundos)}
                </span>
              </div>
              <div className="tarjeta-orden-fila-estado">
                <span className={`etiqueta-estado etiqueta-${orden.estado}`}>{orden.estado.toUpperCase()}</span>
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
    </div>
  )
}
