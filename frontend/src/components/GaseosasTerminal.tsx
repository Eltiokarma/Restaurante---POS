import { useState } from 'react'
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
  // Plegada como la mesa (pedido del dueño): nueve tarjetas comían la
  // pantalla del pedido; lo elegido se ve en la cabecera sin abrirla
  const [abierto, setAbierto] = useState(false)
  if (lista.length === 0) return null
  const elegidas = enCarrito.filter((x) => x.cantidad > 0)
  return (
    <section className="selector-servicio pliegue-extras gaseosas-terminal" aria-label="Gaseosas">
      <button className="pliegue-cabecera" onClick={() => setAbierto((v) => !v)} aria-expanded={abierto}>
        <span className="pliegue-titulo">
          🥤 Gaseosas <small className="titulo-opcional">(opcional)</small>
        </span>
        {elegidas.length > 0 && (
          <span className="pliegue-resumen">
            {elegidas.map((x) => `${x.cantidad} ${x.bebida.nombre}`).join(' + ')}
          </span>
        )}
        <span className="tarjeta-menu-flecha">{abierto ? '▲' : '▼'}</span>
      </button>
      {abierto && (
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
      )}
    </section>
  )
}
