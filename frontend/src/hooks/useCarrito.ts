import { useCallback, useMemo, useState } from 'react'
import { subtotalMenu } from '../api'
import type { Empaque, ItemCarrito, MenuCarrito, MenuHoy, Plato } from '../api'
import type { SugerenciaMenu } from '../menuSugerido'

// El carrito vive SOLO en el estado del frontend hasta que termina la
// ventana de cancelación; recién ahí se persiste en el backend.
// Tiene dos tipos de línea: platos a la carta (items) y menús encadenados
// ya armados (menus), cada uno con sus elecciones y porciones extra.
export function useCarrito() {
  const [items, setItems] = useState<ItemCarrito[]>([])
  const [menus, setMenus] = useState<MenuCarrito[]>([])

  const cambiarCantidad = useCallback((plato: Plato, delta: number) => {
    setItems((prev) => {
      const existente = prev.find((i) => i.plato.id === plato.id)
      if (!existente) {
        return delta > 0
          ? [...prev, { plato, cantidad: delta, empaque: 'mesa' as Empaque, nota: '' }]
          : prev
      }
      const nueva = existente.cantidad + delta
      if (nueva <= 0) return prev.filter((i) => i.plato.id !== plato.id)
      return prev.map((i) => (i.plato.id === plato.id ? { ...i, cantidad: nueva } : i))
    })
  }, [])

  // Empaque POR PLATO: mesa, táper, bolsa o lonchera
  const cambiarEmpaque = useCallback((platoId: number, empaque: Empaque) => {
    setItems((prev) => prev.map((i) => (i.plato.id === platoId ? { ...i, empaque } : i)))
  }, [])

  const empaqueParaTodos = useCallback((empaque: Empaque) => {
    setItems((prev) => prev.map((i) => ({ ...i, empaque })))
    setMenus((prev) => prev.map((m) => ({ ...m, empaque })))
  }, [])

  // Pedido especial por plato: "sin frijoles", "con un huevo frito"…
  const cambiarNota = useCallback((platoId: number, nota: string) => {
    setItems((prev) => prev.map((i) => (i.plato.id === platoId ? { ...i, nota } : i)))
  }, [])

  const cantidadDe = useCallback(
    (platoId: number) => items.find((i) => i.plato.id === platoId)?.cantidad ?? 0,
    [items],
  )

  // ---------- Menús encadenados ----------

  const agregarMenu = useCallback((linea: MenuCarrito) => {
    setMenus((prev) => {
      // Dos menús armados igual (mismas elecciones, sin extras) se juntan
      const clave = (m: MenuCarrito) => JSON.stringify([m.menu.id, m.elecciones, m.empaque])
      const idx = prev.findIndex(
        (m) => m.extras.length === 0 && linea.extras.length === 0 && clave(m) === clave(linea),
      )
      if (idx === -1) return [...prev, linea]
      return prev.map((m, i) => (i === idx ? { ...m, cantidad: m.cantidad + linea.cantidad } : m))
    })
  }, [])

  // "Sopa + lomo + chicha" a la carta → una línea de menú: sale UNA unidad de
  // cada plato usado y entra el menú con esas elecciones. Las notas de los
  // platos se conservan en la nota del menú; el empaque, el del primero.
  const convertirEnMenu = useCallback((s: SugerenciaMenu) => {
    // Se lee el carrito actual aquí (no dentro de un updater): un setState
    // anidado en otro se ejecutaría dos veces en modo estricto
    const usados = items.filter((i) => s.platosUsados.includes(i.plato.id))
    const nota = usados.map((i) => i.nota.trim()).filter(Boolean).join(' / ')
    const empaque = usados[0]?.empaque ?? ('mesa' as Empaque)
    setMenus((m) => [...m, {
      menu: s.menu, cantidad: 1, elecciones: s.elecciones, extras: [], empaque, nota,
    }])
    setItems((prev) =>
      prev
        .map((i) => (s.platosUsados.includes(i.plato.id) ? { ...i, cantidad: i.cantidad - 1 } : i))
        .filter((i) => i.cantidad > 0),
    )
  }, [items])

  const cambiarCantidadMenu = useCallback((idx: number, delta: number) => {
    setMenus((prev) =>
      prev
        .map((m, i) => (i === idx ? { ...m, cantidad: m.cantidad + delta } : m))
        .filter((m) => m.cantidad > 0),
    )
  }, [])

  const quitarMenu = useCallback((idx: number) => {
    setMenus((prev) => prev.filter((_, i) => i !== idx))
  }, [])

  const cambiarEmpaqueMenu = useCallback((idx: number, empaque: Empaque) => {
    setMenus((prev) => prev.map((m, i) => (i === idx ? { ...m, empaque } : m)))
  }, [])

  const cambiarNotaMenu = useCallback((idx: number, nota: string) => {
    setMenus((prev) => prev.map((m, i) => (i === idx ? { ...m, nota } : m)))
  }, [])

  const vaciar = useCallback(() => {
    setItems([])
    setMenus([])
  }, [])

  // Quita del carrito lo que ya no está disponible (agotados)
  const eliminarNoDisponibles = useCallback(
    (idsDisponibles: Set<number>, menuIdsDisponibles?: Set<number>) => {
      setItems((prev) => prev.filter((i) => idsDisponibles.has(i.plato.id)))
      if (menuIdsDisponibles) {
        setMenus((prev) =>
          prev.filter(
            (m) =>
              menuIdsDisponibles.has(m.menu.id) &&
              Object.values(m.elecciones).every((id) => idsDisponibles.has(id)) &&
              m.extras.every((e) => idsDisponibles.has(e.plato_id)),
          ),
        )
      }
    },
    [],
  )

  // Refresca nombre/precio de los items y menús con el menú más reciente
  const sincronizarConMenu = useCallback((platos: Plato[], menusHoy?: MenuHoy[]) => {
    const porId = new Map(platos.map((p) => [p.id, p]))
    setItems((prev) =>
      prev.map((i) => {
        const nuevo = porId.get(i.plato.id)
        return nuevo ? { ...i, plato: nuevo } : i
      }),
    )
    if (menusHoy) {
      const menuPorId = new Map(menusHoy.map((m) => [m.id, m]))
      setMenus((prev) =>
        prev.map((m) => {
          const nuevo = menuPorId.get(m.menu.id)
          return nuevo ? { ...m, menu: nuevo } : m
        }),
      )
    }
  }, [])

  const totalItems = useMemo(
    () => items.reduce((s, i) => s + i.cantidad, 0) + menus.reduce((s, m) => s + m.cantidad, 0),
    [items, menus],
  )
  const totalSoles = useMemo(
    () =>
      items.reduce((s, i) => s + i.plato.precio * i.cantidad, 0) +
      menus.reduce((s, m) => s + subtotalMenu(m), 0),
    [items, menus],
  )

  return {
    items,
    menus,
    cambiarCantidad,
    cambiarEmpaque,
    empaqueParaTodos,
    cambiarNota,
    cantidadDe,
    agregarMenu,
    convertirEnMenu,
    cambiarCantidadMenu,
    quitarMenu,
    cambiarEmpaqueMenu,
    cambiarNotaMenu,
    vaciar,
    eliminarNoDisponibles,
    sincronizarConMenu,
    totalItems,
    totalSoles,
  }
}
