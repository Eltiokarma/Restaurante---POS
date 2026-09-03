import { soles } from '../api'
import type { ItemCarrito, MenuHoy } from '../api'
import { sugerirMenu } from '../menuSugerido'
import type { SugerenciaMenu as Sugerencia } from '../menuSugerido'

interface Props {
  items: ItemCarrito[]
  menus: MenuHoy[]
  onConvertir: (s: Sugerencia) => void
}

/** Banner "esto sale más barato como menú" con el botón para convertirlo. */
export function SugerenciaMenu({ items, menus, onConvertir }: Props) {
  const s = sugerirMenu(items, menus)
  if (!s) return null
  const nombres = s.platosUsados
    .map((id) => items.find((i) => i.plato.id === id)?.plato.nombre)
    .filter(Boolean)
    .join(' + ')
  return (
    <div className="sugerencia-menu">
      <span>
        💡 <strong>{nombres}</strong> sale a <strong>{soles(s.precioMenu)}</strong> como{' '}
        <strong>{s.menu.nombre}</strong> (ahorras {soles(s.ahorro)})
      </span>
      <button className="boton-grande boton-confirmar boton-sugerencia" onClick={() => onConvertir(s)}>
        ✅ Cobrar como menú
      </button>
    </div>
  )
}
