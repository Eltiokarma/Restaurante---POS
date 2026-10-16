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

export type Modalidad = 'mensual' | 'quincenal' | 'diario'
export type Area = 'cocina' | 'salon' | 'otro'

export type Turno = 'dia' | 'noche' | 'ambos'

export interface Trabajador {
  puesto: string
  monto: number
  modalidad: Modalidad
  cantidad: number
  area: Area
  dias: number | null
  turno: Turno
}

export interface Noche {
  q: number
  precio: number
  insumos: number
  dias: number | null
  balones: number
  servicios: number
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
  dias: number
  planilla: Trabajador[]
  noche: Noche | null
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
    ventas_dia: number
    ventas_noche: number
    platos_noche_mes: number
    contrib_noche: number
    contrib_dia: number
  }
  anio_montecarlo: { prob_perdida: number; p10: number; p50: number; p90: number }
  curva: { q: number; utilidad: number }[]
  pagos: {
    jornales_por_dia: number
    quincena_15: number
    fin_de_mes: number
    aportes_fin_de_mes: number
    filas: { puesto: string; cantidad: number; modalidad: Modalidad; area: Area; turno: Turno; costo_mes: number }[]
    por_turno: Record<Turno, number>
  }
}

export interface Sensibilidad {
  tornado: { variable: string; nombre: string; base: number; abajo: number; arriba: number; rango: number }[]
  quiebres: { variable: string; nombre: string; cambio: number | null }[]
  matriz: { precios: number[]; volumenes: number[]; utilidad: number[][] }
}

export type TipoPlato = 'entrada' | 'segundo' | 'sopa' | 'bebida' | 'postre' | 'extra'

export interface Insumo {
  id: number
  nombre: string
  unidad: string
  precio: number
  merma: number
  categoria: string | null
  actualizado: string | null
}

export interface Plato {
  id: number
  nombre: string
  tipo: TipoPlato
  porciones: number
  precio: number | null
  vendidos: number | null
  notas: string | null
  items: { insumo_id: number; cantidad: number }[]
}

export type ClasePlato = 'estrella' | 'caballo' | 'rompecabezas' | 'perro'

export interface AnalisisPlatos {
  platos: {
    id: number
    nombre: string
    tipo: TipoPlato
    precio: number | null
    vendidos: number | null
    costo_porcion: number
    costo_venta: number
    es_menu: boolean
    desglose: { insumo_id: number; insumo: string; costo: number; parte: number }[]
    precio_sin_igv: number | null
    margen: number | null
    costo_pct: number | null
    clase: ClasePlato | null
    consejo: string | null
    popularidad: number | null
    sin_receta: boolean
    umbral_popularidad?: number
    margen_promedio?: number
  }[]
  costo_entrada_bebida_promedio: number
  menu: { costo: number; precio_promedio: number | null; por_insumo: { insumo_id: number; insumo: string; costo: number }[] }
  gasto_semana: number
  sin_receta: string[]
  pareto: { insumo_id: number; insumo: string; gasto_semana: number; parte: number; acumulado: number; menu_mas_10pct: number }[]
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

export interface Ficha {
  categoria: string
  descripcion: string
  supuestos: string[]
  fuente: string
}

export interface Comparado {
  id: number
  nombre: string
  error?: string
  ficha?: Ficha | null
  ventas_mes: number
  utilidad_mes: number
  margen: number
  ingreso_dueno_mes: number
  equilibrio: number | null
  precio_minimo: number
  prob_perdida: number
  anio_malo: number
  anio_tipico: number
  personal_pct: number
  insumos_pct: number
  alquiler_pct: number
  trabajadores: number
  precio: number
  menus_dia: number
  formal: boolean
  noche: boolean
  regimen: string
  inversion: number
  van: number
  tir: number | null
  recupero: number | null
  alertas: string[]
  quiebres: Record<string, number | null>
  tornado: { variable: string; nombre: string; rango: number }[]
}

export interface DecisionCorrida {
  delta_precio: number
  precio: number
  calidad: 'economica' | 'estandar' | 'generosa'
  mezcla: number | null
  noche: boolean
  utilidad_media: number
  utilidad_peor: number
  utilidad_mejor: number
  prob_perdida_max: number
  van_medio: number
  van_peor: number
  q_min: number
  q_max: number
}

export interface FilaCorrida {
  delta_precio: number
  calidad: string
  mezcla: number | null
  noche: boolean
  elasticidad: number
  q: number
  precio: number
  utilidad: number
  prob_perdida: number
  van: number
}

export type Curvas = Record<string, { precio: number; q: number; utilidad: number }[]>

export interface Corrida {
  id: number
  nombre: string
  tipo: 'decisiones' | 'decisiones_todos' | 'estres'
  estado: 'pendiente' | 'corriendo' | 'lista' | 'error' | 'interrumpida'
  progreso: number
  total: number
  error: string | null
  creado: string
  terminado: string | null
  resultado?: {
    // decisiones
    base_nombre?: string
    q0?: number
    precio0?: number
    factores?: { precio: number[]; calidad: string[]; mezcla: (number | null)[]; noche: boolean[]; elasticidad: number[] }
    filas?: FilaCorrida[]
    decisiones?: DecisionCorrida[]
    base?: DecisionCorrida | null
    supuestos?: Record<string, string>
    mezcla?: { costo_res: number; costo_otros: number; acompanamiento: number; parte_actual: number } | null
    curvas?: Curvas
    // estrés
    golpes?: { clave: string; nombre: string }[]
    negocios?: {
      id: number
      nombre: string
      categoria?: string | null
      error?: string
      // decisiones de todos
      precio0?: number
      q0?: number
      base?: DecisionCorrida | null
      mejor?: DecisionCorrida | null
      top?: DecisionCorrida[]
      mejor_sin_noche?: DecisionCorrida | null
      mejor_sin_cambiar_turno?: DecisionCorrida | null
      curvas?: Curvas
      // estrés
      golpes?: { golpe: string; nombre: string; utilidad: number; ingreso_dueno: number; prob_perdida: number }[]
    }[]
  } | null
}

export interface Guardado {
  id: number
  nombre: string
  datos: { escenario: Escenario; supuestos: SupuestosFlujo; ficha?: Ficha }
  creado: string
}

export const api = {
  ciudades: () => pedir<Ciudad[]>('/ciudades'),
  calcular: (e: Escenario) => pedir<Calculo>('/calcular', { method: 'POST', body: JSON.stringify(e) }),
  flujo: (e: Escenario, s: SupuestosFlujo) =>
    pedir<Flujo>('/flujo', { method: 'POST', body: JSON.stringify({ ...e, ...s }) }),
  sensibilidad: (e: Escenario, delta: number) =>
    pedir<Sensibilidad>('/sensibilidad', { method: 'POST', body: JSON.stringify({ ...e, delta }) }),
  insumos: () => pedir<Insumo[]>('/insumos'),
  guardarInsumo: (i: Omit<Insumo, 'id' | 'actualizado'>, id?: number) =>
    pedir<Insumo>(id ? `/insumos/${id}` : '/insumos', { method: id ? 'PUT' : 'POST', body: JSON.stringify(i) }),
  borrarInsumo: (id: number) => pedir<void>(`/insumos/${id}`, { method: 'DELETE' }),
  platos: () => pedir<Plato[]>('/platos'),
  guardarPlato: (p: Omit<Plato, 'id'>, id?: number) =>
    pedir<Plato>(id ? `/platos/${id}` : '/platos', { method: id ? 'PUT' : 'POST', body: JSON.stringify(p) }),
  borrarPlato: (id: number) => pedir<void>(`/platos/${id}`, { method: 'DELETE' }),
  analisis: (igv: number, formal: boolean) => pedir<AnalisisPlatos>(`/platos/analisis?igv=${igv}&formal=${formal}`),
  comparar: (ids: number[]) => pedir<Comparado[]>('/comparar', { method: 'POST', body: JSON.stringify({ ids }) }),
  corridas: () => pedir<Corrida[]>('/corridas'),
  corrida: (id: number) => pedir<Corrida>(`/corridas/${id}`),
  lanzarCorrida: (cuerpo: { tipo: 'decisiones' | 'decisiones_todos' | 'estres'; escenario_id?: number; ids?: number[]; usar_recetas?: boolean }) =>
    pedir<Corrida>('/corridas', { method: 'POST', body: JSON.stringify(cuerpo) }),
  borrarCorrida: (id: number) => pedir<void>(`/corridas/${id}`, { method: 'DELETE' }),
  escenarios: () => pedir<Guardado[]>('/escenarios'),
  guardar: (nombre: string, datos: Guardado['datos']) =>
    pedir<{ id: number }>('/escenarios', { method: 'POST', body: JSON.stringify({ nombre, datos }) }),
  borrar: (id: number) => pedir<void>(`/escenarios/${id}`, { method: 'DELETE' }),
}
