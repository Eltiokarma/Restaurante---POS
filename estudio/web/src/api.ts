// Cliente único del servicio del estudio. Todo pide el token (X-Token).

const CLAVE_TOKEN = 'estudio-token'

export function tokenGuardado(): string {
  try {
    return localStorage.getItem(CLAVE_TOKEN) ?? ''
  } catch {
    return ''
  }
}

export function guardarToken(t: string) {
  try {
    if (t) localStorage.setItem(CLAVE_TOKEN, t)
    else localStorage.removeItem(CLAVE_TOKEN)
  } catch {
    /* sin almacenamiento: se pide el token cada vez */
  }
}

let token = tokenGuardado()
export function usarToken(t: string) {
  token = t
}

export class ErrorToken extends Error {}

async function pedir<T>(ruta: string, opciones: RequestInit = {}): Promise<T> {
  const r = await fetch(`/api${ruta}`, {
    ...opciones,
    headers: { 'Content-Type': 'application/json', 'X-Token': token, ...(opciones.headers ?? {}) },
  })
  if (r.status === 401) throw new ErrorToken('Token inválido')
  if (!r.ok) {
    const cuerpo = await r.json().catch(() => ({}))
    throw new Error(typeof cuerpo.detail === 'string' ? cuerpo.detail : `Error ${r.status}`)
  }
  return r.status === 204 ? (undefined as T) : r.json()
}

export interface Ciudad {
  id: string
  nombre: string
  confianza: string | null
  zonas: { id: number; nombre: string; tipo: string }[]
}

export interface ValoresLocal {
  precio: number
  insumos: number
  alquiler_mes: number
  sueldo_cocinero: number
  sueldo_ayudante: number
  sueldo_mozo: number
  gas_balon45: number
  servicios_mes: number
}

export interface Escenario extends Partial<ValoresLocal> {
  ciudad_id: string
  zona_id: number | null
  segmento: 'popular' | 'ejecutivo'
  anio: number
  formal: boolean
  balones: number
  sueldo_dueno: boolean
  q: number
}

export interface Calculo {
  local: ValoresLocal & { pmin: number; pmax: number; precio_propio: boolean }
  equilibrio_menus_dia: number | null
  precio_minimo_a_q: number
  mes_a_q: {
    ventas: number
    fijos: number
    utilidad: number
    margen: number
    cocina: number
    mozos: number
    costo_variable_menu: number
    precio_sin_igv: number
    personal: number
    alquiler: number
    gas: number
  }
  anio_montecarlo: { prob_perdida: number; p10: number; p50: number; p90: number }
  curva: { q: number; utilidad: number }[]
}

export type Regimen = 'informal' | 'nuevo_rus' | 'rer' | 'mype'

export interface SupuestosFlujo {
  inversion: number
  meses_arranque: number
  arranque_desde: number
  crecimiento_q: number
  inflacion: number
  alza_precio: number
  alza_rmv: number
  tasa_descuento: number
  regimen: Regimen
}

export interface AnioFlujo {
  anio: number
  igv: number
  rmv: number
  precio: number
  menus_dia: number
  ventas: number
  igv_pagado: number
  utilidad_operativa: number
  impuesto: number
  flujo: number
  acumulado: number
  descontado_acumulado: number
}

export interface Flujo {
  regimen: Regimen
  nombre: string
  anios: AnioFlujo[]
  van: number
  tir: number | null
  recupero: number | null
  recupero_descontado: number | null
  alertas: string[]
  comparacion: {
    regimen: Regimen
    nombre: string
    van: number
    tir: number | null
    recupero: number | null
    impuestos_10a: number
    flujo_10a: number
    alertas: string[]
  }[]
  supuestos: Record<string, string>
}

export interface Guardado {
  id: number
  nombre: string
  datos: { escenario: Escenario; supuestos: SupuestosFlujo }
  creado: string
}

export const api = {
  ciudades: () => pedir<Ciudad[]>('/ciudades'),
  calcular: (e: Escenario) => pedir<Calculo>('/calcular', { method: 'POST', body: JSON.stringify(e) }),
  flujo: (e: Escenario, s: SupuestosFlujo) =>
    pedir<Flujo>('/flujo', { method: 'POST', body: JSON.stringify({ ...e, ...s }) }),
  escenarios: () => pedir<Guardado[]>('/escenarios'),
  guardar: (nombre: string, datos: Guardado['datos']) =>
    pedir<{ id: number }>('/escenarios', { method: 'POST', body: JSON.stringify({ nombre, datos }) }),
  borrar: (id: number) => pedir<void>(`/escenarios/${id}`, { method: 'DELETE' }),
}
