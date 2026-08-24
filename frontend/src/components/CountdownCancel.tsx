import { useEffect, useRef, useState } from 'react'

interface Props {
  duracionSeg: number
  onTerminado: () => void
}

/**
 * Cuenta regresiva de la ventana de cancelación.
 *
 * Corrección de drift: el tiempo restante se calcula SIEMPRE contra el
 * timestamp de inicio (performance.now()), no acumulando ticks del
 * setInterval, que en tablets puede atrasarse.
 */
export function CountdownCancel({ duracionSeg, onTerminado }: Props) {
  const [restanteMs, setRestanteMs] = useState(duracionSeg * 1000)
  const inicio = useRef<number | null>(null)
  const terminadoRef = useRef(false)
  const onTerminadoRef = useRef(onTerminado)
  onTerminadoRef.current = onTerminado

  useEffect(() => {
    inicio.current = performance.now()
    terminadoRef.current = false
    const intervalo = window.setInterval(() => {
      const transcurrido = performance.now() - (inicio.current ?? 0)
      const restante = duracionSeg * 1000 - transcurrido
      setRestanteMs(Math.max(0, restante))
      if (restante <= 0 && !terminadoRef.current) {
        terminadoRef.current = true
        window.clearInterval(intervalo)
        onTerminadoRef.current()
      }
    }, 100)
    return () => window.clearInterval(intervalo)
  }, [duracionSeg])

  const segundos = Math.ceil(restanteMs / 1000)
  const fraccion = restanteMs / (duracionSeg * 1000)
  // verde → amarillo → rojo en los últimos 5 segundos
  const color = segundos <= 5 ? '#d32f2f' : fraccion < 0.5 ? '#f9a825' : '#2e7d32'

  return (
    <div className="countdown">
      <div className="countdown-numero" style={{ color }}>
        {segundos}
      </div>
      <div className="countdown-barra-fondo">
        <div
          className="countdown-barra"
          style={{ width: `${fraccion * 100}%`, backgroundColor: color }}
        />
      </div>
    </div>
  )
}
