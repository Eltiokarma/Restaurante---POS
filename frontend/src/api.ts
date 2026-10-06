// Cliente HTTP mínimo para la API del backend.

export interface Plato {
  id: number
  nombre: string
  categoria: string
  precio: number
  activo_hoy: boolean
  sale_al_momento: boolean
  // Porciones que entran por tanda en cocina (0 = sin límite)
  capacidad_tanda: number
  // Nombre de archivo de la foto (servida por el backend); null = sin foto
  foto: string | null
  sinonimos: string[]
}

export function urlFotoPlato(foto: string): string {
  return `/api/menu/fotos/${foto}`
}

export type Entrega = 'junto' | 'separado'

export const NOMBRE_ENTREGA: Record<Entrega, { titulo: string; detalle: string }> = {
  junto: { titulo: '🍽 Todo junto', detalle: 'una sola entrega' },
  separado: { titulo: '⏱ Separado', detalle: 'por tiempos, según salga' },
}

export type Empaque = 'mesa' | 'taper' | 'bolsa' | 'lonchera'

export const EMPAQUES: Empaque[] = ['mesa', 'taper', 'bolsa', 'lonchera']

export const NOMBRE_EMPAQUE: Record<Empaque, string> = {
  // "Mesa" chocaba con la selección de mesa de al lado (hallazgo 34):
  // este empaque significa "se come acá, en vajilla", no pide número
  mesa: '🍽 Comer acá',
  taper: '🥡 Táper',
  bolsa: '🛍 Bolsa',
  lonchera: '🍱 Lonchera',
}

export interface ItemCarrito {
  plato: Plato
  cantidad: number
  empaque: Empaque
  nota: string
}

// ---------- Menú encadenado (§1): el menú como unidad de venta ----------

export interface MenuAlternativaHoy {
  plato_id: number
  nombre: string
  precio: number
  recargo: number
  sale_al_momento: boolean
}

export interface MenuTiempoHoy {
  orden: number
  rotulo: string
  obligatorio: boolean
  // Precio de UNA porción adicional pedida con el menú (0 = no se ofrece)
  precio_extra: number
  // Cuánto baja el menú si el cliente quita este tiempo (0 = no baja)
  descuento_si_se_quita: number
  alternativas: MenuAlternativaHoy[]
}

// Porción suelta que se suma a un menú: + presa, + refresco, + arroz…
export interface AgregadoHoy {
  id: number
  nombre: string
  precio: number
}

export interface MenuHoy {
  id: number
  nombre: string
  precio: number
  tiempos: MenuTiempoHoy[]
  agregados: AgregadoHoy[]
}

export interface ExtraMenu {
  tiempo_orden: number
  plato_id: number
  cantidad: number
}

// Cómo quiere ESE plato: presa de pollo, o la proteína cambiada por 2
// huevos fritos (mismo precio) y su cocción. Nada elegido = como viene
// (y no se imprime nada)
export type Presa = 'pecho' | 'pierna' | 'ala' | 'encuentro'
export type CoccionHuevo = 'inglesa' | 'bien_frito'
export interface VarianteMenu {
  presa?: Presa
  huevo?: boolean
  coccion?: CoccionHuevo
  // "Sin puré", "Jugoso"… (claves de OPCIONES_PLATO)
  opciones?: string[]
}

/** Cambios rápidos de un plato. Mismas claves que el backend. */
export const OPCIONES_PLATO: Record<string, string> = {
  sin_pure: 'Sin puré', sin_lentejas: 'Sin lentejas', sin_ensalada: 'Sin ensalada',
  sin_frejoles: 'Sin frejoles', sin_arroz: 'Sin arroz', poco_arroz: 'Poco arroz',
  sin_papas: 'Sin papas', sin_jugo: 'Sin jugo', jugoso: 'Jugoso', sin_aji: 'Sin ají',
  sin_cebolla: 'Sin cebolla',
}
// Pares que se excluyen: marcar uno quita el otro
export const OPCIONES_OPUESTAS: Record<string, string> = {
  sin_jugo: 'jugoso', jugoso: 'sin_jugo', sin_arroz: 'poco_arroz', poco_arroz: 'sin_arroz',
}

const sinTildes = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()

/** Qué cambios ofrecer según el nombre del plato (pedido del dueño: los
 *  que lleve; el segundo además "sin ají" y, si es de salsa, jugo). */
export function opcionesDePlato(nombre: string, esSegundo: boolean): string[] {
  const n = sinTildes(nombre)
  const lleva = (x: string) => n.includes(x) && !n.startsWith(x)
  const salida: string[] = []
  if (lleva('pure')) salida.push('sin_pure')
  if (lleva('lenteja')) salida.push('sin_lentejas')
  if (lleva('ensalada')) salida.push('sin_ensalada')
  if (lleva('frejol') || lleva('frijol')) salida.push('sin_frejoles')
  if (lleva('papa')) salida.push('sin_papas')
  if (n.includes('arroz')) salida.push('poco_arroz', 'sin_arroz')
  if (esSegundo) {
    if (/saltad|estofad|seco|cau cau|aji de gallina|tallarin|olla|guiso|locro|chanfainita|carapulcra|adobo|picante|asado|menestr/.test(n)) {
      salida.push('jugoso', 'sin_jugo')
    }
    if (/saltad|seco|sarsa|criolla/.test(n)) salida.push('sin_cebolla')
    salida.push('sin_aji')
  }
  return salida
}
export const NOMBRE_PRESA: Record<Presa, string> = { pecho: 'Pecho', pierna: 'Pierna', ala: 'Ala', encuentro: 'Encuentro' }
export const NOMBRE_COCCION: Record<CoccionHuevo, string> = { inglesa: 'A la inglesa', bien_frito: 'Bien frito' }

/** ¿Se le elige presa? Los platos con "pollo" en el nombre (dueño). */
export function llevaPollo(nombre: string): boolean {
  return nombre.toLowerCase().includes('pollo')
}

/** Texto corto de la variante para el ticket en pantalla. */
export function textoVariante(v?: VarianteMenu): string {
  if (!v) return ''
  const partes: string[] = []
  if (v.huevo) partes.push(`🍳 2 huevos${v.coccion ? ` · ${NOMBRE_COCCION[v.coccion].toLowerCase()}` : ''}`)
  else if (v.presa) partes.push(`🍗 ${NOMBRE_PRESA[v.presa]}`)
  for (const o of v.opciones ?? []) if (OPCIONES_PLATO[o]) partes.push(OPCIONES_PLATO[o].toLowerCase())
  return partes.join(' · ')
}

// Un menú armado dentro del carrito (elecciones ya resueltas)
export interface MenuCarrito {
  menu: MenuHoy
  cantidad: number
  elecciones: Record<number, number> // tiempo_orden → plato_id
  extras: ExtraMenu[]
  omitidos: number[] // tiempos quitados ("sin sopa")
  agregados: { agregado: AgregadoHoy; cantidad: number }[] // +1 presa…
  empaque: Empaque
  // Empaque POR TIEMPO ("la sopa en bolsa, el segundo en lonchera");
  // un tiempo que no esté aquí usa el empaque general del menú
  empaques: Partial<Record<number, Empaque>>
  nota: string
  // Cada persona (menú) sale "todo junto" o "por tiempos"; sin valor =
  // automático (por tiempos si lleva un plato al momento)
  entrega?: Entrega
  // Tiempos "va a esperar" (reservados): cocina no los saca aún (caja)
  espera?: number[]
  // Nombre opcional de la persona ("Juan"): sale en la comanda de cocina
  nombre_persona?: string
  // tiempo_orden → presa / cambio a huevo
  variantes?: Partial<Record<number, VarianteMenu>>
}

// Estado POR ÍTEM (§3): la cocina tacha porciones, no tickets enteros
export type EstadoItem = 'pendiente' | 'preparando' | 'listo' | 'entregado'

export interface OrdenItemOut {
  id?: number
  // Presa o cambio a huevo ("PIERNA", "2 HUEVOS … EN VEZ DE CARNE"); "" = como viene
  detalle?: string
  // Línea de cobro (ej. "Táper × 3"): al total y al ticket, no a cocina
  es_cargo?: boolean
  // Categoría del plato (null si el plato salió del catálogo): cocina
  // esconde las bebidas, que no se preparan
  categoria?: string | null
  nombre: string
  precio: number
  cantidad: number
  empaque: Empaque
  nota: string
  estado: EstadoItem
  subtotal: number
}

export interface OrdenMenuItemOut extends OrdenItemOut {
  tiempo_orden: number | null
  es_extra: boolean
  es_agregado: boolean
  // "Va a esperar": reservado, cocina no lo saca todavía
  espera?: boolean
}

export interface OrdenMenuOut {
  nombre: string
  precio: number
  cantidad: number
  nota: string
  subtotal: number
  // Tiempos que el cliente quitó ("Sin sopa"), con el descuento aplicado
  omitidos: { rotulo: string; descuento: number; tiempo_orden?: number }[]
  id?: number
  menu_id?: number | null
  // Tiempos que la persona aún no eligió (salen "SIN ELEGIR")
  pendientes?: string[]
  pendientes_detalle?: { tiempo_orden: number; rotulo: string }[]
  // Entrega de ESTE menú (cada persona la suya)
  entrega?: Entrega
  // Nombre opcional de la persona
  nombre_persona?: string
  items: OrdenMenuItemOut[]
}

export interface OrdenOut {
  id: number
  numero_orden_dia: number
  fecha: string
  hora: string
  total: number
  estado: string
  tipo_servicio: TipoServicio
  // tactil | voz | mixto, o "manual" (venta anotada a mano en finanzas)
  origen?: OrigenPedido | 'manual'
  metodo_pago: MetodoPago | null
  // "Falta pagar": salió el ticket, la plata no entró todavía
  pago_pendiente?: boolean
  // "OK y pagó" / "OK y no pagó" al crear el pedido en la terminal
  pago_al_pedir?: 'pagado' | 'pendiente' | null
  // "Falta vuelto": pagó de más; monto que se le debe (null = nada)
  vuelto_pendiente?: number | null
  entrega: Entrega
  // Comandas que se imprimen (2 = una extra para la guía)
  copias?: number
  mesa_ids: number[]
  mesas: string[]
  mesa_liberada: boolean
  minutos_espera: number
  // Cuánto tardó el ticket en salir completo (min); null = aún no sale
  servido_min?: number | null
  // Segundos desde que se anuló (cintillo "no preparar" en cocina); null si no aplica
  anulada_hace_seg: number | null
  // Solo la venta a la carta; los platos de menú van agrupados en "menus"
  items: OrdenItemOut[]
  menus: OrdenMenuOut[]
}

export type TipoServicio = 'sala' | 'llevar' | 'mixto'

export const NOMBRE_SERVICIO: Record<TipoServicio, string> = {
  sala: '🍽 En sala',
  llevar: '🛍 Para llevar',
  mixto: '🥡 Mixto',
}

export type MetodoPago = 'efectivo' | 'tarjeta' | 'yape'

export const NOMBRE_PAGO: Record<MetodoPago, string> = {
  efectivo: '💵 Efectivo',
  tarjeta: '💳 Tarjeta',
  yape: '📱 Yape',
}

export interface Insumo {
  id: number
  nombre: string
  unidad: string
  stock_actual: number
  // Avisar cuando el stock baje de aquí; 0 = sin aviso configurado
  stock_minimo: number
  bajo_minimo: boolean
  costo_unitario: number
  valor: number
  activo: boolean
}

// Tickets que llevan rato sin imprimirse (la ticketera o el puente se colgaron)
export interface ImpresionPendiente {
  cantidad: number
  minutos: number
}

// Cuánto movimiento hay en la base, para el borrado de datos de prueba
export interface ResumenDatos {
  ordenes: number
  cancelaciones: number
  cierres_caja: number
  movimientos_kardex: number
  voz_logs: number
}

export interface MovimientoKardex {
  id: number
  fecha: string
  hora: string
  insumo: string
  unidad: string
  tipo: string
  cantidad: number
  costo_total: number | null
  referencia: string
}

export interface RecetaDetalle {
  plato_id: number
  items: { insumo_id: number; insumo: string; unidad: string; cantidad: number }[]
  costo_porcion: number
}

export interface CajaEstado {
  abierta: boolean
  cerrada: boolean
  ventas_efectivo: number
  ventas_tarjeta: number
  ventas_yape: number
  sin_registrar: number
  ventas_despues_del_cierre: boolean
  // Número de caja dentro del día (1 = la primera; puede haber varias)
  turno?: number
  // Total de egresos del turno (vivo con caja abierta; snapshot al cierre)
  egresos?: number
  // Tickets marcados "falta pagar" (plata que no entró) y vueltos por dar
  // (plata de más en el cajón); vivos con caja abierta, snapshot al cierre
  por_cobrar?: number
  vueltos_pendientes?: number
  fecha?: string
  hora_apertura?: string
  monto_apertura?: number
  hora_cierre?: string | null
  monto_contado?: number | null
  total_sistema?: number | null
  diferencia?: number | null
  // Signo y magnitud separados, para mostrar el descuadre como cifra grande
  descuadre?: { tipo: 'exacta' | 'sobra' | 'falta'; monto: number } | null
  notas?: string
  total_vendido: number
}

export interface EgresoOut {
  id: number
  hora: string
  concepto: string
  monto: number
  categoria: string
}

// Categorías para agrupar los egresos del cajón (el análisis de Finanzas)
export const CATEGORIAS_EGRESO: { clave: string; nombre: string }[] = [
  { clave: 'verduras', nombre: '🥬 Verduras y frutas' },
  { clave: 'carnes', nombre: '🥩 Carnes y pollo' },
  { clave: 'hierbas', nombre: '🌿 Hierbas y especias' },
  { clave: 'abarrotes', nombre: '🍚 Abarrotes (no perecibles)' },
  { clave: 'lacteos', nombre: '🥚 Lácteos y huevos' },
  { clave: 'limpieza', nombre: '🧴 Productos de limpieza' },
  { clave: 'descartables', nombre: '🥡 Descartables y plásticos' },
  { clave: 'menaje', nombre: '🍴 Menaje y utensilios' },
  { clave: 'mantenimiento', nombre: '🔧 Mantenimiento y repuestos' },
  { clave: 'gas', nombre: '🔥 Gas y combustible' },
  { clave: 'servicios', nombre: '💡 Servicios (luz, agua, internet)' },
  { clave: 'transporte', nombre: '🚚 Transporte y taxi' },
  { clave: 'adelantos', nombre: '💵 Adelantos al personal' },
  { clave: 'tramites', nombre: '📄 Trámites e impuestos' },
  { clave: 'perecibles', nombre: '🧊 Perecibles (frescos)' },
  { clave: 'no_perecibles', nombre: '🥫 No perecibles' },
  { clave: 'otros', nombre: '📦 Otros' },
]

export const NOMBRE_CATEGORIA_EGRESO: Record<string, string> = {
  ...Object.fromEntries(CATEGORIAS_EGRESO.map((c) => [c.clave, c.nombre])),
  // Salidas que no pasan por el cajón pero sí por las cuentas
  descuadre: '⚖️ Descuadre de caja',
  incobrable: '🚶 Se fue sin pagar',
  cobranza: '🤝 Cobro de otro día',
  propina: '🙏 Propinas',
  reintegro: '↩️ Devolución de un proveedor',
  prestamo: '🏦 Préstamo o aporte',
}

// Movimientos de plata que no son venta: el descuadre de un cierre, el
// cobro de una venta de otro día, lo que se fue sin pagar.
export const CATEGORIAS_MOVIMIENTO: { clave: string; nombre: string; tipo: 'entra' | 'sale' | 'ambos' }[] = [
  { clave: 'descuadre', nombre: '⚖️ Descuadre de caja (sobró o faltó)', tipo: 'ambos' },
  { clave: 'incobrable', nombre: '🚶 Se fue sin pagar', tipo: 'sale' },
  { clave: 'cobranza', nombre: '🤝 Cobro de una venta de otro día', tipo: 'entra' },
  { clave: 'propina', nombre: '🙏 Propinas', tipo: 'entra' },
  { clave: 'reintegro', nombre: '↩️ Devolución de un proveedor', tipo: 'entra' },
  { clave: 'prestamo', nombre: '🏦 Préstamo o aporte', tipo: 'ambos' },
  { clave: 'otros', nombre: '📦 Otros', tipo: 'ambos' },
]

export const NOMBRE_CATEGORIA_MOVIMIENTO: Record<string, string> =
  Object.fromEntries(CATEGORIAS_MOVIMIENTO.map((c) => [c.clave, c.nombre]))

export const NOMBRE_METODO_PAGO: Record<string, string> = {
  efectivo: '💵 Efectivo',
  tarjeta: '💳 Tarjeta',
  yape: '📱 Yape',
  sin_cobrar: '⏳ Aún sin cobrar',
}

// Sugerencias para los desplegables de Finanzas ("Otro…" permite escribir)
export const COSTOS_FIJOS_SUGERIDOS = [
  'Alquiler', 'Luz', 'Agua', 'Internet', 'Gas', 'Licencias y permisos',
  'Contador', 'Seguridad', 'Arbitrios',
]

export const ROLES_SUGERIDOS = [
  'Cocina', 'Ayudante de cocina', 'Mozo / Moza', 'Caja', 'Limpieza', 'Administración',
]

export interface EgresosOut {
  egresos: EgresoOut[]
  total: number
}

export interface MenuGuardadoOut {
  id: number
  nombre: string
  actualizado: string
  cuantos_platos: number
  resumen: string
}

export interface DatosLocal {
  nombre: string
  direccion: string
  ruc: string
}

export interface ConfigOut {
  nombre_local: string
  direccion: string
  ruc: string
  ventana_cancelacion_seg: number
  timeout_inactividad_seg: number
  // "terminal": imprime la pantalla donde pide el cliente
  // "estacion": imprime la PC que tenga abierta /ticketera
  // "puente": el puente del local manda ESC/POS a la impresora de red
  modo_impresion: 'terminal' | 'estacion' | 'puente'
  impresora_ip: string
  impresora_puerto: number
  impresora_columnas: number
  // Toggle guardado (admin) y disponibilidad efectiva (toggle + API keys)
  voz_habilitada: boolean
  voz_disponible: boolean
  exigir_caja_abierta: boolean
  // Terminal y caja muestran solo los menús (sin platos sueltos)
  terminal_solo_menus: boolean
  // S/ por porción que sale en táper (0 = gratis) y qué empaques se ofrecen
  precio_taper: number
  empaques_ofrecidos: Empaque[]
  // Ventana de la tanda en cocina (minutos); 0 = apagada
  cocina_bulk_min: number
  cocina_tandas: boolean
  cocina_tanda_max_tickets: number
}

// --- Finanzas: lo que solo el dueño sabe (fijos y planilla) más el
// resumen que junta ventas, kardex y egresos ---
export interface CostoFijo {
  id: number
  nombre: string
  monto_mensual: number
}

export interface TrabajadorPlanilla {
  id: number
  nombre: string
  rol: string
  sueldo_mensual: number
}

export interface FinanzasFijos {
  costos: CostoFijo[]
  trabajadores: TrabajadorPlanilla[]
  total_costos_mes: number
  total_planilla_mes: number
}

export interface FinanzasDia {
  fecha: string
  entro: number
  egresos: number
  compras: number
}

export interface FinanzasResumen {
  desde: string
  hasta: string
  dias: number
  ventas: number
  costo_insumos: number
  mermas: number
  compras_insumos: number
  egresos_caja: number
  costos_fijos_mes: number
  planilla_mes: number
  fijos_periodo: number
  utilidad_estimada: number
  margen_pct: number | null
  venta_diaria_necesaria: number | null
  promedio_venta_dia: number
  dias_con_venta: number
  cobertura_recetas: { activos: number; con_receta: number }
  egresos_por_categoria: { categoria: string; monto: number }[]
  ingresos_por_categoria: { categoria: string; monto: number }[]
  otros_ingresos: number
  cobranzas: number
  entradas_por_metodo: Record<string, number>
  por_dia: FinanzasDia[]
}

export interface DiaBorrado {
  fecha: string
  ordenes: number
  ventas: number
  movimientos_kardex: number
  cierres_caja: number
  egresos: number
  cancelaciones: number
  tandas: number
}

// ---------- Tablero: la foto del negocio en una pantalla ----------
export interface InsumoTablero {
  id: number
  nombre: string
  unidad: string
  consumido: number
  consumido_soles: number
  comprado: number
  comprado_soles: number
  merma: number
  merma_soles: number
  ajuste: number
  stock_actual: number
  bajo_minimo: boolean
  dias_stock: number | null
  // Pareto del gasto: A = el 80% de la plata, B hasta 95%, C la cola
  clase_abc: string
  pct_valor: number
  pct_acumulado: number
}

export interface TableroDia {
  fecha: string
  etiqueta: string
  dia_semana: string
  ventas: number
  egresos: number
  compras: number
}

export interface Tablero {
  desde: string
  hasta: string
  dias: number
  kpis: {
    ventas: number
    costo_insumos: number
    mermas: number
    compras: number
    egresos: number
    margen_pct: number | null
    otros_ingresos: number
    cobranzas: number
    dias_con_venta: number
    promedio_dia: number
    mejor_dia: TableroDia | null
  }
  por_dia: TableroDia[]
  por_dia_semana: { dia: string; total: number; veces: number; promedio: number }[]
  top_platos: { nombre: string; cantidad: number; total: number; categoria: string }[]
  insumos: InsumoTablero[]
}

export interface OrdenPorCobrar {
  id: number
  fecha: string
  numero_orden_dia: number
  hora: string
  total: number
  mesas: number[]
  dias: number
}

export interface PorCobrar {
  pendientes: OrdenPorCobrar[]
  total_pendiente: number
  sin_metodo: OrdenPorCobrar[]
  total_sin_metodo: number
}

export interface MovimientoCaja {
  id: number
  fecha: string
  hora: string
  tipo: 'entra' | 'sale'
  concepto: string
  monto: number
  categoria: string
  automatico: boolean
}

export interface MovimientosOut {
  desde: string
  hasta: string
  movimientos: MovimientoCaja[]
  total_entra: number
  total_sale: number
  total_cobranzas: number
}

export interface FlujoFila {
  etiqueta: string
  desde: string
  hasta: string
  entro: number
  egresos: number
  compras: number
}

// Bebida embotellada de la lista fija (Inca Kola personal…): no es un
// plato; se pide con el pedido (terminal, voz) o se suma después (caja)
export interface Bebida {
  id: number
  nombre: string
  precio: number
  activa: boolean
  insumo_id: number | null
}

// Ticket chico de SOLO las gaseosas agregadas a una orden
export interface TicketBebidaOut {
  id?: number
  numero: string
  mesas: string[]
  items: { nombre: string; precio: number; cantidad: number }[]
  total: number
  hora?: string
  // GASEOSAS (default) | CAMBIO: la orden ya registrada se modificó
  titulo?: string
  total_orden?: number
}

// Respuesta de un cambio a una orden ya registrada
export interface RespuestaCambio {
  orden: OrdenOut
  modo_impresion: string
  // Ticket chico "CAMBIO" para cocina (en modo terminal lo imprime la pantalla)
  ticket_cambio: TicketBebidaOut | null
}

// Tanda de cocina (pre-orquestador): grupo de órdenes completas que
// salen juntas. Calculada por el backend con reglas deterministas.
export interface TandaPlato {
  nombre: string
  cantidad: number
  al_momento: boolean
  // Partición por capacidad ("6 + 3"); vacío = sale de una
  partes: number[]
}

export interface Tanda {
  numero: number
  orden_ids: number[]
  tickets: { numero: string; mesas: string[]; entrega: Entrega }[]
  platos: TandaPlato[]
  // Órdenes "separado" cuyo segundo espera a que salga su entrada
  esperando: { numero: string; platos: string[] }[]
  espera_min: number
  empezada: boolean
  // "Sale en ~N min" según el ritmo real del día; null sin historia aún
  estimado_min: number | null
}

// Cuánto está tardando un ticket en salir completo (promedio de los
// últimos 15 servidos hoy)
export interface MetricasServido {
  servidas: number
  promedio_min: number | null
}

export interface MesaEstado {
  id: number
  nombre: string
  activa: boolean
  ocupada: boolean
  ordenes: number[]
}

export type OrigenPedido = 'tactil' | 'voz' | 'mixto'

export interface VozItemResuelto {
  plato_id: number
  nombre: string
  precio: number
  cantidad: number
}

// Una persona (menú) entendida por voz: solo los tiempos que dijo; lo
// demás lo completa con los dedos en su ticket
export interface VozPersona {
  menu_id: number
  menu_nombre: string
  precio: number
  cantidad: number
  // empaque: solo si ESE plato va distinto que la persona ("sopa en bolsa")
  // espera: ese plato sale después ("el segundo más tarde")
  elecciones: {
    tiempo_orden: number; rotulo: string; plato_id: number; nombre: string
    empaque: Empaque | null; espera: boolean
    // Presa de pollo / 2 huevos en vez de la carne (si lo dijo)
    presa?: Presa; huevo?: boolean; coccion?: CoccionHuevo
  }[]
  sin: number[]
  sin_rotulos: string[]
  empaque: Empaque
  entrega: Entrega | null
  nombre: string
  nota: string
  agregados: { agregado_id: number; cantidad: number; nombre: string }[]
}

export interface VozGaseosa {
  bebida_id: number
  cantidad: number
  nombre: string
  precio: number
}

export interface VozRespuesta {
  log_id: number
  transcripcion: string
  items_resueltos: VozItemResuelto[]
  personas: VozPersona[]
  gaseosas: VozGaseosa[]
  mesa: { id: number; nombre: string } | null
  no_encontrados: string[]
  notas: string
  // Sin dudas (reglas, o la IA no adivinó nada): va directo a la ventana
  seguro?: boolean
  latencia_ms: number
}

export type VozResultado = 'aceptado' | 'corregido' | 'descartado'

export interface VozPanel {
  logs: {
    id: number
    hora: string
    transcripcion: string
    interpretacion: {
      personas?: { menu_id: number; cantidad: number }[]
      items: { plato_id: number; cantidad: number }[]
      no_encontrados: string[]
      notas: string
    }
    resultado: string
    latencia_ms: number
  }[]
  metricas: {
    total: number
    pct_aceptado: number
    pct_corregido: number
    pct_descartado: number
    latencia_promedio_ms: number | null
    costo_dia_usd: number
    costo_dia_soles: number
  }
}

const TOKEN_KEY = 'pos_admin_token'

export function getAdminToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setAdminToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearAdminToken() {
  localStorage.removeItem(TOKEN_KEY)
}

// PIN del local: solo aplica en despliegues en internet (Railway). El
// backend lo exige cuando la variable PIN_LOCAL está definida.
const PIN_KEY = 'pos_pin_local'

export function getPinLocal(): string {
  return localStorage.getItem(PIN_KEY) ?? ''
}

export function setPinLocal(pin: string) {
  localStorage.setItem(PIN_KEY, pin)
}

async function request<T>(path: string, options: RequestInit = {}, admin = false): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (admin) headers['X-Admin-Token'] = getAdminToken()
  const pin = getPinLocal()
  if (pin) headers['X-Pin-Local'] = pin
  const res = await fetch(path, { ...options, headers })
  if (!res.ok) {
    let detail = `Error ${res.status}`
    try {
      const body = await res.json()
      if (body.detail) detail = body.detail
    } catch {
      /* respuesta sin JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export interface MenuOrdenIn {
  menu_id: number
  cantidad: number
  elecciones: Record<number, number>
  extras: ExtraMenu[]
  omitidos: number[]
  agregados: { agregado_id: number; cantidad: number }[]
  empaque: Empaque
  empaques: Partial<Record<number, Empaque>>
  nota?: string
  entrega?: Entrega
  espera?: number[]
  nombre_persona?: string
  variantes?: Record<number, VarianteMenu>
}

// Menú del día como lo ve la caja: plantillas con TODAS sus alternativas
// (prendidas o no) y los menús guardados
export interface MenuCajaPlantilla {
  id: number
  nombre: string
  precio: number
  activo_hoy: boolean
  tiempos: {
    orden: number
    rotulo: string
    alternativas: { plato_id: number; nombre: string; recargo: number; activo_hoy: boolean }[]
  }[]
}

export interface MenuCaja {
  plantillas: MenuCajaPlantilla[]
  guardados: MenuGuardadoOut[]
  stock?: StockPlato[]
}

/** Porciones de hoy de una entrada o segundo. stock/quedan null = no se
 *  cuenta. quedan puede ser negativo: es aviso, no bloquea la venta. */
export interface StockPlato {
  plato_id: number
  nombre: string
  categoria: string
  stock: number | null
  vendidos: number
  quedan: number | null
  /** Lo puesto el último día que se contó: sugerencia para hoy */
  sugerido?: number | null
  sugerido_fecha?: string | null
}

/** ¿El menú lleva algún plato que se prepara al momento? Entonces esa
 *  persona no puede salir "todo junto" (el backend también lo exige). */
export function menuConAlMomento(m: MenuCarrito): boolean {
  return m.menu.tiempos.some((t) =>
    t.alternativas.some(
      (a) =>
        a.sale_al_momento &&
        ((!m.omitidos.includes(t.orden) && m.elecciones[t.orden] === a.plato_id) ||
          m.extras.some((e) => e.plato_id === a.plato_id)),
    ),
  )
}

/** Por defecto la comanda sale POR TIEMPOS; "todo junto" es lo especial
 *  y lo de siempre para llevar (pedido del dueño): sin elegir a mano, junto
 *  solo si todo lo de la persona va en táper, bolsa o lonchera. */
export function entregaDeMenu(m: MenuCarrito): Entrega {
  if (menuConAlMomento(m)) return 'separado'
  if (m.entrega) return m.entrega
  // Los tiempos de una sola opción (el refresco) no deciden
  const decisivos = m.menu.tiempos.filter((t) => t.alternativas.length > 1 && !m.omitidos.includes(t.orden))
  const empaques = (decisivos.length > 0 ? decisivos : m.menu.tiempos).map((t) => m.empaques[t.orden] ?? m.empaque)
  return empaques.every((e) => e !== 'mesa') ? 'junto' : 'separado'
}

/** La entrega en grande (ticket y cocina). Cada persona (menú) puede
 *  tener la suya: si todas coinciden se dice como siempre; si no, cuántas
 *  de cada una. Mismo criterio que la comanda ESC/POS del backend. */
export function lineaEntrega(orden: OrdenOut): { texto: string; separado: boolean } {
  const entregas: Entrega[] = orden.menus.flatMap((m) =>
    Array.from({ length: m.cantidad }, () => m.entrega ?? orden.entrega),
  )
  // Las bebidas sueltas no cuentan: no pasan por cocina
  if (orden.items.some((i) => !i.es_cargo && i.categoria !== 'bebida') || entregas.length === 0) {
    entregas.push(orden.entrega)
  }
  if (new Set(entregas).size === 1) {
    return entregas[0] === 'separado'
      ? { texto: 'SEPARADO', separado: true }
      : { texto: 'TODO JUNTO', separado: false }
  }
  const juntos = entregas.filter((e) => e === 'junto').length
  return { texto: `${juntos} JUNTO / ${entregas.length - juntos} SEPARADO`, separado: true }
}

/** La persona dictada como línea del carrito. Un tiempo con una sola
 *  opción entra incluido (igual que al tocar "+" en la terminal); los que
 *  no nombró quedan sin elegir para que el cliente los complete. */
export function personaVozAMenu(p: VozPersona, menu: MenuHoy): MenuCarrito {
  const elecciones: Record<number, number> = {}
  const empaques: Partial<Record<number, Empaque>> = {}
  const espera: number[] = []
  const variantes: Partial<Record<number, VarianteMenu>> = {}
  for (const t of menu.tiempos) {
    if (p.sin.includes(t.orden)) continue
    const dicho = p.elecciones.find((e) => e.tiempo_orden === t.orden)
    if (dicho && t.alternativas.some((a) => a.plato_id === dicho.plato_id)) {
      elecciones[t.orden] = dicho.plato_id
      if (dicho.empaque && dicho.empaque !== p.empaque) empaques[t.orden] = dicho.empaque
      if (dicho.espera) espera.push(t.orden)
      if (dicho.huevo) variantes[t.orden] = { huevo: true, ...(dicho.coccion ? { coccion: dicho.coccion } : {}) }
      else if (dicho.presa) variantes[t.orden] = { presa: dicho.presa }
    } else if (t.alternativas.length === 1) {
      elecciones[t.orden] = t.alternativas[0].plato_id
    }
  }
  return {
    menu, cantidad: p.cantidad, elecciones, extras: [],
    omitidos: p.sin.filter((o) => menu.tiempos.some((t) => t.orden === o)),
    agregados: (p.agregados ?? []).flatMap((a) => {
      const agregado = menu.agregados.find((x) => x.id === a.agregado_id)
      return agregado ? [{ agregado, cantidad: a.cantidad }] : []
    }),
    empaque: p.empaque, empaques, nota: p.nota,
    entrega: p.entrega ?? undefined, nombre_persona: p.nombre, espera, variantes,
  }
}

/** Lo que viaja al backend por cada menú del carrito. */
export function menuAPayload(m: MenuCarrito): MenuOrdenIn {
  return {
    menu_id: m.menu.id, cantidad: m.cantidad, elecciones: m.elecciones,
    extras: m.extras, omitidos: m.omitidos, empaques: m.empaques,
    agregados: m.agregados.map((a) => ({ agregado_id: a.agregado.id, cantidad: a.cantidad })),
    empaque: m.empaque, nota: m.nota.trim(),
    entrega: entregaDeMenu(m),
    // Solo lo elegido puede esperar
    espera: (m.espera ?? []).filter((t) => m.elecciones[t] !== undefined && !m.omitidos.includes(t)),
    nombre_persona: (m.nombre_persona ?? '').trim(),
    variantes: variantesValidas(m),
  }
}

/** Solo las variantes de platos elegidos que las admiten: la presa, si el
 *  plato lleva pollo (repartir o cambiar de plato pudo dejar una vieja). */
function variantesValidas(m: MenuCarrito): Record<number, VarianteMenu> {
  const salida: Record<number, VarianteMenu> = {}
  for (const [clave, v] of Object.entries(m.variantes ?? {})) {
    const t = Number(clave)
    const platoId = m.elecciones[t]
    if (!v || platoId === undefined || m.omitidos.includes(t)) continue
    const nombre = m.menu.tiempos.find((x) => x.orden === t)?.alternativas.find((a) => a.plato_id === platoId)?.nombre ?? ''
    const esSegundo = (m.menu.tiempos.find((x) => x.orden === t)?.rotulo ?? '').toLowerCase().includes('segundo')
    const validas = opcionesDePlato(nombre, esSegundo)
    const opciones = (v.opciones ?? []).filter((o) => validas.includes(o))
    const limpia: VarianteMenu = {}
    if (v.huevo) Object.assign(limpia, { huevo: true }, v.coccion ? { coccion: v.coccion } : {})
    else if (v.presa && llevaPollo(nombre)) limpia.presa = v.presa
    if (opciones.length > 0) limpia.opciones = opciones
    if (Object.keys(limpia).length > 0) salida[t] = limpia
  }
  return salida
}

export const api = {
  menuHoy: () =>
    request<{ categorias: string[]; platos: Plato[]; menus: MenuHoy[]; stock?: StockPlato[] }>('/api/menu/today'),

  config: () => request<ConfigOut>('/api/config'),

  crearOrden: (
    items: { plato_id: number; cantidad: number; empaque: Empaque; nota?: string }[],
    duracionSeg?: number,
    origen: OrigenPedido = 'tactil',
    mesaIds: number[] = [],
    entrega: Entrega = 'junto',
    menus: MenuOrdenIn[] = [],
    copias = 1,
    bebidas: { bebida_id: number; cantidad: number }[] = [],
    pago?: 'pagado' | 'pendiente',
  ) =>
    request<{ orden: OrdenOut; local: DatosLocal }>('/api/orders', {
      method: 'POST',
      body: JSON.stringify({
        items, menus, duracion_seg: duracionSeg, origen, mesa_ids: mesaIds, entrega, copias, bebidas, pago,
      }),
    }),

  // ---- Cambios a una orden ya registrada (el cliente se arrepintió) ----
  agregarAOrden: (
    id: number,
    cambio: { menus?: MenuOrdenIn[]; bebidas?: { bebida_id: number; cantidad: number }[] },
  ) =>
    request<RespuestaCambio>(`/api/orders/${id}/agregar`, {
      method: 'POST',
      body: JSON.stringify({ menus: cambio.menus ?? [], items: [], bebidas: cambio.bebidas ?? [] }),
    }),
  devolverTiempo: (id: number, ordenMenuId: number, tiempoOrden: number, platoId: number | null) =>
    request<RespuestaCambio>(`/api/orders/${id}/menus/${ordenMenuId}/devolver`, {
      method: 'POST',
      body: JSON.stringify({ tiempo_orden: tiempoOrden, plato_id: platoId }),
    }),
  cambiarEmpaqueItem: (id: number, itemId: number, empaque: Empaque) =>
    request<RespuestaCambio>(`/api/orders/${id}/items/${itemId}/empaque`, {
      method: 'PATCH',
      body: JSON.stringify({ empaque }),
    }),
  quitarPersona: (id: number, ordenMenuId: number) =>
    request<RespuestaCambio>(`/api/orders/${id}/menus/${ordenMenuId}`, { method: 'DELETE' }),
  quitarItemDeOrden: (id: number, itemId: number) =>
    request<RespuestaCambio>(`/api/orders/${id}/items/${itemId}`, { method: 'DELETE' }),

  // La persona eligió después lo que quedó "sin elegir" (desde caja)
  elegirPendiente: (ordenId: number, ordenMenuId: number, tiempoOrden: number, platoId: number) =>
    request<OrdenOut>(`/api/orders/${ordenId}/menus/${ordenMenuId}/elegir`, {
      method: 'POST',
      body: JSON.stringify({ tiempo_orden: tiempoOrden, plato_id: platoId }),
    }),

  // "Ya lo piden": el plato reservado pasa a la cola normal de cocina
  soltarEspera: (itemId: number) =>
    request<{ id: number; espera: boolean }>(`/api/orders/items/${itemId}/soltar`, { method: 'POST' }),

  corregirEntrega: (ordenId: number, entrega: Entrega) =>
    request<{ id: number; entrega: Entrega }>(`/api/orders/${ordenId}/entrega`, {
      method: 'PATCH',
      body: JSON.stringify({ entrega }),
    }),

  ordenesDeDia: (fecha: string) =>
    request<{ fecha: string; ordenes: OrdenOut[]; total_vendido: number }>(
      `/api/orders/of-day?fecha=${fecha}`),

  // --- Mesas ---
  mesas: () => request<{ mesas: MesaEstado[] }>('/api/mesas'),

  crearMesa: (nombre: string) =>
    request<MesaEstado>('/api/mesas', { method: 'POST', body: JSON.stringify({ nombre }) }, true),

  actualizarMesa: (id: number, cambios: { nombre?: string; activa?: boolean }) =>
    request<MesaEstado>(`/api/mesas/${id}`, { method: 'PUT', body: JSON.stringify(cambios) }, true),

  liberarMesa: (id: number) =>
    request<{ mesa_id: number; tickets_liberados: number }>(`/api/mesas/${id}/liberar`, {
      method: 'POST',
    }),

  // Mesas compartidas: libera SOLO la mesa de este ticket
  liberarMesaDeTicket: (ordenId: number) =>
    request<{ id: number; mesa_liberada: boolean }>(`/api/orders/${ordenId}/liberar-mesa`, {
      method: 'POST',
    }),

  asignarMesas: (ordenId: number, mesaIds: number[]) =>
    request<{ id: number; mesa_ids: number[]; mesas: string[] }>(`/api/orders/${ordenId}/mesas`, {
      method: 'PATCH',
      body: JSON.stringify({ mesa_ids: mesaIds }),
    }),

  cierresHistorial: () =>
    request<{ cierres: CajaEstado[] }>('/api/caja/historial', {}, true),

  // --- Pedido por voz ---
  vozOrden: async (audio: Blob, duracionSeg: number): Promise<VozRespuesta> => {
    const datos = new FormData()
    datos.append('audio', audio, 'pedido.webm')
    datos.append('duracion_seg', duracionSeg.toFixed(1))
    const pin = getPinLocal()
    const res = await fetch('/api/voice/order', {
      method: 'POST',
      body: datos,
      headers: pin ? { 'X-Pin-Local': pin } : undefined,
    })
    if (!res.ok) {
      let detail = `Error ${res.status}`
      try {
        const body = await res.json()
        if (body.detail) detail = body.detail
      } catch { /* sin JSON */ }
      throw new ApiError(res.status, detail)
    }
    return res.json()
  },

  vozResultado: (logId: number, resultado: VozResultado) =>
    request<{ id: number; resultado: string }>(`/api/voice/logs/${logId}`, {
      method: 'PATCH',
      body: JSON.stringify({ resultado }),
    }).catch(() => null), // el log es telemetría: nunca bloquea al cliente

  vozLogsHoy: () => request<VozPanel>('/api/voice/logs/today', {}, true),

  cobrarOrden: (id: number, metodo: MetodoPago) =>
    request<{ id: number; metodo_pago: MetodoPago }>(`/api/orders/${id}/pago`, {
      method: 'PATCH',
      body: JSON.stringify({ metodo_pago: metodo }),
    }),

  // --- Insumos, recetas y kardex (admin) ---
  insumos: () =>
    request<{ insumos: Insumo[]; valor_inventario: number; por_agotarse: string[] }>(
      '/api/insumos', {}, true),

  actualizarInsumo: (id: number, cambios: { nombre?: string; unidad?: string; activo?: boolean; stock_minimo?: number }) =>
    request<Insumo>(`/api/insumos/${id}`, {
      method: 'PUT',
      body: JSON.stringify(cambios),
    }, true),

  crearInsumo: (nombre: string, unidad: string, costoUnitario: number) =>
    request<Insumo>('/api/insumos', {
      method: 'POST',
      body: JSON.stringify({ nombre, unidad, costo_unitario: costoUnitario }),
    }, true),

  movimientoInsumo: (
    insumoId: number,
    tipo: 'compra' | 'merma' | 'ajuste',
    cantidad: number,
    costoTotal?: number,
    nota = '',
  ) =>
    request<Insumo>(`/api/insumos/${insumoId}/movimientos`, {
      method: 'POST',
      body: JSON.stringify({ tipo, cantidad, costo_total: costoTotal, nota }),
    }, true),

  kardex: (opts?: { desde?: string; hasta?: string; insumoId?: number }) => {
    const params = new URLSearchParams()
    if (opts?.desde) params.set('desde', opts.desde)
    if (opts?.hasta) params.set('hasta', opts.hasta)
    if (opts?.insumoId) params.set('insumo_id', String(opts.insumoId))
    const q = params.toString()
    return request<{ movimientos: MovimientoKardex[] }>(
      `/api/insumos/kardex${q ? `?${q}` : ''}`, {}, true)
  },

  receta: (platoId: number) => request<RecetaDetalle>(`/api/insumos/recetas/${platoId}`, {}, true),

  // --- Bases pregrabadas: despensa típica de fonda y recetas por plato ---
  baseKardex: () =>
    request<{
      insumos: { nombre: string; unidad: string; costo_referencial: number; stock_minimo: number; existe: boolean }[]
      platos_con_receta: string[]
    }>('/api/insumos/base', {}, true),

  cargarDespensaBase: () =>
    request<{ creados: string[]; total: number }>('/api/insumos/base/cargar', { method: 'POST' }, true),

  recetaSugerida: (platoId: number) =>
    request<{
      plato_id: number
      encontrada: boolean
      base: string | null
      items: { insumo: string; unidad: string; cantidad: number; existe: boolean; sin_conversion: boolean }[]
    }>(`/api/insumos/recetas/${platoId}/sugerida`, {}, true),

  aplicarRecetaSugerida: (platoId: number) =>
    request<RecetaDetalle & { avisos: string[] }>(`/api/insumos/recetas/${platoId}/sugerida`, { method: 'POST' }, true),

  // Ids de los platos que ya tienen receta (una sola consulta)
  platosConReceta: () => request<{ plato_ids: number[] }>('/api/insumos/recetas', {}, true),

  guardarReceta: (platoId: number, items: { insumo_id: number; cantidad: number }[]) =>
    request<RecetaDetalle>(`/api/insumos/recetas/${platoId}`, {
      method: 'PUT',
      body: JSON.stringify({ items }),
    }, true),

  // --- Apertura y cierre de caja ---
  cajaHoy: () => request<CajaEstado>('/api/caja/hoy'),

  abrirCaja: (montoApertura: number, notas = '') =>
    request<CajaEstado>('/api/caja/abrir', {
      method: 'POST',
      body: JSON.stringify({ monto_apertura: montoApertura, notas }),
    }),

  cerrarCaja: (montoContado: number, notas = '') =>
    request<CajaEstado>('/api/caja/cerrar', {
      method: 'POST',
      body: JSON.stringify({ monto_contado: montoContado, notas }),
    }),

  // Vuelve a mandar el resumen del cierre a la ticketera (modo puente)
  imprimirCierre: () =>
    request<{ ok: boolean }>('/api/caja/imprimir-cierre', { method: 'POST' }),

  // Deshace el cierre del día (se cerró por error o en una demo)
  reabrirCaja: () =>
    request<CajaEstado>('/api/caja/reabrir', { method: 'POST' }),

  // Corrige el fondo inicial de la caja de hoy (abierta o cerrada)
  corregirFondoCaja: (montoApertura: number) =>
    request<CajaEstado>('/api/caja/apertura', {
      method: 'PUT',
      body: JSON.stringify({ monto_apertura: montoApertura }),
    }),

  // --- Egresos del turno ("salió plata del cajón") ---
  egresosTurno: () => request<EgresosOut>('/api/caja/egresos'),

  registrarEgreso: (concepto: string, monto: number, categoria = 'otros') =>
    request<EgresosOut>('/api/caja/egresos', {
      method: 'POST',
      body: JSON.stringify({ concepto, monto, categoria }),
    }),

  borrarEgreso: (id: number) =>
    request<EgresosOut>(`/api/caja/egresos/${id}`, { method: 'DELETE' }),

  // "Falta pagar": el ticket salió pero la plata no entró todavía
  marcarPagoPendiente: (ordenId: number, pendiente: boolean) =>
    request<{ id: number; pago_pendiente: boolean }>(`/api/orders/${ordenId}/pago-pendiente`, {
      method: 'PATCH',
      body: JSON.stringify({ pendiente }),
    }),

  // "Falta vuelto": pagó con billete grande; null = vuelto ya entregado
  registrarVuelto: (ordenId: number, pagoCon: number | null) =>
    request<{ id: number; vuelto_pendiente: number | null }>(`/api/orders/${ordenId}/vuelto`, {
      method: 'PATCH',
      body: JSON.stringify({ pago_con: pagoCon }),
    }),

  // El resumen de cierre salió por la impresora (modo puente)
  confirmarCierreImpreso: () =>
    request<{ confirmada: boolean }>('/api/print/cierre/impresa', { method: 'POST' }),

  ordenesHoy: () =>
    request<{ ordenes: OrdenOut[]; total_vendido: number; impresion_pendiente: ImpresionPendiente }>(
      '/api/orders/today'),

  // --- Empezar limpio (admin): borra el movimiento de las pruebas ---
  resumenDatos: () => request<ResumenDatos>('/api/mantenimiento/datos', {}, true),

  // Borra el movimiento de UN día (el de las pruebas), sin tocar el resto
  borrarDia: (fecha: string, confirmacion: string) =>
    request<{ borrado: DiaBorrado }>('/api/mantenimiento/borrar-dia', {
      method: 'POST',
      body: JSON.stringify({ fecha, confirmacion }),
    }, true),

  reiniciarDatos: (confirmacion: string, reiniciarStock: boolean) =>
    request<{ borrado: ResumenDatos; stock_reiniciado: boolean }>('/api/mantenimiento/reiniciar', {
      method: 'POST',
      body: JSON.stringify({ confirmacion, reiniciar_stock: reiniciarStock }),
    }, true),

  // --- Bebidas embotelladas (lista fija de caja) ---
  bebidas: () => request<{ bebidas: Bebida[] }>('/api/bebidas'),

  crearBebida: (nombre: string, precio: number) =>
    request<Bebida>('/api/bebidas', {
      method: 'POST',
      body: JSON.stringify({ nombre, precio }),
    }, true),

  editarBebida: (id: number, cambios: { nombre?: string; precio?: number; activa?: boolean }) =>
    request<Bebida>(`/api/bebidas/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(cambios),
    }, true),

  borrarBebida: (id: number) =>
    request<{ borrada: boolean }>(`/api/bebidas/${id}`, { method: 'DELETE' }, true),

  // Añade gaseosas a una orden YA creada (desde caja): el backend suma el
  // total, descuenta el kardex y prepara el ticket chico de solo gaseosas
  agregarBebidas: (ordenId: number, items: { bebida_id: number; cantidad: number }[]) =>
    request<{ orden: OrdenOut; modo_impresion: string; ticket_bebida: TicketBebidaOut }>(
      `/api/orders/${ordenId}/bebidas`, {
        method: 'POST',
        body: JSON.stringify({ items }),
      }),

  // Mueve TODOS los pedidos de hoy de una mesa a otra (el grupo se cambió)
  trasladarMesa: (deMesaId: number, aMesaId: number, reimprimir: boolean) =>
    request<{ trasladadas: number; ordenes: OrdenOut[] }>('/api/orders/trasladar-mesa', {
      method: 'POST',
      body: JSON.stringify({ de_mesa_id: deMesaId, a_mesa_id: aMesaId, reimprimir }),
    }),

  confirmarBebidaImpresa: (ticketId: number) =>
    request<{ confirmada: boolean }>(`/api/print/bebida/${ticketId}/impresa`, { method: 'POST' }),

  // --- Finanzas: costos fijos, planilla y resumen financiero ---
  finanzasFijos: () => request<FinanzasFijos>('/api/finanzas/fijos', {}, true),

  crearCostoFijo: (nombre: string, montoMensual: number) =>
    request<FinanzasFijos>('/api/finanzas/costos-fijos', {
      method: 'POST',
      body: JSON.stringify({ nombre, monto_mensual: montoMensual }),
    }, true),

  editarCostoFijo: (id: number, nombre: string, montoMensual: number) =>
    request<FinanzasFijos>(`/api/finanzas/costos-fijos/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ nombre, monto_mensual: montoMensual }),
    }, true),

  borrarCostoFijo: (id: number) =>
    request<FinanzasFijos>(`/api/finanzas/costos-fijos/${id}`, { method: 'DELETE' }, true),

  crearTrabajador: (nombre: string, rol: string, sueldoMensual: number) =>
    request<FinanzasFijos>('/api/finanzas/planilla', {
      method: 'POST',
      body: JSON.stringify({ nombre, rol, sueldo_mensual: sueldoMensual }),
    }, true),

  editarTrabajador: (id: number, nombre: string, rol: string, sueldoMensual: number) =>
    request<FinanzasFijos>(`/api/finanzas/planilla/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ nombre, rol, sueldo_mensual: sueldoMensual }),
    }, true),

  borrarTrabajador: (id: number) =>
    request<FinanzasFijos>(`/api/finanzas/planilla/${id}`, { method: 'DELETE' }, true),

  finanzasResumen: (dias: number) =>
    request<FinanzasResumen>(`/api/finanzas/resumen?dias=${dias}`, {}, true),

  // Pagos pendientes de cualquier día (caja y admin los ven igual)
  porCobrar: () => request<PorCobrar>('/api/orders/por-cobrar'),
  // Distinto de cobrarOrden: este levanta una deuda de CUALQUIER día y,
  // si es de una fecha anterior, deja la cobranza anotada en el cajón de hoy
  cobrarPendiente: (id: number, metodo_pago: string) =>
    request<{ id: number; metodo_pago: string; cobranza_registrada: boolean }>(
      `/api/orders/${id}/cobrar`, { method: 'POST', body: JSON.stringify({ metodo_pago }) }),
  marcarIncobrable: (id: number) =>
    request<{ id: number; monto: number }>(
      `/api/orders/${id}/incobrable`, { method: 'POST' }),

  // Movimientos de caja que no son venta (descuadres, propinas…)
  movimientos: (dias = 60) =>
    request<MovimientosOut>(`/api/finanzas/movimientos?dias=${dias}`, {}, true),
  anotarMovimiento: (datos: {
    fecha: string; tipo: 'entra' | 'sale'; concepto: string; monto: number; categoria: string
  }) => request<MovimientosOut>('/api/finanzas/movimientos',
    { method: 'POST', body: JSON.stringify(datos) }, true),
  borrarMovimiento: (id: number) =>
    request<MovimientosOut>(`/api/finanzas/movimientos/${id}`, { method: 'DELETE' }, true),

  // El período va por días (últimos N) o por rango exacto desde/hasta
  tablero: (periodo: { dias: number } | { desde: string; hasta: string }) => {
    const q = 'dias' in periodo
      ? `dias=${periodo.dias}`
      : `desde=${periodo.desde}&hasta=${periodo.hasta}`
    return request<Tablero>(`/api/finanzas/tablero?${q}`, {}, true)
  },

  finanzasFlujo: (agrupar: 'dia' | 'semana' | 'mes' | 'anio') =>
    request<{ agrupar: string; filas: FlujoFila[] }>(
      `/api/finanzas/flujo?agrupar=${agrupar}`, {}, true),

  // --- Estación de impresión (/ticketera) ---
  pendientesImpresion: () =>
    request<{ ordenes: OrdenOut[]; tickets_bebida: TicketBebidaOut[]; local: DatosLocal }>(
      '/api/orders/pending-print'),

  marcarImpreso: (id: number) =>
    request<{ id: number; impreso: boolean }>(`/api/orders/${id}/printed`, { method: 'POST' }),

  reimprimirOrden: (id: number) =>
    request<{ id: number; impreso: boolean }>(`/api/orders/${id}/reprint`, { method: 'POST' }),

  descartarPendientes: () =>
    request<{ descartadas: number }>('/api/orders/pending-print/clear', { method: 'POST' }),

  // --- Tandas de cocina (pre-orquestador) ---
  tandas: () => request<{ habilitado: boolean; tandas: Tanda[]; metricas: MetricasServido }>('/api/orders/tandas'),

  empezarTanda: (ordenIds: number[]) =>
    request<{ ordenes: OrdenOut[]; avisos: string[]; log_id: number }>('/api/orders/tandas/empezar', {
      method: 'POST',
      body: JSON.stringify({ orden_ids: ordenIds }),
    }),

  salioTanda: (ordenIds: number[], logId?: number) =>
    request<{ ordenes: OrdenOut[]; avisos: string[]; log_id: number }>('/api/orders/tandas/salio', {
      method: 'POST',
      body: JSON.stringify({ orden_ids: ordenIds, log_id: logId ?? null }),
    }),

  // Tachar un bulk desde "Por salir": avanza N porciones de un plato en
  // cascada (orden más antigua primero) y devuelve las órdenes que cambiaron
  despacharBulk: (lineas: { plato_nombre: string; cantidad: number }[], estadoDestino: EstadoItem) =>
    request<{ ordenes: OrdenOut[] }>('/api/orders/despachar-bulk', {
      method: 'POST',
      body: JSON.stringify({ estado_destino: estadoDestino, lineas }),
    }),

  cambiarEstado: (id: number, estado: string) =>
    request<{ id: number; estado: string }>(`/api/orders/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ estado }),
    }),

  registrarCancelacion: (items: { nombre: string; precio: number; cantidad: number }[], total: number) =>
    request<{ ok: boolean }>('/api/cancellations', {
      method: 'POST',
      body: JSON.stringify({ items, total }),
    }),

  // --- Admin ---
  login: (password: string) =>
    request<{ token: string }>('/api/admin/login', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),

  catalogo: () => request<{ platos: Plato[] }>('/api/menu/catalog', {}, true),

  // --- Fotos de plato (admin) ---
  subirFotoPlato: async (platoId: number, archivo: File): Promise<{ plato_id: number; foto: string }> => {
    const datos = new FormData()
    datos.append('archivo', archivo)
    const cabeceras: Record<string, string> = { 'X-Admin-Token': getAdminToken() }
    if (getPinLocal()) cabeceras['X-Pin-Local'] = getPinLocal()
    const res = await fetch(`/api/menu/platos/${platoId}/foto`, {
      method: 'POST', body: datos, headers: cabeceras,
    })
    if (!res.ok) {
      let detail = `Error ${res.status}`
      try {
        const body = await res.json()
        if (body.detail) detail = body.detail
      } catch { /* sin JSON */ }
      throw new ApiError(res.status, detail)
    }
    return res.json()
  },

  quitarFotoPlato: (platoId: number) =>
    request<{ plato_id: number; foto: null }>(`/api/menu/platos/${platoId}/foto`, {
      method: 'DELETE',
    }, true),

  // --- Plantillas de menú encadenado (admin) ---
  plantillas: () => request<{ plantillas: PlantillaMenu[] }>('/api/menu/plantillas', {}, true),

  guardarPlantillas: (plantillas: PlantillaMenuIn[]) =>
    request<{ plantillas: PlantillaMenu[] }>('/api/menu/plantillas', {
      method: 'PUT',
      body: JSON.stringify({ plantillas }),
    }, true),

  menuAnterior: () => request<{ fecha: string | null; platos: Plato[] }>('/api/menu/previous', {}, true),

  guardarMenu: (platos: { id?: number; nombre: string; categoria: string; precio: number; activo_hoy: boolean; sale_al_momento?: boolean; capacidad_tanda?: number; sinonimos?: string[] }[]) =>
    request<{ categorias: string[]; platos: Plato[] }>('/api/menu/today', {
      method: 'PUT',
      body: JSON.stringify({ platos }),
    }, true),

  // --- Menú del día desde la caja (sin token de admin) ---
  menuCaja: () => request<MenuCaja>('/api/menu/caja'),
  platoParaHoy: (platoId: number, activoHoy: boolean) =>
    request<MenuCaja>(`/api/menu/platos/${platoId}/hoy`, {
      method: 'PATCH', body: JSON.stringify({ activo_hoy: activoHoy }),
    }),
  stockPlato: (platoId: number, stock: number | null) =>
    request<MenuCaja>(`/api/menu/platos/${platoId}/stock`, {
      method: 'PATCH', body: JSON.stringify({ stock }),
    }),
  menuParaHoy: (plantillaId: number, activoHoy: boolean) =>
    request<MenuCaja>(`/api/menu/plantillas/${plantillaId}/hoy`, {
      method: 'PATCH', body: JSON.stringify({ activo_hoy: activoHoy }),
    }),
  cargarGuardadoCaja: (guardadoId: number) =>
    request<MenuCaja>(`/api/menu/caja/guardados/${guardadoId}/cargar`, { method: 'POST' }),

  // --- Menús guardados ("el menú de los jueves") ---
  menusGuardados: () =>
    request<{ guardados: MenuGuardadoOut[] }>('/api/menu/guardados', {}, true),

  guardarMenuDeHoyComo: (nombre: string) =>
    request<{ guardados: MenuGuardadoOut[] }>('/api/menu/guardados', {
      method: 'POST',
      body: JSON.stringify({ nombre }),
    }, true),

  cargarMenuGuardado: (id: number) =>
    request<{ categorias: string[]; platos: Plato[]; menus: MenuHoy[] }>(
      `/api/menu/guardados/${id}/cargar`, { method: 'POST' }, true,
    ),

  borrarMenuGuardado: (id: number) =>
    request<{ guardados: MenuGuardadoOut[] }>(`/api/menu/guardados/${id}`, {
      method: 'DELETE',
    }, true),

  cancelacionesHoy: () =>
    request<{
      cancelaciones: { id: number; fecha: string; hora: string; total: number; items: { nombre: string; cantidad: number; precio: number }[] }[]
    }>('/api/cancellations/today', {}, true),

  // Encola un ticket de prueba para el puente de impresión
  imprimirPrueba: () =>
    request<{ encolada: boolean }>('/api/print/prueba', { method: 'POST' }, true),

  // El ticket de prueba se confirma como las órdenes: si no sale, sigue en cola
  confirmarPruebaImpresa: () =>
    request<{ confirmada: boolean }>('/api/print/prueba/impresa', { method: 'POST' }),

  // Cola de tickets en bytes ESC/POS (base64): la consume el puente del
  // local o la ticketera-tablet con RawBT
  colaImpresion: () =>
    request<{
      impresora: { ip: string; puerto: number }
      trabajos: { tipo: 'orden' | 'prueba'; orden_id: number | null; numero: string; datos_b64: string }[]
    }>('/api/print/cola'),

  guardarConfig: (config: Partial<ConfigOut>) =>
    request<ConfigOut>('/api/config', { method: 'PUT', body: JSON.stringify(config) }, true),

  statsHoy: () => request<StatsOut>('/api/stats/today', {}, true),

  statsRango: (desde: string, hasta: string) =>
    request<StatsOut>(`/api/stats/range?desde=${desde}&hasta=${hasta}`, {}, true),

  // Descarga el CSV de ventas. Sin fechas: hoy.
  descargarVentasCsv: (desde?: string, hasta?: string) =>
    descargarCsv(`/api/stats/export${rangoEnUrl(desde, hasta)}`, 'ventas.csv'),

  // Agregados comunes de los menús (+presa, +refresco…), solo admin
  agregadosMenu: () =>
    request<{ agregados: AgregadoAdmin[] }>('/api/menu/agregados', {}, true),

  guardarAgregadosMenu: (agregados: (Omit<AgregadoAdmin, 'id'> & { id?: number })[]) =>
    request<{ agregados: AgregadoAdmin[] }>(
      '/api/menu/agregados',
      { method: 'PUT', body: JSON.stringify({ agregados }) },
      true,
    ),

  // Reporte de consumo del kardex. Sin fechas: últimos 7 días.
  consumoKardex: (desde?: string, hasta?: string) =>
    request<ReporteConsumo>(`/api/insumos/consumo${rangoEnUrl(desde, hasta)}`, {}, true),

  descargarConsumoCsv: (desde?: string, hasta?: string) =>
    descargarCsv(`/api/insumos/consumo.csv${rangoEnUrl(desde, hasta)}`, 'consumo.csv'),
}

function rangoEnUrl(desde?: string, hasta?: string): string {
  return desde && hasta ? `?desde=${desde}&hasta=${hasta}` : ''
}

// Los CSV necesitan el token, así que van por fetch + blob en vez de un
// <a href> directo; el navegador guarda el archivo con el nombre del backend.
async function descargarCsv(ruta: string, nombrePorDefecto: string) {
  const cabeceras: Record<string, string> = { 'X-Admin-Token': getAdminToken() }
  if (getPinLocal()) cabeceras['X-Pin-Local'] = getPinLocal()
  const res = await fetch(ruta, { headers: cabeceras })
  if (!res.ok) throw new ApiError(res.status, `Error ${res.status}`)
  const blob = await res.blob()
  const nombre = res.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] ?? nombrePorDefecto
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nombre
  a.click()
  URL.revokeObjectURL(url)
}

export interface AgregadoAdmin {
  id: number
  nombre: string
  precio: number
  activo: boolean
}

export interface ConsumoInsumo {
  id: number
  nombre: string
  unidad: string
  consumido: number
  consumido_soles: number
  comprado: number
  comprado_soles: number
  merma: number
  merma_soles: number
  ajuste: number
  stock_actual: number
  bajo_minimo: boolean
  dias_stock: number | null
}

export interface ReporteConsumo {
  desde: string
  hasta: string
  dias: number
  gasto_compras: number
  valor_consumo: number
  valor_mermas: number
  por_agotarse: string[]
  por_dia: { fecha: string; soles: number }[]
  insumos: ConsumoInsumo[]
}

export interface StatsOut {
  desde: string
  hasta: string
  num_ordenes: number
  total_vendido: number
  duracion_promedio_seg: number | null
  ventas_por_plato: { nombre: string; cantidad: number; total: number }[]
  ventas_por_dia: { fecha: string; ordenes: number; total: number }[]
  ordenes_por_hora: { hora: string; cantidad: number }[]
  num_cancelaciones: number
  total_cancelado: number
  tasa_cancelacion: number
}

// Formas del CRUD admin de plantillas de menú
export interface PlantillaMenu {
  id: number
  nombre: string
  precio: number
  activo_hoy: boolean
  tiempos: {
    orden: number
    rotulo: string
    obligatorio: boolean
    precio_extra: number
    descuento_si_se_quita: number
    alternativas: { plato_id: number; nombre: string; recargo: number }[]
  }[]
}

export interface PlantillaMenuIn {
  id?: number
  nombre: string
  precio: number
  activo_hoy: boolean
  tiempos: {
    rotulo: string
    obligatorio: boolean
    precio_extra: number
    descuento_si_se_quita: number
    alternativas: { plato_id: number; recargo: number }[]
  }[]
}

// Lo que suma UNA unidad del menú armado (precio + recargos elegidos);
// los extras van aparte porque no se multiplican por la cantidad de menús
// Precio de UNA unidad del menú: precio base + recargos de las elecciones
// − descuentos por los tiempos quitados ("sin sopa"). El backend hace el
// mismo cálculo y es la autoridad; esto es solo para mostrar en pantalla.
// Tiempos del menú que TODAVÍA hay que elegir. Es el espejo exacto de la
// validación del backend (services/orders._armar_menu): obligatorio, con
// más de una alternativa, no quitado y sin elección — así la guía dice lo
// mismo que el 422 diría al final, pero desde el principio.
export function tiemposPendientes(linea: MenuCarrito): MenuTiempoHoy[] {
  return linea.menu.tiempos.filter(
    (t) =>
      t.obligatorio &&
      t.alternativas.length > 1 &&
      !linea.omitidos.includes(t.orden) &&
      linea.elecciones[t.orden] === undefined,
  )
}

// Cuántos tiempos del menú requieren elección (para "2 de 3 listos")
export function tiemposElegibles(linea: MenuCarrito): number {
  return linea.menu.tiempos.filter(
    (t) => t.obligatorio && t.alternativas.length > 1 && !linea.omitidos.includes(t.orden),
  ).length
}

export function precioUnitarioMenu(linea: MenuCarrito): number {
  let unitario = linea.menu.precio
  for (const tiempo of linea.menu.tiempos) {
    if (linea.omitidos.includes(tiempo.orden)) {
      unitario -= tiempo.descuento_si_se_quita
      continue
    }
    const elegido = linea.elecciones[tiempo.orden]
    const alternativa = tiempo.alternativas.find((a) => a.plato_id === elegido)
    if (alternativa) unitario += alternativa.recargo
  }
  return unitario
}

export function subtotalExtras(linea: MenuCarrito): number {
  let total = 0
  for (const extra of linea.extras) {
    const tiempo = linea.menu.tiempos.find((t) => t.orden === extra.tiempo_orden)
    const alternativa = tiempo?.alternativas.find((a) => a.plato_id === extra.plato_id)
    if (tiempo) total += (tiempo.precio_extra + (alternativa?.recargo ?? 0)) * extra.cantidad
  }
  return total
}

// Porciones que salen en táper (para mostrar el cargo ANTES de confirmar;
// el backend hace el mismo conteo y es la autoridad)
/** Efectivo que debería haber en el cajón: fondo + ventas en efectivo −
 * egresos. Espejo SOLO para pintar (panel, doble check y resumen): la
 * autoridad del cuadre es el backend. */
export function esperadoEnCaja(estado: CajaEstado): number {
  return Math.round(
    ((estado.monto_apertura ?? 0) + estado.ventas_efectivo - (estado.egresos ?? 0)
      - (estado.por_cobrar ?? 0) + (estado.vueltos_pendientes ?? 0)) * 100,
  ) / 100
}

export function unidadesEnTaper(items: ItemCarrito[], menus: MenuCarrito[]): number {
  let n = items.reduce((s, i) => s + (i.empaque === 'taper' ? i.cantidad : 0), 0)
  for (const m of menus) {
    const empaqueDe = (orden: number) => m.empaques[orden] ?? m.empaque
    for (const t of m.menu.tiempos) {
      if (m.omitidos.includes(t.orden)) continue
      const elegida = t.alternativas.some((a) => a.plato_id === m.elecciones[t.orden])
      const incluida = elegida || t.alternativas.length === 1
      if (incluida && empaqueDe(t.orden) === 'taper') n += m.cantidad
    }
    for (const e of m.extras) {
      if (empaqueDe(e.tiempo_orden) === 'taper') n += e.cantidad
    }
    if (m.empaque === 'taper') n += m.agregados.reduce((s, a) => s + a.cantidad, 0)
  }
  return n
}

export function subtotalAgregados(linea: MenuCarrito): number {
  return linea.agregados.reduce((s, a) => s + a.agregado.precio * a.cantidad, 0)
}

export function subtotalMenu(linea: MenuCarrito): number {
  return (
    precioUnitarioMenu(linea) * linea.cantidad + subtotalExtras(linea) + subtotalAgregados(linea)
  )
}

export function soles(monto: number): string {
  // Espacio DURO tras "S/" y separador de miles peruano: la cifra nunca
  // se parte en dos líneas ni deja el "S/" solo al final del renglón.
  const [entera, decimales] = Math.abs(monto).toFixed(2).split('.')
  const miles = entera.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${monto < 0 ? '−' : ''}S/\u00a0${miles}.${decimales}`
}

export const NOMBRE_CATEGORIA: Record<string, string> = {
  entrada: 'Entradas',
  fondo: 'Platos de fondo',
  bebida: 'Bebidas',
  postre: 'Postres',
}
