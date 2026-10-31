import { useState } from 'react'
import { soles } from '../api'
import type { MenuCaja, PlatoParaAgregar } from '../api'

const ORDEN_DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

function ordenDia(nombre: string): number {
  const i = ORDEN_DIAS.indexOf(nombre)
  return i === -1 ? ORDEN_DIAS.length : i
}

/**
 * Caja → Menú del día: sumar un plato de otro día ("el asado del jueves,
 * hoy sábado") sin pasar por el editor del admin. Se elige el día (o se
 * busca) y un toque lo pone como opción de hoy, con el recargo que tenía.
 */
export function AgregarDeOtroDia({ menuCaja, onAgregar }: {
  menuCaja: MenuCaja
  onAgregar: (plantillaId: number, plato: PlatoParaAgregar) => void
}) {
  const activas = menuCaja.plantillas.filter((p) => p.activo_hoy)
  const [plantillaId, setPlantillaId] = useState<number | null>(null)
  const [dia, setDia] = useState<string | null>(null)
  const [busqueda, setBusqueda] = useState('')
  const plantilla = activas.find((p) => p.id === plantillaId) ?? activas[0]
  if (!plantilla) return null

  // Lo que ya está prendido hoy en ese menú no se ofrece
  const prendidos = new Set(
    plantilla.tiempos.flatMap((t) => t.alternativas.filter((a) => a.activo_hoy).map((a) => a.plato_id)),
  )
  const disponibles = (menuCaja.para_agregar ?? []).filter((p) => !prendidos.has(p.plato_id))
  const dias = [...new Set(disponibles.flatMap((p) => p.dias))].sort((a, b) => ordenDia(a) - ordenDia(b) || a.localeCompare(b))
  const texto = busqueda.trim().toLowerCase()
  const lista = texto
    ? disponibles.filter((p) => p.nombre.toLowerCase().includes(texto))
    : dia === 'otros'
      ? disponibles.filter((p) => p.dias.length === 0)
      : dia ? disponibles.filter((p) => p.dias.includes(dia)) : []
  const grupos = [
    { titulo: 'Segundos', platos: lista.filter((p) => p.categoria === 'fondo') },
    { titulo: 'Entradas', platos: lista.filter((p) => p.categoria === 'entrada') },
  ].filter((g) => g.platos.length > 0)

  return (
    <div className="defecto-bloque">
      <h4>➕ Agregar un plato de otro día</h4>
      {activas.length > 1 && (
        <div className="defecto-chips">
          {activas.map((p) => (
            <button
              key={p.id}
              className={`defecto-chip ${p.id === plantilla.id ? 'defecto-chip-activo' : ''}`}
              onClick={() => setPlantillaId(p.id)}
            >
              {p.nombre}
            </button>
          ))}
        </div>
      )}
      <input
        className="agregar-dia-buscar"
        type="search"
        placeholder="Buscar: asado, causa, trucha…"
        value={busqueda}
        onChange={(e) => setBusqueda(e.target.value)}
        aria-label="Buscar un plato"
      />
      {!texto && (
        <div className="defecto-chips">
          {dias.map((d) => (
            <button
              key={d}
              className={`defecto-chip ${dia === d ? 'defecto-chip-activo' : ''}`}
              aria-pressed={dia === d}
              onClick={() => setDia(dia === d ? null : d)}
            >
              {d}
            </button>
          ))}
          {disponibles.some((p) => p.dias.length === 0) && (
            <button
              className={`defecto-chip ${dia === 'otros' ? 'defecto-chip-activo' : ''}`}
              aria-pressed={dia === 'otros'}
              onClick={() => setDia(dia === 'otros' ? null : 'otros')}
            >
              Otros
            </button>
          )}
        </div>
      )}
      {!texto && !dia && <p className="rh-ayuda">Elige el día de donde viene el plato, o búscalo por su nombre.</p>}
      {(texto || dia) && grupos.length === 0 && <p className="rh-ayuda">Nada por aquí (o ya está en el menú de hoy).</p>}
      {grupos.map((g) => (
        <div key={g.titulo} className="menu-dia-tiempo">
          <span className="menu-dia-rotulo">{g.titulo}</span>
          <div className="defecto-chips">
            {g.platos.map((p) => (
              <button key={p.plato_id} className="defecto-chip" onClick={() => onAgregar(plantilla.id, p)}>
                ＋ {p.nombre}{p.recargo > 0 ? ` (+${soles(p.recargo)})` : ''}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
