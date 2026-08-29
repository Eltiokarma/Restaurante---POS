import type { Plato } from '../api'
import { soles, urlFotoPlato } from '../api'

interface Props {
  plato: Plato
  cantidad: number
  onCambiar: (delta: number) => void
}

export function TarjetaPlato({ plato, cantidad, onCambiar }: Props) {
  return (
    <div className={`tarjeta-plato ${cantidad > 0 ? 'con-items' : ''} ${plato.foto ? 'con-foto' : ''}`}>
      {plato.foto && (
        <img
          className="tarjeta-plato-foto"
          src={urlFotoPlato(plato.foto)}
          alt={plato.nombre}
          loading="lazy"
        />
      )}
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
