import type { ReactNode } from 'react'

interface BarraProps {
  etiqueta: string
  valor: number
  min: number
  max: number
  paso: number
  onChange: (v: number) => void
  formato?: (v: number) => string
  base?: number // el valor de la ciudad: si te alejas, se marca y se puede volver
}

/** Barra deslizante con el número grande y un botón para volver al valor de la ciudad. */
export function Barra({ etiqueta, valor, min, max, paso, onChange, formato, base }: BarraProps) {
  const movido = base !== undefined && Math.abs(valor - base) > paso / 2
  return (
    <label className="es-barra">
      <span className="es-barra-cab">
        <span>{etiqueta}</span>
        <strong>{formato ? formato(valor) : valor}</strong>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={paso}
        value={valor}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {movido && (
        <button type="button" className="es-volver" onClick={() => onChange(base!)}>
          Volver a {formato ? formato(base!) : base}
        </button>
      )}
    </label>
  )
}

interface ChipsProps<T extends string | number | boolean> {
  opciones: { valor: T; texto: ReactNode }[]
  valor: T
  onChange: (v: T) => void
}

export function Chips<T extends string | number | boolean>({ opciones, valor, onChange }: ChipsProps<T>) {
  return (
    <div className="es-chips" role="radiogroup">
      {opciones.map((o) => (
        <button
          key={String(o.valor)}
          type="button"
          role="radio"
          aria-checked={o.valor === valor}
          className={o.valor === valor ? 'es-chip es-chip-on' : 'es-chip'}
          onClick={() => onChange(o.valor)}
        >
          {o.texto}
        </button>
      ))}
    </div>
  )
}

export function Dato({ titulo, valor, nota, tono }: { titulo: string; valor: ReactNode; nota?: ReactNode; tono?: 'bien' | 'mal' }) {
  return (
    <div className="es-dato">
      <span className="es-dato-titulo">{titulo}</span>
      <span className={`es-dato-valor ${tono ? `es-${tono}` : ''}`}>{valor}</span>
      {nota && <span className="es-dato-nota">{nota}</span>}
    </div>
  )
}
