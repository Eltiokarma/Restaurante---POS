import type { ItemCarrito, MenuHoy } from './api'

/**
 * Sugerencia de menú encadenado (§1, aprendido en sala).
 *
 * La gente pide "sopa, lomo y chicha" tocando cada plato desde las
 * categorías — venta a la carta — y termina pagando cada uno. Si existe
 * un menú activo cuyos tiempos se cubren con lo que hay en el carrito y
 * sale más barato, se ofrece convertirlo en un toque.
 */
export interface SugerenciaMenu {
  menu: MenuHoy
  elecciones: Record<number, number> // tiempo_orden → plato_id
  platosUsados: number[]             // una unidad de cada uno sale del carrito
  sumaCarta: number
  precioMenu: number
  ahorro: number
}

export function sugerirMenu(items: ItemCarrito[], menus: MenuHoy[]): SugerenciaMenu | null {
  let mejor: SugerenciaMenu | null = null
  for (const menu of menus) {
    const elecciones: Record<number, number> = {}
    const usados: number[] = []
    let precioMenu = menu.precio
    let cubre = true
    for (const tiempo of menu.tiempos) {
      const item = items.find(
        (i) => !usados.includes(i.plato.id) && tiempo.alternativas.some((a) => a.plato_id === i.plato.id),
      )
      if (item) {
        elecciones[tiempo.orden] = item.plato.id
        usados.push(item.plato.id)
        precioMenu += tiempo.alternativas.find((a) => a.plato_id === item.plato.id)?.recargo ?? 0
      } else if (tiempo.alternativas.length === 1) {
        // Tiempo de una sola opción: viene incluido, no hace falta que esté en el carrito
        elecciones[tiempo.orden] = tiempo.alternativas[0].plato_id
      } else if (tiempo.obligatorio) {
        cubre = false
        break
      }
    }
    // Con un solo plato del carrito no hay "combo" que convertir
    if (!cubre || usados.length < 2) continue
    const sumaCarta = usados.reduce(
      (s, id) => s + (items.find((i) => i.plato.id === id)?.plato.precio ?? 0), 0,
    )
    const ahorro = Math.round((sumaCarta - precioMenu) * 100) / 100
    if (ahorro <= 0) continue
    if (!mejor || ahorro > mejor.ahorro) {
      mejor = { menu, elecciones, platosUsados: usados, sumaCarta, precioMenu, ahorro }
    }
  }
  return mejor
}
