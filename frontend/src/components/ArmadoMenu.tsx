import { useState } from 'react'
import { soles, subtotalMenu, NOMBRE_EMPAQUE } from '../api'
import type { Empaque, ExtraMenu, MenuCarrito, MenuHoy } from '../api'

interface Props {
  menu: MenuHoy
  onAgregar: (linea: MenuCarrito) => void
  onCerrar: () => void
}

/**
 * Modal táctil para armar un menú encadenado: una sección por tiempo con
 * botones grandes. Un tiempo con UNA sola alternativa no se elige: se
 * muestra como incluido. Si el tiempo ofrece porciones extra
 * (precio_extra > 0), debajo aparece el paso "¿una más?".
 */
export function ArmadoMenu({ menu, onAgregar, onCerrar }: Props) {
  const [elecciones, setElecciones] = useState<Record<number, number>>(() => {
    const base: Record<number, number> = {}
    // Los tiempos de una sola opción vienen elegidos de fábrica
    for (const t of menu.tiempos) {
      if (t.alternativas.length === 1) base[t.orden] = t.alternativas[0].plato_id
    }
    return base
  })
  const [extras, setExtras] = useState<ExtraMenu[]>([])
  const [cantidad, setCantidad] = useState(1)

  const faltantes = menu.tiempos.filter(
    (t) => t.obligatorio && t.alternativas.length > 0 && !(t.orden in elecciones),
  )

  const cantidadExtra = (tiempoOrden: number, platoId: number) =>
    extras.find((e) => e.tiempo_orden === tiempoOrden && e.plato_id === platoId)?.cantidad ?? 0

  const cambiarExtra = (tiempoOrden: number, platoId: number, delta: number) => {
    setExtras((prev) => {
      const idx = prev.findIndex((e) => e.tiempo_orden === tiempoOrden && e.plato_id === platoId)
      if (idx === -1) {
        return delta > 0 ? [...prev, { tiempo_orden: tiempoOrden, plato_id: platoId, cantidad: delta }] : prev
      }
      const nueva = prev[idx].cantidad + delta
      if (nueva <= 0) return prev.filter((_, i) => i !== idx)
      return prev.map((e, i) => (i === idx ? { ...e, cantidad: nueva } : e))
    })
  }

  const linea: MenuCarrito = {
    menu, cantidad, elecciones, extras, omitidos: [], agregados: [],
    empaque: 'mesa' as Empaque, empaques: {}, nota: '',
  }

  return (
    <div className="modal-fondo">
      <div className="modal modal-armado">
        <div className="combo-cabecera">
          <span className="combo-titulo">{menu.nombre}</span>
          <span className="combo-precio">{soles(menu.precio)}</span>
        </div>

        <div className="combo-tiempos armado-tiempos">
          {menu.tiempos.map((t) => (
            <div key={t.orden} className={`tiempo ${t.alternativas.length === 1 ? 'tiempo-sin-opciones' : ''}`}>
              <span className="tiempo-orden">{t.orden}</span>
              <div className="tiempo-cuerpo">
                <span className="tiempo-rotulo">{t.rotulo}</span>
                {t.alternativas.length === 1 ? (
                  <div className="tiempo-fila-incluido">
                    <span className="tiempo-plato">{t.alternativas[0].nombre}</span>
                    <span className="tiempo-incluido">Incluido</span>
                  </div>
                ) : (
                  <div className="opciones-tiempo">
                    {t.alternativas.map((a) => (
                      <button
                        key={a.plato_id}
                        className={`opcion-tiempo ${elecciones[t.orden] === a.plato_id ? 'opcion-activa' : ''}`}
                        onClick={() => setElecciones((prev) => ({ ...prev, [t.orden]: a.plato_id }))}
                      >
                        {elecciones[t.orden] === a.plato_id ? '● ' : '○ '}
                        {a.nombre}
                        {a.recargo > 0 && <small> +{soles(a.recargo)}</small>}
                        {a.sale_al_momento && <small> 🍳 al momento</small>}
                      </button>
                    ))}
                  </div>
                )}
                {t.precio_extra > 0 && (
                  <div className="extras-tiempo">
                    <span className="extras-titulo">
                      ¿{t.rotulo.toLowerCase()} extra? ({soles(t.precio_extra)} c/u)
                    </span>
                    {t.alternativas.map((a) => (
                      <span key={a.plato_id} className="extra-stepper">
                        {a.nombre}
                        <button
                          className="boton-mini"
                          onClick={() => cambiarExtra(t.orden, a.plato_id, -1)}
                          disabled={cantidadExtra(t.orden, a.plato_id) === 0}
                          aria-label={`Quitar ${a.nombre} extra`}
                        >−</button>
                        <strong>{cantidadExtra(t.orden, a.plato_id)}</strong>
                        <button
                          className="boton-mini"
                          onClick={() => cambiarExtra(t.orden, a.plato_id, 1)}
                          aria-label={`Agregar ${a.nombre} extra`}
                        >+</button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="armado-pie">
          <div className="armado-cantidad">
            <button className="boton-mini" onClick={() => setCantidad((c) => Math.max(1, c - 1))} aria-label="Un menú menos">−</button>
            <strong>{cantidad}</strong>
            <button className="boton-mini" onClick={() => setCantidad((c) => Math.min(20, c + 1))} aria-label="Un menú más">+</button>
          </div>
          <button className="boton-grande boton-secundario" onClick={onCerrar}>
            Cancelar
          </button>
          <button
            className="boton-grande boton-confirmar"
            disabled={faltantes.length > 0}
            onClick={() => onAgregar(linea)}
          >
            {faltantes.length > 0
              ? `Elige ${faltantes[0].rotulo.toLowerCase()}`
              : `✅ Agregar ${cantidad > 1 ? `${cantidad} menús` : ''} — ${soles(subtotalMenu(linea))}`}
          </button>
        </div>
      </div>
    </div>
  )
}

/** Resumen en una línea de lo elegido, para el carrito y el countdown:
 * "Sopa criolla + Asado con puré + Chicha morada (+1 entrada extra)" */
export function describirMenu(linea: MenuCarrito): string {
  const partes: string[] = []
  for (const t of linea.menu.tiempos) {
    if (linea.omitidos.includes(t.orden)) {
      partes.push(`sin ${t.rotulo.toLowerCase()}`)
      continue
    }
    const alternativa = t.alternativas.find((a) => a.plato_id === linea.elecciones[t.orden])
    if (!alternativa) continue
    // Solo se menciona el empaque cuando ESTE plato va distinto al resto
    const distinto = linea.empaques[t.orden]
    partes.push(
      alternativa.nombre +
        (distinto && distinto !== linea.empaque ? ` (${NOMBRE_EMPAQUE[distinto]})` : ''),
    )
  }
  const extras = linea.extras.reduce((s, e) => s + e.cantidad, 0)
  const agregados = linea.agregados
    .map((a) => `+${a.cantidad} ${a.agregado.nombre.toLowerCase()}`)
    .join(', ')
  return (
    partes.join(' + ') +
    (extras > 0 ? ` (+${extras} extra)` : '') +
    (agregados ? ` (${agregados})` : '')
  )
}
