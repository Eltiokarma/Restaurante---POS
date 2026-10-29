import { useEffect, useState } from 'react'
import { api, registrarAutorizador } from '../api'
import type { PersonaEquipo } from '../api'
import { TecladoPin } from './TecladoPin'

interface Pedido {
  mensaje: string
  responder: (autoriza: string | null) => void
}

/**
 * Lo delicado (anular, quitar platos, borrar un egreso, reabrir la caja…)
 * con el equipo activo: el backend responde 428 y aquí un admin pone su
 * PIN en el momento, sin cambiar de sesión. Montado una sola vez en
 * main.tsx; api.ts reintenta la misma acción con lo que se responda.
 */
export function Autorizador() {
  const [pedido, setPedido] = useState<Pedido | null>(null)
  const [admins, setAdmins] = useState<PersonaEquipo[]>([])
  const [elegido, setElegido] = useState<number | null>(null)
  const [pin, setPin] = useState('')

  useEffect(() => {
    registrarAutorizador((mensaje) => new Promise((responder) => {
      setPin('')
      setPedido({ mensaje, responder })
      api.equipoQuienes()
        .then((d) => {
          const lista = d.personas.filter((p) => p.rol === 'admin')
          setAdmins(lista)
          // Con un solo admin (lo normal) ya queda elegido
          setElegido((actual) => actual ?? (lista.length === 1 ? lista[0].id : null))
        })
        .catch(() => setAdmins([]))
    }))
    return () => registrarAutorizador(null)
  }, [])

  if (!pedido) return null
  // Si vuelve a pedirse, el backend dice que el PIN estuvo mal
  const error = pedido.mensaje.includes('incorrecto') ? 'PIN incorrecto' : ''

  const cerrar = (respuesta: string | null) => {
    pedido.responder(respuesta)
    setPedido(null)
  }

  return (
    <div className="modal-fondo modal-autoriza-fondo" onClick={() => cerrar(null)}>
      <div className="modal modal-autoriza" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <h2>🔐 Pide autorización</h2>
        <p>{error ? 'Ese PIN no es. Intenta de nuevo.' : 'Esto necesita el PIN de un administrador.'}</p>
        {admins.length === 0 && (
          <p className="teclado-pin-error">
            No hay administradores en el equipo: créalos en Admin → Equipo.
          </p>
        )}
        {admins.length > 1 && (
          <div className="quien-eres-lista">
            {admins.map((a) => (
              <button
                key={a.id}
                type="button"
                className={`quien-eres-persona ${elegido === a.id ? 'elegida' : ''}`}
                onClick={() => setElegido(a.id)}
              >
                {a.nombre}
              </button>
            ))}
          </div>
        )}
        {admins.length === 1 && <p><strong>{admins[0].nombre}</strong>, pon tu PIN:</p>}
        {elegido !== null && (
          <TecladoPin
            valor={pin}
            onCambiar={setPin}
            onOk={() => cerrar(`${elegido}:${pin}`)}
            error={error}
            okTexto="Autorizar"
          />
        )}
        <button type="button" className="quien-eres-volver" onClick={() => cerrar(null)}>Cancelar</button>
      </div>
    </div>
  )
}
