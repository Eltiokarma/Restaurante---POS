import type { Plato } from '../api'
import { soles } from '../api'

interface Props {
  plato: Plato
  cantidad: number
  onCambiar: (delta: number) => void
}

export function TarjetaPlato({ plato, cantidad, onCambiar }: Props) {
  return (
    <div className={`tarjeta-plato ${cantidad > 0 ? 'con-items' : ''}`}>
      <div className="tarjeta-plato-info">
        <span className="tarjeta-plato-nombre">{plato.nombre}</span>
        <span className="tarjeta-plato-precio">{soles(plato.precio)}</span>
      </div>
      <div className="tarjeta-plato-controles">
        <button
          className="boton-cantidad"
          onClick={() => onCambiar(-1)}
          disabled={cantidad === 0}
          aria-label={`Quitar ${plato.nombre}`}
        >
          −
        </button>
        <span className="tarjeta-plato-cantidad">{cantidad}</span>
        <button
          className="boton-cantidad boton-mas"
          onClick={() => onCambiar(1)}
          aria-label={`Agregar ${plato.nombre}`}
        >
          +
        </button>
      </div>
    </div>
  )
}
