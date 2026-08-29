// Cliente HTTP mínimo para la API del backend.

export interface Plato {
  id: number
  nombre: string
  categoria: string
  precio: number
  activo_hoy: boolean
  sale_al_momento: boolean
  sinonimos: string[]
}

export type Entrega = 'junto' | 'separado'

export const NOMBRE_ENTREGA: Record<Entrega, { titulo: string; detalle: string }> = {
  junto: { titulo: '🍽 Todo junto', detalle: 'una sola entrega' },
  separado: { titulo: '⏱ Separado', detalle: 'por tiempos, según salga' },
}

export type Empaque = 'mesa' | 'taper' | 'bolsa' | 'lonchera'

export const EMPAQUES: Empaque[] = ['mesa', 'taper', 'bolsa', 'lonchera']

export const NOMBRE_EMPAQUE: Record<Empaque, string> = {
  mesa: '🍽 Mesa',
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
  alternativas: MenuAlternativaHoy[]
}

export interface MenuHoy {
  id: number
  nombre: string
  precio: number
  tiempos: MenuTiempoHoy[]
}

export interface ExtraMenu {
  tiempo_orden: number
  plato_id: number
  cantidad: number
}

// Un menú armado dentro del carrito (elecciones ya resueltas)
export interface MenuCarrito {
  menu: MenuHoy
  cantidad: number
  elecciones: Record<number, number> // tiempo_orden → plato_id
  extras: ExtraMenu[]
  empaque: Empaque
  nota: string
}

// Estado POR ÍTEM (§3): la cocina tacha porciones, no tickets enteros
export type EstadoItem = 'pendiente' | 'preparando' | 'listo' | 'entregado'

export interface OrdenItemOut {
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
}

export interface OrdenMenuOut {
  nombre: string
  precio: number
  cantidad: number
  nota: string
  subtotal: number
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
  metodo_pago: MetodoPago | null
  entrega: Entrega
  mesa_ids: number[]
  mesas: string[]
  mesa_liberada: boolean
  minutos_espera: number
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
  costo_unitario: number
  valor: number
  activo: boolean
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
  fecha?: string
  hora_apertura?: string
  monto_apertura?: number
  hora_cierre?: string | null
  monto_contado?: number | null
  total_sistema?: number | null
  diferencia?: number | null
  notas?: string
  total_vendido: number
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
  modo_impresion: 'terminal' | 'estacion'
  // Toggle guardado (admin) y disponibilidad efectiva (toggle + API keys)
  voz_habilitada: boolean
  voz_disponible: boolean
  exigir_caja_abierta: boolean
  // Ventana de la tanda en cocina (minutos); 0 = apagada
  cocina_bulk_min: number
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

export interface VozRespuesta {
  log_id: number
  transcripcion: string
  items_resueltos: VozItemResuelto[]
  no_encontrados: string[]
  notas: string
  latencia_ms: number
}

export type VozResultado = 'aceptado' | 'corregido' | 'descartado'

export interface VozPanel {
  logs: {
    id: number
    hora: string
    transcripcion: string
    interpretacion: { items: { plato_id: number; cantidad: number }[]; no_encontrados: string[]; notas: string }
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
  empaque: Empaque
  nota?: string
}

export const api = {
  menuHoy: () =>
    request<{ categorias: string[]; platos: Plato[]; menus: MenuHoy[] }>('/api/menu/today'),

  config: () => request<ConfigOut>('/api/config'),

  crearOrden: (
    items: { plato_id: number; cantidad: number; empaque: Empaque; nota?: string }[],
    duracionSeg?: number,
    origen: OrigenPedido = 'tactil',
    mesaIds: number[] = [],
    entrega: Entrega = 'junto',
    menus: MenuOrdenIn[] = [],
  ) =>
    request<{ orden: OrdenOut; local: DatosLocal }>('/api/orders', {
      method: 'POST',
      body: JSON.stringify({
        items, menus, duracion_seg: duracionSeg, origen, mesa_ids: mesaIds, entrega,
      }),
    }),

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
  insumos: () => request<{ insumos: Insumo[]; valor_inventario: number }>('/api/insumos', {}, true),

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

  kardex: (insumoId?: number) =>
    request<{ movimientos: MovimientoKardex[] }>(
      `/api/insumos/kardex${insumoId ? `?insumo_id=${insumoId}` : ''}`, {}, true),

  receta: (platoId: number) => request<RecetaDetalle>(`/api/insumos/recetas/${platoId}`, {}, true),

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

  ordenesHoy: () => request<{ ordenes: OrdenOut[]; total_vendido: number }>('/api/orders/today'),

  // --- Estación de impresión (/ticketera) ---
  pendientesImpresion: () =>
    request<{ ordenes: OrdenOut[]; local: DatosLocal }>('/api/orders/pending-print'),

  marcarImpreso: (id: number) =>
    request<{ id: number; impreso: boolean }>(`/api/orders/${id}/printed`, { method: 'POST' }),

  reimprimirOrden: (id: number) =>
    request<{ id: number; impreso: boolean }>(`/api/orders/${id}/reprint`, { method: 'POST' }),

  descartarPendientes: () =>
    request<{ descartadas: number }>('/api/orders/pending-print/clear', { method: 'POST' }),

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

  // --- Plantillas de menú encadenado (admin) ---
  plantillas: () => request<{ plantillas: PlantillaMenu[] }>('/api/menu/plantillas', {}, true),

  guardarPlantillas: (plantillas: PlantillaMenuIn[]) =>
    request<{ plantillas: PlantillaMenu[] }>('/api/menu/plantillas', {
      method: 'PUT',
      body: JSON.stringify({ plantillas }),
    }, true),

  menuAnterior: () => request<{ fecha: string | null; platos: Plato[] }>('/api/menu/previous', {}, true),

  guardarMenu: (platos: { id?: number; nombre: string; categoria: string; precio: number; activo_hoy: boolean; sale_al_momento?: boolean; sinonimos?: string[] }[]) =>
    request<{ categorias: string[]; platos: Plato[] }>('/api/menu/today', {
      method: 'PUT',
      body: JSON.stringify({ platos }),
    }, true),

  cancelacionesHoy: () =>
    request<{
      cancelaciones: { id: number; fecha: string; hora: string; total: number; items: { nombre: string; cantidad: number; precio: number }[] }[]
    }>('/api/cancellations/today', {}, true),

  guardarConfig: (config: Partial<ConfigOut>) =>
    request<ConfigOut>('/api/config', { method: 'PUT', body: JSON.stringify(config) }, true),

  statsHoy: () => request<StatsOut>('/api/stats/today', {}, true),

  statsRango: (desde: string, hasta: string) =>
    request<StatsOut>(`/api/stats/range?desde=${desde}&hasta=${hasta}`, {}, true),

  // Descarga el CSV de ventas (necesita el token, así que va por
  // fetch + blob en vez de un <a href> directo). Sin fechas: hoy.
  descargarVentasCsv: async (desde?: string, hasta?: string) => {
    const params = desde && hasta ? `?desde=${desde}&hasta=${hasta}` : ''
    const cabeceras: Record<string, string> = { 'X-Admin-Token': getAdminToken() }
    if (getPinLocal()) cabeceras['X-Pin-Local'] = getPinLocal()
    const res = await fetch(`/api/stats/export${params}`, { headers: cabeceras })
    if (!res.ok) throw new ApiError(res.status, `Error ${res.status}`)
    const blob = await res.blob()
    const nombre = res.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] ?? 'ventas.csv'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = nombre
    a.click()
    URL.revokeObjectURL(url)
  },
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
    alternativas: { plato_id: number; recargo: number }[]
  }[]
}

// Lo que suma UNA unidad del menú armado (precio + recargos elegidos);
// los extras van aparte porque no se multiplican por la cantidad de menús
export function precioUnitarioMenu(linea: MenuCarrito): number {
  let unitario = linea.menu.precio
  for (const tiempo of linea.menu.tiempos) {
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

export function subtotalMenu(linea: MenuCarrito): number {
  return precioUnitarioMenu(linea) * linea.cantidad + subtotalExtras(linea)
}

export function soles(monto: number): string {
  return `S/ ${monto.toFixed(2)}`
}

export const NOMBRE_CATEGORIA: Record<string, string> = {
  entrada: 'Entradas',
  fondo: 'Platos de fondo',
  bebida: 'Bebidas',
  postre: 'Postres',
}
