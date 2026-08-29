// Cliente HTTP mínimo para la API del backend.

export interface Plato {
  id: number
  nombre: string
  categoria: string
  precio: number
  activo_hoy: boolean
  sinonimos: string[]
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
}

export interface OrdenItemOut {
  nombre: string
  precio: number
  cantidad: number
  empaque: Empaque
  subtotal: number
}

export interface OrdenOut {
  id: number
  numero_orden_dia: number
  fecha: string
  hora: string
  total: number
  estado: string
  tipo_servicio: TipoServicio
  minutos_espera: number
  items: OrdenItemOut[]
}

export type TipoServicio = 'sala' | 'llevar' | 'mixto'

export const NOMBRE_SERVICIO: Record<TipoServicio, string> = {
  sala: '🍽 En sala',
  llevar: '🛍 Para llevar',
  mixto: '🥡 Mixto',
}

export interface CajaEstado {
  abierta: boolean
  cerrada: boolean
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

export const api = {
  menuHoy: () => request<{ categorias: string[]; platos: Plato[] }>('/api/menu/today'),

  config: () => request<ConfigOut>('/api/config'),

  crearOrden: (
    items: { plato_id: number; cantidad: number; empaque: Empaque }[],
    duracionSeg?: number,
    origen: OrigenPedido = 'tactil',
  ) =>
    request<{ orden: OrdenOut; local: DatosLocal }>('/api/orders', {
      method: 'POST',
      body: JSON.stringify({ items, duracion_seg: duracionSeg, origen }),
    }),

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

  menuAnterior: () => request<{ fecha: string | null; platos: Plato[] }>('/api/menu/previous', {}, true),

  guardarMenu: (platos: { id?: number; nombre: string; categoria: string; precio: number; activo_hoy: boolean; sinonimos?: string[] }[]) =>
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

export function soles(monto: number): string {
  return `S/ ${monto.toFixed(2)}`
}

export const NOMBRE_CATEGORIA: Record<string, string> = {
  entrada: 'Entradas',
  fondo: 'Platos de fondo',
  bebida: 'Bebidas',
  postre: 'Postres',
}
