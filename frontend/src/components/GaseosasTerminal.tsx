import { soles } from '../api'
import type { Bebida } from '../api'

interface Props {
  lista: Bebida[]
  enCarrito: { bebida: Bebida; cantidad: number }[]
  onCambiar: (bebida: Bebida, delta: number) => void
}

/** Gaseosas en la terminal (pedido del dueño): la lista fija de caja,
 *  con − / + por botella. No pasan por cocina; salen en la comanda. */
export function GaseosasTerminal({ lista, enCarrito, onCambiar }: Props) {
  if (lista.length === 0) return null
  return (
    <section className="gaseosas-terminal" aria-label="Gaseosas">
      <h2 className="gaseosas-titulo">🥤 Gaseosas</h2>
      <div className="gaseosas-grilla">
        {lista.map((b) => {
          const cantidad = enCarrito.find((x) => x.bebida.id === b.id)?.cantidad ?? 0
          return (
            <div className={`gaseosa ${cantidad > 0 ? 'gaseosa-elegida' : ''}`} key={b.id}>
              <div className="gaseosa-info">
                <span className="gaseosa-nombre">{b.nombre}</span>
                <span className="gaseosa-precio">{soles(b.precio)}</span>
              </div>
              <div className="gaseosa-controles">
                <button
                  className="gaseosa-boton"
                  onClick={() => onCambiar(b, -1)}
                  disabled={cantidad === 0}
                  aria-label={`Una ${b.nombre} menos`}
                >
                  −
                </button>
                <span className="gaseosa-cantidad">{cantidad}</span>
                <button
                  className="gaseosa-boton gaseosa-mas"
                  onClick={() => onCambiar(b, 1)}
                  aria-label={`Una ${b.nombre} más`}
                >
                  +
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
