const TECLAS = ['1', '2', '3', '4', '5', '6', '7', '8', '9']

/**
 * Teclado numérico grande para PINes en la tablet (candado, "¿Quién
 * eres?" y la autorización del admin): botones de 80 px, sin depender del
 * teclado del sistema. `largo` es el máximo de dígitos.
 */
export function TecladoPin({ valor, onCambiar, onOk, ocupado = false, largo = 6, minimo = 4, error, okTexto = 'OK' }: {
  valor: string
  onCambiar: (valor: string) => void
  onOk: () => void
  ocupado?: boolean
  largo?: number
  minimo?: number
  error?: string
  okTexto?: string
}) {
  const tocar = (d: string) => { if (valor.length < largo) onCambiar(valor + d) }
  return (
    <form className="teclado-pin-caja" onSubmit={(e) => { e.preventDefault(); if (valor.length >= minimo) onOk() }}>
      <div className="teclado-pin-visor" aria-live="polite">
        {valor ? '●'.repeat(valor.length) : <span className="teclado-pin-vacio">PIN</span>}
      </div>
      {error && <p className="teclado-pin-error">{error}</p>}
      <div className="teclado-pin">
        {TECLAS.map((t) => (
          <button key={t} type="button" onClick={() => tocar(t)}>{t}</button>
        ))}
        <button type="button" aria-label="Borrar" onClick={() => onCambiar(valor.slice(0, -1))}>⌫</button>
        <button type="button" onClick={() => tocar('0')}>0</button>
        <button type="submit" className="teclado-pin-ok" disabled={valor.length < minimo || ocupado}>
          {ocupado ? '…' : okTexto}
        </button>
      </div>
    </form>
  )
}
