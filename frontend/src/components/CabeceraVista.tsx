import type { JSX, ReactNode } from 'react'
import {
  IconoAjustes, IconoCirculoAspa, IconoDisco, IconoFrasco, IconoMicrofono,
  IconoMoneda, IconoPizarra, IconoTablero, IconoTicket,
} from './Iconos'

export type Tab = 'tablero' | 'resumen' | 'menu' | 'ordenes' | 'insumos' | 'finanzas'
  | 'cancelaciones' | 'voz' | 'config'

/**
 * Las 9 secciones del admin. Cada una tiene SU color, y ese color se
 * repite en el rail, en la versalita del título y en el borde de las
 * tarjetas de esa vista: el dueño sabe dónde está parado por el color,
 * sin tener que leer la pestaña.
 */
export const SECCIONES: {
  id: Tab
  rotulo: string        // lo que dice el rail (corto)
  versalita: string     // la línea chica sobre el título
  titulo: string        // el título grande de la vista
  Icono: (p: { tam?: number }) => JSX.Element
}[] = [
  { id: 'tablero', rotulo: 'Tablero', versalita: 'El negocio', titulo: 'Tablero', Icono: IconoTablero },
  { id: 'resumen', rotulo: 'Resumen', versalita: 'El día', titulo: 'Cómo va la fonda', Icono: IconoDisco },
  { id: 'menu', rotulo: 'Menú', versalita: 'La pizarra', titulo: 'Menú del día', Icono: IconoPizarra },
  { id: 'ordenes', rotulo: 'Órdenes', versalita: 'Movimiento', titulo: 'Órdenes del día', Icono: IconoTicket },
  { id: 'insumos', rotulo: 'Insumos', versalita: 'Despensa', titulo: 'Insumos y recetas', Icono: IconoFrasco },
  { id: 'finanzas', rotulo: 'Finanzas', versalita: 'La plata', titulo: 'Finanzas', Icono: IconoMoneda },
  { id: 'cancelaciones', rotulo: 'Canceladas', versalita: 'Ventana de cancelación', titulo: 'Pedidos cancelados', Icono: IconoCirculoAspa },
  { id: 'voz', rotulo: 'Voz', versalita: 'Pedido por voz', titulo: 'Qué escuchó el sistema', Icono: IconoMicrofono },
  { id: 'config', rotulo: 'Ajustes', versalita: 'Configuración', titulo: 'El local y el salón', Icono: IconoAjustes },
]

/**
 * La cabecera de cada vista: versalita subrayada con el color de la
 * sección, título en serif y, a la derecha, los controles propios de
 * esa pantalla (períodos, CSV, fecha…).
 */
export function CabeceraVista({ id, children }: { id: Tab; children?: ReactNode }) {
  const seccion = SECCIONES.find((s) => s.id === id) ?? SECCIONES[0]
  return (
    <div className="ad-cabecera-vista">
      <div className="ad-titulo-vista">
        <span className={`ad-versalita ad-color-${id}`}>{seccion.versalita}</span>
        <h1>{seccion.titulo}</h1>
      </div>
      {children && <div className="ad-controles-vista">{children}</div>}
    </div>
  )
}
