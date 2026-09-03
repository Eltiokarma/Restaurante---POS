import { useEffect, useState } from 'react'
import type { ImpresionPendiente } from '../api'

// Debajo de esto es normal: el ticket recién salió y la cola tarda ~3 s
const MINUTOS_PARA_AVISAR = 2
// "Ocultar" lo esconde este rato; si la cola CRECE, vuelve antes
const OCULTAR_MS = 10 * 60 * 1000

/**
 * Cintillo de impresión detenida (caja y cocina).
 *
 * Si la ticketera o el puente se cuelgan, los tickets se acumulan en
 * silencio: cocina no se entera y el cliente espera un plato que nadie
 * está preparando. Esto convierte ese problema invisible en uno visible.
 * Es compacto y se puede ocultar un rato (reaparece si se acumulan más).
 */
export function AvisoImpresion({ estado }: { estado?: ImpresionPendiente }) {
  const [ocultoHasta, setOcultoHasta] = useState(0)
  const [cantidadOcultada, setCantidadOcultada] = useState(0)

  const cantidad = estado?.cantidad ?? 0
  // Si llegaron más tickets atascados desde que se ocultó, vuelve a mostrarse.
  // Y si la cola se vació, se olvida lo ocultado: un atasco NUEVO (aunque
  // sea de un solo ticket) es justo lo que este aviso existe para mostrar.
  useEffect(() => {
    if (cantidad === 0 && cantidadOcultada !== 0) {
      setCantidadOcultada(0)
      setOcultoHasta(0)
    } else if (cantidad > cantidadOcultada) {
      setOcultoHasta(0)
    }
  }, [cantidad, cantidadOcultada])

  if (!estado || cantidad === 0 || estado.minutos < MINUTOS_PARA_AVISAR) return null
  if (Date.now() < ocultoHasta) return null

  const minutos = Math.round(estado.minutos)
  return (
    <div className="aviso-impresion">
      <span className="aviso-impresion-texto">
        <strong>
          ⚠ {cantidad} ticket{cantidad > 1 ? 's' : ''} sin imprimir
          {minutos >= 1 && ` hace ${minutos} min`}
        </strong>
        {' · '}revisa la tablet que imprime (prendida, con <code>/ticketera</code> abierta)
      </span>
      <button
        className="aviso-impresion-cerrar"
        onClick={() => {
          setCantidadOcultada(cantidad)
          setOcultoHasta(Date.now() + OCULTAR_MS)
        }}
        title="Ocultar 10 minutos (vuelve solo si se acumulan más)"
        aria-label="Ocultar aviso"
      >
        ✕
      </button>
    </div>
  )
}
