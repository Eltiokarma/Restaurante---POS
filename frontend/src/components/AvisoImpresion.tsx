import type { ImpresionPendiente } from '../api'

// Debajo de esto es normal: el ticket recién salió y la cola tarda ~3 s
const MINUTOS_PARA_AVISAR = 2

/**
 * Cintillo de impresión detenida (caja y cocina).
 *
 * Si la ticketera o el puente se cuelgan, los tickets se acumulan en
 * silencio: cocina no se entera y el cliente espera un plato que nadie
 * está preparando. Esto convierte ese problema invisible en uno visible.
 */
export function AvisoImpresion({ estado }: { estado?: ImpresionPendiente }) {
  if (!estado || estado.cantidad === 0 || estado.minutos < MINUTOS_PARA_AVISAR) return null
  const minutos = Math.round(estado.minutos)
  return (
    <div className="aviso-impresion">
      <strong>
        ⚠ {estado.cantidad} ticket{estado.cantidad > 1 ? 's' : ''} sin imprimir
        {minutos >= 1 && ` hace ${minutos} min`}
      </strong>
      <span>
        Revisa la tablet (o la PC) que imprime: que esté prendida, con la pantalla
        encendida y la página <code>/ticketera</code> abierta.
      </span>
    </div>
  )
}
