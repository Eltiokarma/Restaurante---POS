import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, ApiError, setPinLocal } from '../api'

/**
 * Candado para despliegues en internet (Railway): si el backend tiene
 * PIN_LOCAL definido, pide el PIN una sola vez por dispositivo y lo
 * guarda. En la LAN del local (sin PIN) no aparece nunca.
 */
export function CandadoPin({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<'verificando' | 'pedir' | 'ok'>('verificando')
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')

  const verificar = async () => {
    try {
      await api.config()
      setEstado('ok')
    } catch (e) {
      if (e instanceof ApiError && e.status === 401 && e.message.includes('PIN')) {
        setEstado('pedir')
      } else {
        // Backend caído u otro error: dejar pasar, cada página muestra el suyo
        setEstado('ok')
      }
    }
  }

  useEffect(() => {
    verificar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const entrar = async (e: React.FormEvent) => {
    e.preventDefault()
    setPinLocal(pin.trim())
    setError('')
    try {
      await api.config()
      setEstado('ok')
    } catch {
      setError('PIN incorrecto, intenta de nuevo')
    }
  }

  if (estado === 'verificando') return null
  if (estado === 'ok') return <>{children}</>

  return (
    <div className="pantalla-admin admin-login">
      <form onSubmit={entrar} className="login-caja">
        <h1>🔐 PIN del local</h1>
        <p style={{ color: '#77705f' }}>
          Este sistema está protegido. Ingresa el PIN del restaurante (se guarda en este
          dispositivo, solo se pide una vez).
        </p>
        <input
          type="password"
          inputMode="numeric"
          placeholder="PIN"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          autoFocus
        />
        {error && <div className="banner-error">{error}</div>}
        <button type="submit" className="boton-grande boton-primario">Entrar</button>
      </form>
    </div>
  )
}
