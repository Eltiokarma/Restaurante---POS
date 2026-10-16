import type { Area, Calculo, Modalidad, Trabajador, Turno } from './api'
import { Chips } from './Controles'
import { soles } from './formato'

interface Props {
  planilla: Trabajador[]
  dias: number
  conNoche: boolean
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

const TURNOS: { valor: Turno; texto: string }[] = [
  { valor: 'dia', texto: 'Día' },
  { valor: 'noche', texto: 'Noche' },
  { valor: 'ambos', texto: 'Día y noche' },
]

const NUEVO: Trabajador = {
  puesto: '',
  monto: 50,
  modalidad: 'diario',
  cantidad: 1,
  area: 'cocina',
  dias: null,
  turno: 'dia',
}

/** Cuánto le cuesta esta persona al mes (sin cargas de planilla). */
function delMes(t: Trabajador, dias: number) {
  return t.modalidad === 'diario' ? t.monto * (t.dias ?? dias) * t.cantidad : t.monto * t.cantidad
}

/** La planilla propia: una fila por persona (o por grupo que gana igual). */
export function Planilla({ planilla, dias, conNoche, onChange }: Props) {
  const cambiar = (i: number, cambios: Partial<Trabajador>) =>
    onChange(planilla.map((t, k) => (k === i ? { ...t, ...cambios } : t)))

  return (
    <div className="es-planilla">
      <p className="es-nota">
        Una fila por persona: así cada uno tiene su sueldo o jornal. Si varios ganan igual, usa “Cuántos”.
      </p>
      {planilla.map((t, i) => (
        <div key={i} className="es-trabajador">
          <div className="es-fila">
            <input
              value={t.puesto}
              onChange={(e) => cambiar(i, { puesto: e.target.value })}
              placeholder="Puesto o nombre (p. ej. Ayudante – Rosa)"
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
          {conNoche && <Chips valor={t.turno} onChange={(tu) => cambiar(i, { turno: tu })} opciones={TURNOS} />}
          <div className="es-fila es-pie-trabajador">
            <span className="es-nota">
              {soles(delMes(t, dias))} al mes
              {t.modalidad === 'quincenal' ? ` (2 pagos de ${soles(delMes(t, dias) / 2)})` : ''}
            </span>
            <button
              type="button"
              className="es-secundario"
              onClick={() => onChange([...planilla.slice(0, i + 1), { ...t, puesto: '' }, ...planilla.slice(i + 1)])}
            >
              Duplicar
            </button>
          </div>
        </div>
      ))}
      <button type="button" className="es-secundario" onClick={() => onChange([...planilla, NUEVO])}>
        + Agregar persona
      </button>
    </div>
  )
}

/** Planilla inicial a partir de la automática: una fila por persona. */
export function planillaDesde(calculo: Calculo | null): Trabajador[] {
  const fila = (puesto: string, monto: number, area: Area, turno: Turno = 'dia'): Trabajador => ({
    puesto,
    monto,
    modalidad: 'mensual',
    cantidad: 1,
    area,
    dias: null,
    turno,
  })
  if (!calculo) return [fila('Cocinero', 1300, 'cocina')]
  const l = calculo.local
  const filas: Trabajador[] = []
  // las filas automáticas del calendario dicen cuántos hay de cada puesto y turno
  for (const f of calculo.pagos.filas) {
    const monto = f.puesto.startsWith('Cocinero') ? l.sueldo_cocinero : f.area === 'salon' ? l.sueldo_mozo : l.sueldo_ayudante
    for (let k = 1; k <= f.cantidad; k++)
      filas.push(fila(f.cantidad > 1 ? `${f.puesto} ${k}` : f.puesto, monto, f.area, f.turno))
  }
  return filas.length ? filas : [fila('Cocinero', l.sueldo_cocinero, 'cocina')]
}

export function CalendarioPagos({ calculo, dias, conNoche }: { calculo: Calculo; dias: number; conNoche: boolean }) {
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
          {conNoche && (
            <>
              <tr>
                <th>Personal del día</th>
                <td>{soles(p.por_turno.dia)}</td>
              </tr>
              <tr>
                <th>Personal de la noche</th>
                <td>{soles(p.por_turno.noche)}</td>
              </tr>
              {p.por_turno.ambos > 0 && (
                <tr>
                  <th>Personal de los dos turnos</th>
                  <td>{soles(p.por_turno.ambos)}</td>
                </tr>
              )}
            </>
          )}
        </tbody>
      </table>
    </div>
  )
}
