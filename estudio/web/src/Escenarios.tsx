import { useEffect, useState } from 'react'
import { api, type Escenario, type Guardado, type SupuestosFlujo } from './api'

interface Props {
  esc: Escenario
  sup: SupuestosFlujo
  onCargar: (g: Guardado) => void
  onError: (e: unknown) => void
}

/** Guardar el juego de barras con un nombre ("Candela hoy") y volver a él. */
export function Escenarios({ esc, sup, onCargar, onError }: Props) {
  const [lista, setLista] = useState<Guardado[]>([])
  const [nombre, setNombre] = useState('')
  const [elegido, setElegido] = useState<number | ''>('')
  const [aviso, setAviso] = useState('')

  const refrescar = () => api.escenarios().then(setLista).catch(onError)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => void refrescar(), [])

  const guardar = async () => {
    const n = nombre.trim()
    if (!n) return
    try {
      await api.guardar(n, { escenario: esc, supuestos: sup })
      setNombre('')
      setAviso(`Guardado: ${n}`)
      setTimeout(() => setAviso(''), 2500)
      refrescar()
    } catch (e) {
      onError(e)
    }
  }

  const borrar = async () => {
    if (elegido === '') return
    const g = lista.find((x) => x.id === elegido)
    if (!g || !window.confirm(`¿Borrar "${g.nombre}"?`)) return
    try {
      await api.borrar(g.id)
      setElegido('')
      refrescar()
    } catch (e) {
      onError(e)
    }
  }

  return (
    <section className="es-escenarios">
      <div className="es-fila">
        <select
          value={elegido}
          onChange={(e) => {
            const id = e.target.value === '' ? '' : Number(e.target.value)
            setElegido(id)
            const g = lista.find((x) => x.id === id)
            if (g) onCargar(g)
          }}
        >
          <option value="">{lista.length ? 'Abrir escenario guardado…' : 'Aún no hay escenarios guardados'}</option>
          {[...new Set(lista.map((g) => g.datos.ficha?.categoria ?? 'Mis escenarios'))].map((cat) => (
            <optgroup key={cat} label={cat}>
              {lista
                .filter((g) => (g.datos.ficha?.categoria ?? 'Mis escenarios') === cat)
                .map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.nombre}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
        {elegido !== '' && (
          <button type="button" className="es-secundario" onClick={borrar}>
            Borrar
          </button>
        )}
      </div>
      <div className="es-fila">
        <input
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && guardar()}
          placeholder="Nombre (p. ej. Candela hoy)"
          maxLength={120}
        />
        <button type="button" className="es-secundario" onClick={guardar} disabled={!nombre.trim()}>
          Guardar
        </button>
      </div>
      {aviso && <p className="es-aviso">{aviso}</p>}
    </section>
  )
}
