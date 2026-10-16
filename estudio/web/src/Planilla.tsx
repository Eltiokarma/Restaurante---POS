import type { Area, Calculo, Modalidad, Trabajador } from './api'
import { Chips } from './Controles'
import { soles } from './formato'

interface Props {
  planilla: Trabajador[]
  dias: number
  onChange: (p: Trabajador[]) => void
}

const MODALIDADES: { valor: Modalidad; texto: string }[] = [
  { valor: 'mensual', texto: 'Mensual' },
  { valor: 'quincenal', texto: 'Quincenal' },
  { valor: 'diario', texto: 'Por día' },
]

const AREAS: { valor: Area; texto: string }[] = [
  { valor: 'cocina', texto: 'Cocina' },
  { valor: 'salon', texto: 'Salón' },
  { valor: 'otro', texto: 'Otro' },
]

const NUEVO: Trabajador = { puesto: '', monto: 50, modalidad: 'diario', cantidad: 1, area: 'cocina', dias: null }

/** La planilla propia: cada fila es un puesto, cuántos son y cómo se les paga. */
export function Planilla({ planilla, dias, onChange }: Props) {
  const cambiar = (i: number, cambios: Partial<Trabajador>) =>
    onChange(planilla.map((t, k) => (k === i ? { ...t, ...cambios } : t)))

  return (
    <div className="es-planilla">
      {planilla.map((t, i) => (
        <div key={i} className="es-trabajador">
          <div className="es-fila">
            <input
              value={t.puesto}
              onChange={(e) => cambiar(i, { puesto: e.target.value })}
              placeholder="Puesto (p. ej. Ayudante)"
              aria-label="Puesto"
            />
            <button
              type="button"
              className="es-quitar"
              aria-label={`Quitar ${t.puesto || 'puesto'}`}
              onClick={() => onChange(planilla.filter((_, k) => k !== i))}
            >
              ✕
            </button>
          </div>
          <Chips
            valor={t.modalidad}
            onChange={(m) =>
              cambiar(i, {
                modalidad: m,
                // al pasar de jornal a sueldo (o al revés) el monto cambia de escala
                monto:
                  m === 'diario' && t.modalidad !== 'diario'
                    ? Math.round(t.monto / 26)
                    : m !== 'diario' && t.modalidad === 'diario'
                      ? Math.round(t.monto * 26)
                      : t.monto,
              })
            }
            opciones={MODALIDADES}
          />
          <div className="es-campos">
            <label>
              <span>{t.modalidad === 'diario' ? 'Jornal por día' : 'Sueldo al mes'}</span>
              <input
                type="number"
                inputMode="decimal"
                min={0}
                value={t.monto}
                onChange={(e) => cambiar(i, { monto: Number(e.target.value) })}
              />
            </label>
            <label>
              <span>Cuántos</span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                value={t.cantidad}
                onChange={(e) => cambiar(i, { cantidad: Math.max(0, Math.round(Number(e.target.value))) })}
              />
            </label>
            {t.modalidad === 'diario' && (
              <label>
                <span>Días al mes</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={31}
                  value={t.dias ?? dias}
                  onChange={(e) => cambiar(i, { dias: Number(e.target.value) })}
                />
              </label>
            )}
          </div>
          <Chips valor={t.area} onChange={(a) => cambiar(i, { area: a })} opciones={AREAS} />
        </div>
      ))}
      <button type="button" className="es-secundario" onClick={() => onChange([...planilla, NUEVO])}>
        + Agregar puesto
      </button>
    </div>
  )
}

/** Planilla inicial a partir de la automática, para no empezar de cero. */
export function planillaDesde(calculo: Calculo | null): Trabajador[] {
  if (!calculo) return [{ ...NUEVO, puesto: 'Cocinero', modalidad: 'mensual', monto: 1300 }]
  const l = calculo.local
  const m = calculo.mes_a_q
  const filas: Trabajador[] = [
    { puesto: 'Cocinero', monto: l.sueldo_cocinero, modalidad: 'mensual', cantidad: 1, area: 'cocina', dias: null },
  ]
  if (m.cocina > 1)
    filas.push({
      puesto: 'Ayudante de cocina',
      monto: l.sueldo_ayudante,
      modalidad: 'mensual',
      cantidad: m.cocina - 1,
      area: 'cocina',
      dias: null,
    })
  filas.push({ puesto: 'Mozo', monto: l.sueldo_mozo, modalidad: 'mensual', cantidad: m.mozos, area: 'salon', dias: null })
  return filas
}

export function CalendarioPagos({ calculo, dias }: { calculo: Calculo; dias: number }) {
  const p = calculo.pagos
  return (
    <div className="es-tabla-caja">
      <table className="es-tabla">
        <caption>Cuándo sale la plata del personal</caption>
        <tbody>
          {p.jornales_por_dia > 0 && (
            <tr>
              <th>Jornales, cada día que se trabaja</th>
              <td>
                {soles(p.jornales_por_dia)} <span className="es-nota-celda">× ~{dias} días</span>
              </td>
            </tr>
          )}
          {p.quincena_15 > 0 && (
            <tr>
              <th>Quincena (día 15)</th>
              <td>{soles(p.quincena_15)}</td>
            </tr>
          )}
          <tr>
            <th>Fin de mes (sueldos)</th>
            <td>{soles(p.fin_de_mes)}</td>
          </tr>
          {p.aportes_fin_de_mes > 0 && (
            <tr>
              <th>Cargas de planilla formal (EsSalud y otras)</th>
              <td>{soles(p.aportes_fin_de_mes)}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
