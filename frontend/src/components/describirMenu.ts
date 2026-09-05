import type { MenuCarrito } from '../api'
import { NOMBRE_EMPAQUE } from '../api'

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
