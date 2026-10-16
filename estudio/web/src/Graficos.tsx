import { useRef, useState } from 'react'
import { miles, soles } from './formato'

const AN = 640
const AL = 260
const M = { izq: 56, der: 16, arr: 16, aba: 32 }
const ANCHO = AN - M.izq - M.der
const ALTO = AL - M.arr - M.aba

/** Marcas "lindas" para el eje Y que incluyen el cero. */
function marcas(min: number, max: number, n = 5): number[] {
  const lo = Math.min(0, min)
  const hi = Math.max(0, max)
  const crudo = (hi - lo) / n || 1
  const mag = 10 ** Math.floor(Math.log10(crudo))
  const paso = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((p) => p >= crudo) ?? crudo
  const salida: number[] = []
  for (let v = Math.floor(lo / paso) * paso; v <= hi + paso * 0.001; v += paso) salida.push(Math.round(v))
  if (salida[salida.length - 1] < hi) salida.push(salida[salida.length - 1] + paso)
  return salida
}

function useHover(n: number, xDe: (i: number) => number) {
  const ref = useRef<SVGSVGElement>(null)
  const [i, setI] = useState<number | null>(null)
  const mover = (e: React.PointerEvent) => {
    const svg = ref.current
    if (!svg) return
    const caja = svg.getBoundingClientRect()
    const x = ((e.clientX - caja.left) / caja.width) * AN
    let mejor = 0
    for (let k = 1; k < n; k++) if (Math.abs(xDe(k) - x) < Math.abs(xDe(mejor) - x)) mejor = k
    setI(mejor)
  }
  return { ref, i, mover, salir: () => setI(null) }
}

function EjeY({ ticks, y }: { ticks: number[]; y: (v: number) => number }) {
  return (
    <g>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={M.izq} x2={AN - M.der} y1={y(t)} y2={y(t)} className={t === 0 ? 'es-cero' : 'es-grilla'} />
          <text x={M.izq - 8} y={y(t)} dy="0.32em" textAnchor="end" className="es-eje">
            {miles(t)}
          </text>
        </g>
      ))}
    </g>
  )
}

interface CurvaProps {
  puntos: { q: number; utilidad: number }[]
  q: number
  equilibrio: number | null
}

/** Utilidad del mes según los menús que vendas al día. */
export function CurvaUtilidad({ puntos, q, equilibrio }: CurvaProps) {
  const qMax = puntos[puntos.length - 1]?.q ?? 1
  const vals = puntos.map((p) => p.utilidad)
  const ticks = marcas(Math.min(...vals), Math.max(...vals))
  const yMin = ticks[0]
  const yMax = ticks[ticks.length - 1]
  const x = (v: number) => M.izq + (v / qMax) * ANCHO
  const y = (v: number) => M.arr + ((yMax - v) / (yMax - yMin)) * ALTO
  const h = useHover(puntos.length, (k) => x(puntos[k].q))
  const linea = puntos.map((p, k) => `${k ? 'L' : 'M'}${x(p.q).toFixed(1)},${y(p.utilidad).toFixed(1)}`).join('')
  const sel = h.i !== null ? puntos[h.i] : null
  const xTicks = [0, 50, 100, 150, 200, 300, 400, 500, 600].filter((t) => t <= qMax)
  return (
    <figure className="es-grafico">
      <figcaption>Utilidad del mes según los menús que vendes al día</figcaption>
      <div className="es-lienzo">
        <svg
          ref={h.ref}
          viewBox={`0 0 ${AN} ${AL}`}
          role="img"
          aria-label="Utilidad mensual por menús al día"
          onPointerMove={h.mover}
          onPointerDown={h.mover}
          onPointerLeave={h.salir}
        >
          <EjeY ticks={ticks} y={y} />
          {xTicks.map((t) => (
            <text key={t} x={x(t)} y={AL - 10} textAnchor="middle" className="es-eje">
              {t}
            </text>
          ))}
          {equilibrio !== null && equilibrio <= qMax && (
            <g>
              <line x1={x(equilibrio)} x2={x(equilibrio)} y1={M.arr} y2={M.arr + ALTO} className="es-guia" />
              <text
                x={x(equilibrio) + (equilibrio > qMax * 0.75 ? -6 : 6)}
                y={M.arr + 12}
                textAnchor={equilibrio > qMax * 0.75 ? 'end' : 'start'}
                className="es-eje"
              >
                equilibrio {equilibrio}
              </text>
            </g>
          )}
          <line x1={x(q)} x2={x(q)} y1={M.arr} y2={M.arr + ALTO} className="es-guia es-guia-q" />
          <path d={linea} className="es-linea" />
          {sel && (
            <g>
              <line x1={x(sel.q)} x2={x(sel.q)} y1={M.arr} y2={M.arr + ALTO} className="es-cruz" />
              <circle cx={x(sel.q)} cy={y(sel.utilidad)} r={5} className="es-punto" />
            </g>
          )}
        </svg>
        {sel && (
          <div className="es-tip" style={{ left: `${(x(sel.q) / AN) * 100}%` }}>
            <strong>{sel.q} menús/día</strong>
            <span>{soles(sel.utilidad)} al mes</span>
          </div>
        )}
      </div>
    </figure>
  )
}

interface FlujoProps {
  inversion: number
  anios: { anio: number; flujo: number; acumulado: number }[]
}

/** Barras: lo que te deja cada año. Línea: la caja acumulada desde la inversión. */
export function GraficoFlujo({ inversion, anios }: FlujoProps) {
  const etiquetas = ['Inicio', ...anios.map((a) => String(a.anio))]
  const flujos = [-inversion, ...anios.map((a) => a.flujo)]
  const acum = [-inversion, ...anios.map((a) => a.acumulado)]
  const ticks = marcas(Math.min(...flujos, ...acum), Math.max(...flujos, ...acum))
  const yMin = ticks[0]
  const yMax = ticks[ticks.length - 1]
  const n = etiquetas.length
  const banda = ANCHO / n
  const x = (k: number) => M.izq + banda * (k + 0.5)
  const y = (v: number) => M.arr + ((yMax - v) / (yMax - yMin)) * ALTO
  const h = useHover(n, x)
  const anchoBarra = Math.min(36, banda - 6)
  const linea = acum.map((v, k) => `${k ? 'L' : 'M'}${x(k).toFixed(1)},${y(v).toFixed(1)}`).join('')
  return (
    <figure className="es-grafico">
      <figcaption>Caja de cada año y caja acumulada (después de recuperar la inversión)</figcaption>
      <div className="es-leyenda">
        <span>
          <i className="es-muestra es-muestra-barra" /> Lo que deja el año
        </span>
        <span>
          <i className="es-muestra es-muestra-linea" /> Acumulado
        </span>
      </div>
      <div className="es-lienzo">
        <svg
          ref={h.ref}
          viewBox={`0 0 ${AN} ${AL}`}
          role="img"
          aria-label="Flujo de caja por año"
          onPointerMove={h.mover}
          onPointerDown={h.mover}
          onPointerLeave={h.salir}
        >
          <EjeY ticks={ticks} y={y} />
          {flujos.map((v, k) => {
            const y0 = y(0)
            const y1 = y(v)
            const alto = Math.max(1, Math.abs(y1 - y0))
            return (
              <rect
                key={k}
                x={x(k) - anchoBarra / 2}
                width={anchoBarra}
                y={Math.min(y0, y1)}
                height={alto}
                rx={3}
                className={h.i === k ? 'es-barra-dato es-barra-sel' : 'es-barra-dato'}
              />
            )
          })}
          <path d={linea} className="es-linea es-linea-2" />
          {acum.map((v, k) => (
            <circle key={k} cx={x(k)} cy={y(v)} r={4} className="es-punto-2" />
          ))}
          {etiquetas.map((t, k) =>
            n > 8 && k % 2 === 1 ? null : (
              <text key={t} x={x(k)} y={AL - 10} textAnchor="middle" className="es-eje">
                {t}
              </text>
            ),
          )}
        </svg>
        {h.i !== null && (
          <div className="es-tip" style={{ left: `${(x(h.i) / AN) * 100}%` }}>
            <strong>{etiquetas[h.i]}</strong>
            <span>
              {h.i === 0 ? 'Inversión' : 'Deja'} {soles(flujos[h.i])}
            </span>
            <span>Acumulado {soles(acum[h.i])}</span>
          </div>
        )}
      </div>
    </figure>
  )
}
