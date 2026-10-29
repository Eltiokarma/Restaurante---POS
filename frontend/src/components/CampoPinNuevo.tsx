import { useState } from 'react'

/**
 * Para PONER un PIN (persona del equipo, PIN del cajón): se escribe dos
 * veces y un botón deja verlo (pedido del dueño: con los asteriscos no se
 * podía revisar lo escrito). Avisa con `onListo` el PIN solo cuando es
 * válido y las dos veces coinciden; si no, `null`. Para vaciarlo tras
 * guardar, el padre le cambia la `key`.
 */
export function CampoPinNuevo({ onListo, minimo = 4, largo = 6, rotulo = 'PIN' }: {
  onListo: (pin: string | null) => void
  minimo?: number
  largo?: number
  rotulo?: string
}) {
  const [pin, setPin] = useState('')
  const [repetido, setRepetido] = useState('')
  const [ver, setVer] = useState(false)

  const avisar = (a: string, b: string) => onListo(a.length >= minimo && a === b ? a : null)
  const limpiar = (v: string) => v.replace(/\D/g, '').slice(0, largo)
  const tipo = ver ? 'text' : 'password'
  const noCoinciden = repetido.length > 0 && repetido.length >= pin.length && repetido !== pin
  const corto = pin.length > 0 && pin.length < minimo

  return (
    <div className="campo-pin-nuevo">
      <label>
        {rotulo} ({minimo} a {largo} números)
        <span className="campo-pin-fila">
          <input
            type={tipo} inputMode="numeric" autoComplete="new-password" maxLength={largo}
            value={pin}
            onChange={(e) => { const v = limpiar(e.target.value); setPin(v); avisar(v, repetido) }}
          />
          <button type="button" className="campo-pin-ver" aria-pressed={ver} onClick={() => setVer(!ver)}>
            {ver ? '🙈 Ocultar' : '👁 Ver'}
          </button>
        </span>
      </label>
      <label>
        Repite el {rotulo}
        <input
          type={tipo} inputMode="numeric" autoComplete="new-password" maxLength={largo}
          value={repetido}
          onChange={(e) => { const v = limpiar(e.target.value); setRepetido(v); avisar(pin, v) }}
        />
      </label>
      {corto && <span className="campo-pin-aviso">Le faltan números: mínimo {minimo}</span>}
      {noCoinciden && <span className="campo-pin-aviso">No coinciden: revisa los dos</span>}
      {!corto && pin.length >= minimo && pin === repetido && <span className="campo-pin-ok">✔ Coinciden</span>}
    </div>
  )
}
