import type { MenuCarrito, MenuHoy } from '../api'
import { soles } from '../api'

/** Cuántas unidades de ESTE menú hay en el pedido (para el contador). */
export function menusEnPedido(menus: MenuCarrito[], menuId: number): number {
  return menus
    .filter((l) => l.menu.id === menuId)
    .reduce((s, l) => s + l.cantidad, 0)
}

/**
 * La tarjeta que ofrece el menú del día: la lista de tiempos con sus
 * platos (sin precios por plato), el botón "+ UN MENÚ" y el box con el
 * total de menús del pedido al costado. La usan la terminal y la caja.
 */
export function TarjetaOfertaMenu({ menu, etiqueta, enPedido, onAgregar }: {
  menu: MenuHoy
  etiqueta: string
  enPedido: number
  onAgregar: () => void
}) {
  return (
    <div className="combo">
      <div className="combo-cabecera">
        <span className="combo-titulo">{menu.nombre}</span>
        <span className="combo-precio">{soles(menu.precio)}</span>
      </div>
      <div className="combo-resumen-tiempos">
        {menu.tiempos.map((t) => (
          <div key={t.orden}>
            <strong>{t.rotulo}:</strong>{' '}
            {t.alternativas.length === 1
              ? `${t.alternativas[0].nombre} (incluido)`
              : t.alternativas.map((a) => a.nombre).join(' / ')}
          </div>
        ))}
      </div>
      {/* El total de menús al costado del botón: se ve sin scrollear */}
      <div className="fila-armar">
        <button className="boton-armar" onClick={onAgregar}>
          {etiqueta}
        </button>
        <div className="contador-menus" aria-label={`${enPedido} en tu pedido`}>
          <span className="contador-menus-cifra">{enPedido}</span>
          <span className="contador-menus-texto">{enPedido === 1 ? 'menú' : 'menús'}</span>
        </div>
      </div>
    </div>
  )
}
