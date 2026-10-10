import { useCallback, useMemo, useState } from 'react'
import { subtotalMenu } from '../api'
import type { AgregadoHoy, Bebida, Empaque, Entrega, ItemCarrito, MenuCarrito, MenuHoy, Plato, VarianteMenu } from '../api'
import type { SugerenciaMenu } from '../menuSugerido'

// La opción con la que arranca un tiempo: la primera sin recargo (para
// que "Un menú — S/ 11" cueste eso) o, si todas recargan, la más barata
function eleccionPorDefecto(tiempo: MenuHoy['tiempos'][number]): number {
  const sinRecargo = tiempo.alternativas.find((a) => a.recargo === 0)
  if (sinRecargo) return sinRecargo.plato_id
  return [...tiempo.alternativas].sort((a, b) => a.recargo - b.recargo)[0].plato_id
}

// "Platos por defecto" de la caja: con qué arranca cada persona nueva de
// ESE menú (tiempo_orden → plato_id; los tiempos en "omitidos" no van)
export interface DefectoMenu {
  elecciones: Record<number, number>
  omitidos: number[]
  empaques: Partial<Record<number, Empaque>>
}

/** Reparte en orden: las primeras N[0] posiciones reciben el valor 0,
 *  las siguientes N[1] el valor 1… y el resto queda con `resto`. */
function repartirEnOrden<T>(total: number, cuotas: [T, number][], resto: T): T[] {
  const salida: T[] = []
  for (const [valor, n] of cuotas) for (let i = 0; i < n && salida.length < total; i++) salida.push(valor)
  while (salida.length < total) salida.push(resto)
  return salida
}

// El carrito vive SOLO en el estado del frontend hasta que termina la
// ventana de cancelación; recién ahí se persiste en el backend.
// Tiene dos tipos de línea: platos a la carta (items) y menús encadenados
// ya armados (menus), cada uno con sus elecciones y porciones extra.
/** La persona recién puesta, sin nada tocado (la que arranca el pedido). */
export function menuVacio(m: MenuCarrito): boolean {
  const eligioAlgo = m.menu.tiempos.some(
    (t) => t.alternativas.length > 1 && m.elecciones[t.orden] !== undefined,
  )
  return !(eligioAlgo || m.omitidos.length > 0 || m.extras.length > 0 || m.agregados.length > 0
    || (m.nombre_persona ?? '').trim() !== '' || m.nota.trim() !== ''
    || m.empaque !== 'mesa' || Object.keys(m.empaques).length > 0)
}

export function useCarrito() {
  const [items, setItems] = useState<ItemCarrito[]>([])
  const [menus, setMenus] = useState<MenuCarrito[]>([])
  // Gaseosas de la lista fija (no son platos: no pasan por cocina)
  const [bebidas, setBebidas] = useState<{ bebida: Bebida; cantidad: number }[]>([])

  const cambiarBebida = useCallback((bebida: Bebida, delta: number) => {
    setBebidas((prev) => {
      const existente = prev.find((b) => b.bebida.id === bebida.id)
      if (!existente) return delta > 0 ? [...prev, { bebida, cantidad: delta }] : prev
      const nueva = existente.cantidad + delta
      if (nueva <= 0) return prev.filter((b) => b.bebida.id !== bebida.id)
      return prev.map((b) => (b.bebida.id === bebida.id ? { ...b, cantidad: nueva } : b))
    })
  }, [])

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
      espera: [...(linea.espera ?? [])],
    }))
    setMenus((prev) => [...prev, ...unidades])
  }, [])

  // "Un menú" al toque: entra completo con la opción por defecto de cada
  // tiempo; después el cliente lo afina en su tarjeta si quiere
  // preElegir=true (caja): un toque agrega el menú ya armado con los
  // defaults. preElegir=false (terminal del cliente): los tiempos con
  // varias alternativas quedan como casilleros vacíos y la guía de
  // progreso acompaña la elección — el cliente arma SU menú, no se lleva
  // el default en silencio. Un tiempo con una sola opción viene incluido.
  // `defecto` (caja): los "platos por defecto" configurados; un plato que
  // hoy no está en las alternativas se ignora (cae a la regla de siempre)
  const agregarMenuCompleto = useCallback((menu: MenuHoy, preElegir = true, defecto?: DefectoMenu) => {
    const elecciones: Record<number, number> = {}
    const omitidos: number[] = []
    const empaques: Partial<Record<number, Empaque>> = {}
    for (const t of menu.tiempos) {
      if (t.alternativas.length === 0) continue
      if (defecto?.omitidos.includes(t.orden)) {
        omitidos.push(t.orden)
        continue
      }
      const preferido = defecto?.elecciones[t.orden]
      if (preferido !== undefined && t.alternativas.some((a) => a.plato_id === preferido)) {
        elecciones[t.orden] = preferido
      } else if (
        // Sin default para este tiempo, o el default ya no está hoy (cargaron
        // otro menú): regla de siempre
        (preElegir && (!defecto || preferido !== undefined)) || t.alternativas.length === 1
      ) {
        elecciones[t.orden] = eleccionPorDefecto(t)
      }
      const empaque = defecto?.empaques[t.orden]
      if (empaque && empaque !== 'mesa') empaques[t.orden] = empaque
    }
    setMenus((prev) => [...prev, {
      menu, cantidad: 1, elecciones, extras: [], omitidos, agregados: [],
      empaque: 'mesa' as Empaque, empaques, nota: '',
    }])
  }, [])

  // El "−" de la barra de personas: saca la última tarjeta de ese menú
  const quitarUltimoMenu = useCallback((menuId: number) => {
    setMenus((prev) => {
      const ultimo = prev.map((m) => m.menu.id).lastIndexOf(menuId)
      if (ultimo === -1) return prev
      // Una tarjeta con cantidad 2 ("＋ Más") son dos personas: baja una
      if (prev[ultimo].cantidad > 1) {
        return prev.map((m, i) => (i === ultimo ? { ...m, cantidad: m.cantidad - 1 } : m))
      }
      return prev.filter((_, i) => i !== ultimo)
    })
  }, [])

  // ---------- Para todas las personas de un menú ----------

  // "A todas": el mismo plato en ese tiempo para todas las tarjetas del
  // menú. platoId null = todas "sin elegir"
  const eleccionATodos = useCallback((menuId: number, tiempoOrden: number, platoId: number | null) => {
    setMenus((prev) => prev.map((m) => {
      if (m.menu.id !== menuId) return m
      const elecciones = { ...m.elecciones }
      if (platoId === null) delete elecciones[tiempoOrden]
      else elecciones[tiempoOrden] = platoId
      return { ...m, elecciones, omitidos: m.omitidos.filter((o) => o !== tiempoOrden) }
    }))
  }, [])

  // "Nadie lleva sopa": quita el tiempo en todas las tarjetas del menú
  const omitirATodos = useCallback((menuId: number, tiempoOrden: number) => {
    setMenus((prev) => prev.map((m) => {
      if (m.menu.id !== menuId || m.omitidos.includes(tiempoOrden)) return m
      const elecciones = { ...m.elecciones }
      delete elecciones[tiempoOrden]
      return {
        ...m, elecciones,
        omitidos: [...m.omitidos, tiempoOrden],
        extras: m.extras.filter((e) => e.tiempo_orden !== tiempoOrden),
        espera: (m.espera ?? []).filter((t) => t !== tiempoOrden),
      }
    }))
  }, [])

  // Repartir (50/50, 6 sopa / 4 entrada…): en orden de tarjetas, las
  // primeras reciben la primera opción y así; las que sobran quedan sin elegir
  const repartirEleccion = useCallback(
    (menuId: number, tiempoOrden: number, cuotas: [number, number][]) => {
      setMenus((prev) => {
        const total = prev.filter((m) => m.menu.id === menuId).length
        const plan = repartirEnOrden<number | null>(total, cuotas, null)
        let k = 0
        return prev.map((m) => {
          if (m.menu.id !== menuId) return m
          const platoId = plan[k++]
          const elecciones = { ...m.elecciones }
          if (platoId === null) delete elecciones[tiempoOrden]
          else elecciones[tiempoOrden] = platoId
          return { ...m, elecciones, omitidos: m.omitidos.filter((o) => o !== tiempoOrden) }
        })
      })
    },
    [],
  )

  // Repartir el empaque de un tiempo (3 en mesa, 2 en táper) entre las
  // tarjetas que llevan ese plato elegido
  const repartirEmpaque = useCallback(
    (menuId: number, tiempoOrden: number, cuotas: [Empaque, number][]) => {
      setMenus((prev) => {
        // Solo cuentan las personas que tienen ese plato elegido: a una
        // "sin elegir" el táper no le llegaría a ningún plato
        const indices = prev
          .map((m, i) => ({ m, i }))
          .filter(({ m }) =>
            m.menu.id === menuId && !m.omitidos.includes(tiempoOrden) &&
            m.elecciones[tiempoOrden] !== undefined)
          .map(({ i }) => i)
        const plan = repartirEnOrden<Empaque>(indices.length, cuotas, 'mesa')
        const asignado = new Map(indices.map((i, k) => [i, plan[k]]))
        return prev.map((m, i) => {
          const empaque = asignado.get(i)
          if (empaque === undefined) return m
          const empaques = { ...m.empaques }
          if (empaque === m.empaque) delete empaques[tiempoOrden]
          else empaques[tiempoOrden] = empaque
          return { ...m, empaques }
        })
      })
    },
    [],
  )

  // Dejar un tiempo "sin elegir" en UNA persona (el ticket sale igual y lo dice)
  const quitarEleccion = useCallback((idx: number, tiempoOrden: number) => {
    setMenus((prev) => prev.map((m, i) => {
      if (i !== idx) return m
      const elecciones = { ...m.elecciones }
      delete elecciones[tiempoOrden]
      return {
        ...m, elecciones,
        omitidos: m.omitidos.filter((o) => o !== tiempoOrden),
        espera: (m.espera ?? []).filter((t) => t !== tiempoOrden),
      }
    }))
  }, [])

  // "✓ Aplicar por defecto": pone los platos por defecto a TODAS las
  // personas de ese menú, en su sitio (no borra nombre, nota ni agregados).
  // Un default que hoy no está en el menú no toca ese tiempo.
  const aplicarDefecto = useCallback((menuId: number, defecto: DefectoMenu) => {
    setMenus((prev) => prev.map((m) => {
      if (m.menu.id !== menuId) return m
      const elecciones = { ...m.elecciones }
      let omitidos = [...m.omitidos]
      const empaques = { ...m.empaques }
      for (const t of m.menu.tiempos) {
        if (defecto.omitidos.includes(t.orden)) {
          delete elecciones[t.orden]
          if (!omitidos.includes(t.orden)) omitidos.push(t.orden)
          continue
        }
        const preferido = defecto.elecciones[t.orden]
        if (preferido !== undefined && t.alternativas.some((a) => a.plato_id === preferido)) {
          elecciones[t.orden] = preferido
          omitidos = omitidos.filter((o) => o !== t.orden)
        }
        const empaque = defecto.empaques[t.orden]
        if (empaque) {
          if (empaque === m.empaque) delete empaques[t.orden]
          else empaques[t.orden] = empaque
        }
      }
      return {
        ...m, elecciones, omitidos, empaques,
        extras: m.extras.filter((e) => !omitidos.includes(e.tiempo_orden)),
        espera: (m.espera ?? []).filter((t) => elecciones[t] !== undefined),
      }
    }))
  }, [])

  // Nombre opcional de la persona del ticket ("Juan")
  const cambiarNombreMenu = useCallback((idx: number, nombre: string) => {
    setMenus((prev) => prev.map((m, i) => (i === idx ? { ...m, nombre_persona: nombre } : m)))
  }, [])

  // Entrega POR PERSONA: todo junto o por tiempos
  const cambiarEntregaMenu = useCallback((idx: number, entrega: Entrega) => {
    setMenus((prev) => prev.map((m, i) => (i === idx ? { ...m, entrega } : m)))
  }, [])

  // Circulito "va a esperar" (reservado) de un tiempo de un menú
  const alternarEspera = useCallback((idx: number, tiempoOrden: number) => {
    setMenus((prev) => prev.map((m, i) => {
      if (i !== idx) return m
      const espera = m.espera ?? []
      return {
        ...m,
        espera: espera.includes(tiempoOrden)
          ? espera.filter((t) => t !== tiempoOrden)
          : [...espera, tiempoOrden],
      }
    }))
  }, [])

  // Cambiar el plato de un tiempo del menú idx (y des-quitarlo si estaba quitado)
  const cambiarEleccion = useCallback((idx: number, tiempoOrden: number, platoId: number) => {
    setMenus((prev) => prev.map((m, i) => {
      if (i !== idx) return m
      // Otro plato: la presa y los "sin…" eran de ese plato (el huevo sí
      // se queda: vale para cualquier segundo)
      const variantes = { ...(m.variantes ?? {}) }
      const v = variantes[tiempoOrden]
      if (v && m.elecciones[tiempoOrden] !== platoId) {
        if (v.huevo) variantes[tiempoOrden] = { huevo: true, ...(v.coccion ? { coccion: v.coccion } : {}) }
        else delete variantes[tiempoOrden]
      }
      return {
        ...m,
        elecciones: { ...m.elecciones, [tiempoOrden]: platoId },
        omitidos: m.omitidos.filter((o) => o !== tiempoOrden),
        variantes,
      }
    }))
  }, [])

  // Presa de pollo / cambio a 2 huevos fritos de UN plato de UNA persona.
  // null borra la variante (vuelve "como viene")
  const cambiarVariante = useCallback((idx: number, tiempoOrden: number, variante: VarianteMenu | null) => {
    setMenus((prev) => prev.map((m, i) => {
      if (i !== idx) return m
      const variantes = { ...(m.variantes ?? {}) }
      if (variante && (variante.huevo || variante.presa || (variante.opciones ?? []).length > 0)) {
        variantes[tiempoOrden] = variante
      }
      else delete variantes[tiempoOrden]
      return { ...m, variantes }
    }))
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
        espera: [...(original.espera ?? [])],
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
  // Desde la hoja de empaque: entrada y segundo de TODAS las personas de
  // ese menú en el mismo empaque (se borran las excepciones por plato)
  // "Todas las entradas en bolsa": ESE tiempo de todas las personas del
  // menú, hayan elegido su plato o no (al elegirlo, ya va en ese empaque).
  // Antes solo contaban las que ya tenían plato y con una sola elegida no
  // aparecía el botón (pedido del dueño)
  const empaqueTiempoATodas = useCallback((menuId: number, tiempoOrden: number, empaque: Empaque) => {
    setMenus((prev) => prev.map((m) => {
      if (m.menu.id !== menuId || m.omitidos.includes(tiempoOrden)) return m
      const empaques = { ...m.empaques }
      if (empaque === m.empaque) delete empaques[tiempoOrden]
      else empaques[tiempoOrden] = empaque
      return { ...m, empaques }
    }))
  }, [])

  const empaqueMenuParaTodas = useCallback((menuId: number, empaque: Empaque) => {
    setMenus((prev) => prev.map((m) => (m.menu.id === menuId ? { ...m, empaque, empaques: {} } : m)))
  }, [])

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

  // Pedido por voz: los tickets que la terminal abrió solos y nadie tocó
  // (sin plato elegido donde había opción, sin nombre, nota ni cambios)
  // se van, para que lo dictado no quede junto a una "Persona 1" vacía
  const quitarMenusVacios = useCallback(() => {
    setMenus((prev) => prev.filter((m) => !menuVacio(m)))
  }, [])

  const vaciar = useCallback(() => {
    setItems([])
    setMenus([])
    setBebidas([])
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
          // Un plato que se sacó del menú de hoy (o se agotó) deja ese tiempo
          // "sin elegir" a la vista, en vez de una elección escondida que el
          // backend rechazaría con 409 una y otra vez
          const vale = (t: number, platoId: number) =>
            nuevo.tiempos.find((x) => x.orden === t)?.alternativas.some((a) => a.plato_id === platoId) ?? false
          const elecciones = Object.fromEntries(
            Object.entries(m.elecciones).filter(([t, p]) => vale(Number(t), p)),
          ) as Record<number, number>
          return {
            ...m,
            menu: nuevo,
            elecciones,
            extras: m.extras.filter((e) => vale(e.tiempo_orden, e.plato_id)),
            espera: (m.espera ?? []).filter((t) => elecciones[t] !== undefined),
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
    () => items.reduce((s, i) => s + i.cantidad, 0) + menus.reduce((s, m) => s + m.cantidad, 0)
      + bebidas.reduce((s, b) => s + b.cantidad, 0),
    [items, menus, bebidas],
  )
  const totalSoles = useMemo(
    () =>
      items.reduce((s, i) => s + i.plato.precio * i.cantidad, 0) +
      menus.reduce((s, m) => s + subtotalMenu(m), 0) +
      bebidas.reduce((s, b) => s + b.bebida.precio * b.cantidad, 0),
    [items, menus, bebidas],
  )

  return {
    items,
    menus,
    bebidas,
    cambiarBebida,
    cambiarCantidad,
    cambiarEmpaque,
    empaqueParaTodos,
    cambiarNota,
    cantidadDe,
    agregarMenu,
    agregarMenuCompleto,
    quitarUltimoMenu,
    eleccionATodos,
    omitirATodos,
    repartirEleccion,
    repartirEmpaque,
    cambiarEntregaMenu,
    alternarEspera,
    quitarEleccion,
    cambiarNombreMenu,
    aplicarDefecto,
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
    quitarMenusVacios,
    empaqueMenuParaTodas,
    empaqueTiempoATodas,
    cambiarVariante,
    eliminarNoDisponibles,
    sincronizarConMenu,
    totalItems,
    totalSoles,
  }
}
