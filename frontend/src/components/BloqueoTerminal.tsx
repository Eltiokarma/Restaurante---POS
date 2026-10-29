import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api, ApiError } from '../api'

// Un minuto sin tocar la pantalla bloquea la terminal (pedido del dueño)
const BLOQUEO_SEG = 60
const CLAVE_BLOQUEADA = 'pos_terminal_bloqueada'
const TECLAS = ['1', '2', '3', '4', '5', '6', '7', '8', '9']

function leerBloqueada(): boolean {
  try {
    return localStorage.getItem(CLAVE_BLOQUEADA) === '1'
  } catch {
    return false
  }
}

function guardarBloqueada(valor: boolean) {
  try {
    if (valor) localStorage.setItem(CLAVE_BLOQUEADA, '1')
    else localStorage.removeItem(CLAVE_BLOQUEADA)
  } catch {
    /* sin almacenamiento: el bloqueo vale mientras la página siga abierta */
  }
}

/**
 * Candado de la terminal de pedidos: la usa solo el personal, así que al
 * apagarse la pantalla de la tablet o tras un minuto sin tocarla pide el
 * PIN del cajón (el mismo de "💵 Abrir cajón"). El pedido a medio armar no
 * se pierde: la pantalla sigue montada debajo. Sin PIN del cajón
 * configurado no se bloquea nunca.
 */
export function BloqueoTerminal({ children }: { children: ReactNode }) {
  const [conPin, setConPin] = useState(false)
  const [bloqueada, setBloqueadaEstado] = useState(leerBloqueada)
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [verificando, setVerificando] = useState(false)
  const ultimaActividad = useRef(Date.now())

  const setBloqueada = useCallback((valor: boolean) => {
    guardarBloqueada(valor)
    setBloqueadaEstado(valor)
  }, [])

  // Si el admin pone o quita el PIN, la terminal se entera sola
  useEffect(() => {
    const cargar = () => api.config().then((c) => setConPin(!!c.gaveta_con_pin)).catch(() => {})
    cargar()
    const intervalo = window.setInterval(cargar, 30_000)
    return () => window.clearInterval(intervalo)
  }, [])

  useEffect(() => {
    if (!conPin) return
    ultimaActividad.current = Date.now()
    const registrar = () => { ultimaActividad.current = Date.now() }
    // Pantalla apagada (o la tablet cambió de app): al volver pide el PIN
    const alOcultar = () => { if (document.visibilityState === 'hidden') setBloqueada(true) }
    const eventos: (keyof WindowEventMap)[] = ['pointerdown', 'touchstart', 'keydown']
    eventos.forEach((e) => window.addEventListener(e, registrar))
    document.addEventListener('visibilitychange', alOcultar)
    // Con la pantalla apagada los timers se congelan: al despertar, la
    // diferencia de reloj igual lo detecta
    const intervalo = window.setInterval(() => {
      if (Date.now() - ultimaActividad.current >= BLOQUEO_SEG * 1000) setBloqueada(true)
    }, 1_000)
    return () => {
      eventos.forEach((e) => window.removeEventListener(e, registrar))
      document.removeEventListener('visibilitychange', alOcultar)
      window.clearInterval(intervalo)
    }
  }, [conPin, setBloqueada])

  const verificar = async (valor: string) => {
    if (verificando || valor.length < 4) return
    setVerificando(true)
    try {
      await api.desbloquearTerminal(valor)
      setBloqueada(false)
      setPin('')
      setError('')
      ultimaActividad.current = Date.now()
    } catch (e) {
      setPin('')
      setError(e instanceof ApiError && e.status === 403 ? 'PIN incorrecto' : 'Sin conexión, intenta de nuevo')
    } finally {
      setVerificando(false)
    }
  }

  const tocar = (digito: string) => {
    setError('')
    setPin((p) => (p.length < 8 ? p + digito : p))
  }

  return (
    <>
      {children}
      {conPin && bloqueada && (
        <div className="bloqueo-terminal" role="dialog" aria-modal="true" aria-label="Terminal bloqueada">
          <form
            className="bloqueo-terminal-caja"
            onSubmit={(e) => { e.preventDefault(); verificar(pin) }}
          >
            <h1>🔒 Terminal bloqueada</h1>
            <p>Ingresa el PIN del cajón para seguir</p>
            <div className="bloqueo-terminal-pin" aria-live="polite">
              {pin ? '●'.repeat(pin.length) : <span className="bloqueo-terminal-vacio">PIN</span>}
            </div>
            {error && <p className="bloqueo-terminal-error">{error}</p>}
            <div className="bloqueo-terminal-teclado">
              {TECLAS.map((t) => (
                <button key={t} type="button" onClick={() => tocar(t)}>{t}</button>
              ))}
              <button type="button" aria-label="Borrar" onClick={() => { setError(''); setPin((p) => p.slice(0, -1)) }}>⌫</button>
              <button type="button" onClick={() => tocar('0')}>0</button>
              <button type="submit" className="bloqueo-terminal-ok" disabled={pin.length < 4 || verificando}>
                {verificando ? '…' : 'OK'}
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  )
}
