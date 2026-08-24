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

export function Cocina() {
  const [ordenes, setOrdenes] = useState<OrdenOut[]>([])
  const [error, setError] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const data = await api.ordenesHoy()
      setOrdenes(data.ordenes)
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

  // Las entregadas desaparecen de la vista (quedan en BD); orden por antigüedad
  const activas = ordenes.filter((o) => o.estado !== 'entregado')

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
          const urgente = orden.estado === 'pendiente' && orden.minutos_espera > 10
          return (
            <div key={orden.id} className={`tarjeta-orden estado-${orden.estado} ${urgente ? 'urgente' : ''}`}>
              <div className="tarjeta-orden-cabecera">
                <span className="tarjeta-orden-numero">#{String(orden.numero_orden_dia).padStart(3, '0')}</span>
                <span className="tarjeta-orden-hora">{orden.hora.slice(0, 5)}</span>
              </div>
              <span className={`etiqueta-estado etiqueta-${orden.estado}`}>{orden.estado.toUpperCase()}</span>
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
