import { soles } from '../api'

interface Props {
  totalItems: number
  totalSoles: number
  onVerPedido: () => void
}

export function BarraCarrito({ totalItems, totalSoles, onVerPedido }: Props) {
  return (
    <div className="barra-carrito">
      <span className="barra-carrito-resumen">
        {totalItems === 0
          ? 'Tu pedido está vacío'
          : `${totalItems} ${totalItems === 1 ? 'item' : 'items'} — ${soles(totalSoles)}`}
      </span>
      <button className="boton-grande boton-primario" onClick={onVerPedido} disabled={totalItems === 0}>
        VER MI PEDIDO →
      </button>
    </div>
  )
}
