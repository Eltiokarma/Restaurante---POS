import { useEffect, useRef, useState } from 'react'

/**
 * Timeout de inactividad para la terminal: si el cliente abandona a mitad
 * de pedido, tras `timeoutSeg` sin tocar la pantalla se muestra el aviso
 * "¿Sigues ahí?" con una cuenta de `avisoSeg`; si tampoco responde, se
 * llama a `onTimeout` (limpiar carrito y volver al inicio).
 */
export function useInactividad(activo: boolean, timeoutSeg: number, avisoSeg: number, onTimeout: () => void) {
  const [avisoVisible, setAvisoVisible] = useState(false)
  const [segundosRestantes, setSegundosRestantes] = useState(avisoSeg)
  const ultimaActividad = useRef(Date.now())
  const avisoDesde = useRef<number | null>(null)
  const onTimeoutRef = useRef(onTimeout)
  onTimeoutRef.current = onTimeout

  useEffect(() => {
    if (!activo) {
      setAvisoVisible(false)
      avisoDesde.current = null
      return
    }

    ultimaActividad.current = Date.now()

    const registrarActividad = () => {
      ultimaActividad.current = Date.now()
      // Un toque cualquiera durante el aviso cuenta como "sigo aquí"
      if (avisoDesde.current !== null) {
        avisoDesde.current = null
        setAvisoVisible(false)
      }
    }

    const eventos: (keyof WindowEventMap)[] = ['pointerdown', 'touchstart', 'keydown']
    eventos.forEach((e) => window.addEventListener(e, registrarActividad))

    const intervalo = window.setInterval(() => {
      const ahora = Date.now()
      if (avisoDesde.current === null) {
        if (ahora - ultimaActividad.current >= timeoutSeg * 1000) {
          avisoDesde.current = ahora
          setSegundosRestantes(avisoSeg)
          setAvisoVisible(true)
        }
      } else {
        const transcurrido = Math.floor((ahora - avisoDesde.current) / 1000)
        const restante = avisoSeg - transcurrido
        setSegundosRestantes(Math.max(0, restante))
        if (restante <= 0) {
          avisoDesde.current = null
          setAvisoVisible(false)
          onTimeoutRef.current()
        }
      }
    }, 250)

    return () => {
      eventos.forEach((e) => window.removeEventListener(e, registrarActividad))
      window.clearInterval(intervalo)
    }
  }, [activo, timeoutSeg, avisoSeg])

  const seguirAqui = () => {
    ultimaActividad.current = Date.now()
    avisoDesde.current = null
    setAvisoVisible(false)
  }

  return { avisoVisible, segundosRestantes, seguirAqui }
}
