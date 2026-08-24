import { useCallback, useMemo, useState } from 'react'
import type { ItemCarrito, Plato } from '../api'

// El carrito vive SOLO en el estado del frontend hasta que termina la
// ventana de cancelación; recién ahí se persiste en el backend.
export function useCarrito() {
  const [items, setItems] = useState<ItemCarrito[]>([])

  const cambiarCantidad = useCallback((plato: Plato, delta: number) => {
    setItems((prev) => {
      const existente = prev.find((i) => i.plato.id === plato.id)
      if (!existente) {
        return delta > 0 ? [...prev, { plato, cantidad: delta }] : prev
      }
      const nueva = existente.cantidad + delta
      if (nueva <= 0) return prev.filter((i) => i.plato.id !== plato.id)
      return prev.map((i) => (i.plato.id === plato.id ? { ...i, cantidad: nueva } : i))
    })
  }, [])

  const cantidadDe = useCallback(
    (platoId: number) => items.find((i) => i.plato.id === platoId)?.cantidad ?? 0,
    [items],
  )

  const vaciar = useCallback(() => setItems([]), [])

  const totalItems = useMemo(() => items.reduce((s, i) => s + i.cantidad, 0), [items])
  const totalSoles = useMemo(
    () => items.reduce((s, i) => s + i.plato.precio * i.cantidad, 0),
    [items],
  )

  return { items, cambiarCantidad, cantidadDe, vaciar, totalItems, totalSoles }
}
