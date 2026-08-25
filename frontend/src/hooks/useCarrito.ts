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

  // Quita del carrito los platos que ya no están disponibles (agotados)
  const eliminarNoDisponibles = useCallback((idsDisponibles: Set<number>) => {
    setItems((prev) => prev.filter((i) => idsDisponibles.has(i.plato.id)))
  }, [])

  // Refresca nombre/precio de los items con los datos más recientes del menú
  const sincronizarConMenu = useCallback((platos: Plato[]) => {
    const porId = new Map(platos.map((p) => [p.id, p]))
    setItems((prev) =>
      prev.map((i) => {
        const nuevo = porId.get(i.plato.id)
        return nuevo ? { ...i, plato: nuevo } : i
      }),
    )
  }, [])

  const totalItems = useMemo(() => items.reduce((s, i) => s + i.cantidad, 0), [items])
  const totalSoles = useMemo(
    () => items.reduce((s, i) => s + i.plato.precio * i.cantidad, 0),
    [items],
  )

  return {
    items,
    cambiarCantidad,
    cantidadDe,
    vaciar,
    eliminarNoDisponibles,
    sincronizarConMenu,
    totalItems,
    totalSoles,
  }
}
