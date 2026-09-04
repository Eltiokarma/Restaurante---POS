import { useCallback, useMemo, useState } from 'react'
import { subtotalMenu } from '../api'
import type { AgregadoHoy, Empaque, ItemCarrito, MenuCarrito, MenuHoy, Plato } from '../api'
import type { SugerenciaMenu } from '../menuSugerido'

// La opción con la que arranca un tiempo: la primera sin recargo (para
// que "Un menú — S/ 11" cueste eso) o, si todas recargan, la más barata
function eleccionPorDefecto(tiempo: MenuHoy['tiempos'][number]): number {
  const sinRecargo = tiempo.alternativas.find((a) => a.recargo === 0)
  if (sinRecargo) return sinRecargo.plato_id
  return [...tiempo.alternativas].sort((a, b) => a.recargo - b.recargo)[0].plato_id
}

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
    setMenus((prev) => prev.map((m) => ({ ...m, empaque, empaques: {} })))
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

  // Cada menú entra como SU PROPIA línea (no se juntan iguales): el
  // cliente ve "Menú 1, Menú 2…" y edita cada uno por separado. Un armado
  // "para 4" entra como 4 tarjetas independientes por la misma razón.
  const agregarMenu = useCallback((linea: MenuCarrito) => {
    // Los extras y agregados NO se multiplican por la cantidad (así lo
    // muestra el botón del armado): al partir van solo en la primera unidad
    const unidades = Array.from({ length: Math.max(1, linea.cantidad) }, (_, n) => ({
      ...linea,
      cantidad: 1,
      elecciones: { ...linea.elecciones },
      extras: n === 0 ? linea.extras.map((e) => ({ ...e })) : [],
      omitidos: [...linea.omitidos],
      agregados: n === 0 ? linea.agregados.map((a) => ({ ...a })) : [],
      empaques: { ...linea.empaques },
    }))
    setMenus((prev) => [...prev, ...unidades])
  }, [])

  // "Un menú" al toque: entra completo con la opción por defecto de cada
  // tiempo; después el cliente lo afina en su tarjeta si quiere
  const agregarMenuCompleto = useCallback((menu: MenuHoy) => {
    const elecciones: Record<number, number> = {}
    for (const t of menu.tiempos) {
      if (t.alternativas.length > 0) elecciones[t.orden] = eleccionPorDefecto(t)
    }
    setMenus((prev) => [...prev, {
      menu, cantidad: 1, elecciones, extras: [], omitidos: [], agregados: [],
      empaque: 'mesa' as Empaque, empaques: {}, nota: '',
    }])
  }, [])

  // Cambiar el plato de un tiempo del menú idx (y des-quitarlo si estaba quitado)
  const cambiarEleccion = useCallback((idx: number, tiempoOrden: number, platoId: number) => {
    setMenus((prev) => prev.map((m, i) => (i === idx ? {
      ...m,
      elecciones: { ...m.elecciones, [tiempoOrden]: platoId },
      omitidos: m.omitidos.filter((o) => o !== tiempoOrden),
    } : m)))
  }, [])

  // "Sin sopa": quitar (o devolver) un tiempo del menú idx. Al devolverlo
  // vuelve con la primera alternativa elegida (quitarlo borró la elección):
  // sin esto, un tiempo obligatorio quedaría sin elegir y el backend
  // rechazaría el pedido recién al confirmar
  const alternarOmitido = useCallback((idx: number, tiempoOrden: number) => {
    setMenus((prev) => prev.map((m, i) => {
      if (i !== idx) return m
      if (m.omitidos.includes(tiempoOrden)) {
        const elecciones = { ...m.elecciones }
        const tiempo = m.menu.tiempos.find((t) => t.orden === tiempoOrden)
        if (!(tiempoOrden in elecciones) && tiempo && tiempo.alternativas.length > 0) {
          elecciones[tiempoOrden] = eleccionPorDefecto(tiempo)
        }
        return { ...m, elecciones, omitidos: m.omitidos.filter((o) => o !== tiempoOrden) }
      }
      const elecciones = { ...m.elecciones }
      delete elecciones[tiempoOrden]
      return {
        ...m,
        elecciones,
        omitidos: [...m.omitidos, tiempoOrden],
        // Sus porciones extra se van con él: quedarían cobrándose sin chip a la vista
        extras: m.extras.filter((e) => e.tiempo_orden !== tiempoOrden),
      }
    }))
  }, [])

  // +1 presa / −1 presa en el menú idx
  const cambiarAgregado = useCallback((idx: number, agregado: AgregadoHoy, delta: number) => {
    setMenus((prev) => prev.map((m, i) => {
      if (i !== idx) return m
      const pos = m.agregados.findIndex((a) => a.agregado.id === agregado.id)
      if (pos === -1) {
        return delta > 0 ? { ...m, agregados: [...m.agregados, { agregado, cantidad: delta }] } : m
      }
      const cantidad = m.agregados[pos].cantidad + delta
      const agregados = cantidad <= 0
        ? m.agregados.filter((_, j) => j !== pos)
        : m.agregados.map((a, j) => (j === pos ? { ...a, cantidad } : a))
      return { ...m, agregados }
    }))
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
      menu: s.menu, cantidad: 1, elecciones: s.elecciones, extras: [],
      omitidos: [], agregados: [], empaque, empaques: {}, nota,
    }])
    setItems((prev) =>
      prev
        .map((i) => (s.platosUsados.includes(i.plato.id) ? { ...i, cantidad: i.cantidad - 1 } : i))
        .filter((i) => i.cantidad > 0),
    )
  }, [items])

  // "+ Otro igual": copia la línea entera (elecciones, quitados, agregados,
  // extras, nota) como una tarjeta nueva — cantidad+1 no duplicaría los
  // agregados, que van por línea y no por unidad
  const duplicarMenu = useCallback((idx: number) => {
    setMenus((prev) => {
      const original = prev[idx]
      if (!original) return prev
      const copia: MenuCarrito = {
        ...original,
        cantidad: 1,
        elecciones: { ...original.elecciones },
        omitidos: [...original.omitidos],
        agregados: original.agregados.map((a) => ({ ...a })),
        extras: original.extras.map((e) => ({ ...e })),
        empaques: { ...original.empaques },
      }
      return [...prev.slice(0, idx + 1), copia, ...prev.slice(idx + 1)]
    })
  }, [])

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

  // "Todo el menú en X" borra los empaques por tiempo: el general manda
  const cambiarEmpaqueMenu = useCallback((idx: number, empaque: Empaque) => {
    setMenus((prev) => prev.map((m, i) => (i === idx ? { ...m, empaque, empaques: {} } : m)))
  }, [])

  // "La sopa en bolsa": empaque de UN tiempo de UN menú. Elegir el mismo
  // del menú borra el override (no es una excepción real)
  const cambiarEmpaqueTiempo = useCallback((idx: number, tiempoOrden: number, empaque: Empaque) => {
    setMenus((prev) => prev.map((m, i) => {
      if (i !== idx) return m
      const empaques = { ...m.empaques }
      if (empaque === m.empaque) delete empaques[tiempoOrden]
      else empaques[tiempoOrden] = empaque
      return { ...m, empaques }
    }))
  }, [])

  // Porción extra ("una entrada más a S/ 3") desde la tarjeta del menú
  const cambiarExtraMenu = useCallback(
    (idx: number, tiempoOrden: number, platoId: number, delta: number) => {
      setMenus((prev) => prev.map((m, i) => {
        if (i !== idx) return m
        const pos = m.extras.findIndex((e) => e.tiempo_orden === tiempoOrden && e.plato_id === platoId)
        if (pos === -1) {
          return delta > 0
            ? { ...m, extras: [...m.extras, { tiempo_orden: tiempoOrden, plato_id: platoId, cantidad: delta }] }
            : m
        }
        const cantidad = m.extras[pos].cantidad + delta
        const extras = cantidad <= 0
          ? m.extras.filter((_, j) => j !== pos)
          : m.extras.map((e, j) => (j === pos ? { ...e, cantidad } : e))
        return { ...m, extras }
      }))
    },
    [],
  )

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
          if (!nuevo) return m
          const tiempos = new Set(nuevo.tiempos.map((t) => t.orden))
          return {
            ...m,
            menu: nuevo,
            omitidos: m.omitidos.filter((o) => tiempos.has(o)),
            empaques: Object.fromEntries(
              Object.entries(m.empaques).filter(([k]) => tiempos.has(Number(k))),
            ),
            agregados: m.agregados.flatMap((a) => {
              const vigente = nuevo.agregados.find((x) => x.id === a.agregado.id)
              return vigente ? [{ ...a, agregado: vigente }] : []
            }),
          }
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
    agregarMenuCompleto,
    cambiarEleccion,
    alternarOmitido,
    cambiarAgregado,
    duplicarMenu,
    convertirEnMenu,
    cambiarCantidadMenu,
    quitarMenu,
    cambiarEmpaqueMenu,
    cambiarEmpaqueTiempo,
    cambiarExtraMenu,
    cambiarNotaMenu,
    vaciar,
    eliminarNoDisponibles,
    sincronizarConMenu,
    totalItems,
    totalSoles,
  }
}
