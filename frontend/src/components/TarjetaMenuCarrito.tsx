import { useState } from 'react'
import { precioUnitarioMenu, soles, subtotalMenu, EMPAQUES, NOMBRE_EMPAQUE } from '../api'
import type { AgregadoHoy, Empaque, MenuCarrito } from '../api'
import { describirMenu } from './ArmadoMenu'

interface Props {
  linea: MenuCarrito
  numero: number // "Menú 3" en la lista
  onCambiarEleccion: (tiempoOrden: number, platoId: number) => void
  onAlternarOmitido: (tiempoOrden: number) => void
  onCambiarAgregado: (agregado: AgregadoHoy, delta: number) => void
  onCambiarCantidad: (delta: number) => void
  onDuplicar: () => void
  onCambiarEmpaque: (empaque: Empaque) => void
  onCambiarNota: (nota: string) => void
}

/**
 * Un menú del pedido como tarjeta desplegable: cerrada muestra qué lleva
 * y cuánto cuesta; abierta deja cambiar cada tiempo, quitarlo ("Sin
 * sopa", con su descuento si el admin lo configuró) y sumar agregados
 * (+1 presa, +1 refresco). El precio que se ve es el que cobra el
 * backend: base + recargos − descuentos + extras + agregados.
 */
export function TarjetaMenuCarrito({
  linea, numero, onCambiarEleccion, onAlternarOmitido, onCambiarAgregado,
  onCambiarCantidad, onDuplicar, onCambiarEmpaque, onCambiarNota,
}: Props) {
  const [abierta, setAbierta] = useState(false)
  const [cambiando, setCambiando] = useState<number | null>(null) // tiempo con las opciones abiertas

  const quitados = linea.menu.tiempos.filter((t) => linea.omitidos.includes(t.orden))
  const descuento = quitados.reduce((s, t) => s + t.descuento_si_se_quita, 0)

  return (
    <div className={`tarjeta-menu ${abierta ? 'tarjeta-menu-abierta' : ''}`}>
      <button className="tarjeta-menu-cabecera" onClick={() => setAbierta((v) => !v)}>
        <span className="tarjeta-menu-nombre">
          <strong>Menú {numero}</strong>
          {linea.cantidad > 1 && <span className="tarjeta-menu-por"> × {linea.cantidad}</span>}
          {' · '}{linea.menu.nombre}
        </span>
        <span className="tarjeta-menu-precio">{soles(subtotalMenu(linea))}</span>
        <span className="tarjeta-menu-flecha">{abierta ? '▲' : '▼'}</span>
      </button>
      {!abierta && <div className="linea-menu-detalle">{describirMenu(linea)}</div>}

      {abierta && (
        <div className="tarjeta-menu-cuerpo">
          {linea.menu.tiempos.map((t) => {
            const quitado = linea.omitidos.includes(t.orden)
            const elegida = t.alternativas.find((a) => a.plato_id === linea.elecciones[t.orden])
            return (
              <div key={t.orden} className={`menu-tiempo-fila ${quitado ? 'tiempo-quitado' : ''}`}>
                <div className="menu-tiempo-info">
                  <span className="tiempo-rotulo">{t.rotulo}</span>
                  <span className="tiempo-eleccion">
                    {quitado
                      ? `Sin ${t.rotulo.toLowerCase()}${t.descuento_si_se_quita > 0 ? ` (−${soles(t.descuento_si_se_quita)})` : ''}`
                      : elegida
                        ? `${elegida.nombre}${elegida.recargo > 0 ? ` (+${soles(elegida.recargo)})` : ''}`
                        : '—'}
                  </span>
                </div>
                <div className="menu-tiempo-acciones">
                  {!quitado && t.alternativas.length > 1 && (
                    <button
                      className="boton-servicio boton-empaque"
                      onClick={() => setCambiando((c) => (c === t.orden ? null : t.orden))}
                    >
                      Cambiar
                    </button>
                  )}
                  <button
                    className={`boton-servicio boton-empaque ${quitado ? 'servicio-activo' : ''}`}
                    onClick={() => { setCambiando(null); onAlternarOmitido(t.orden) }}
                  >
                    {quitado ? 'Devolver' : `Sin ${t.rotulo.toLowerCase()}`}
                  </button>
                </div>
                {cambiando === t.orden && !quitado && (
                  <div className="opciones-tiempo opciones-en-tarjeta">
                    {t.alternativas.map((a) => (
                      <button
                        key={a.plato_id}
                        className={`opcion-tiempo ${linea.elecciones[t.orden] === a.plato_id ? 'opcion-activa' : ''}`}
                        onClick={() => { onCambiarEleccion(t.orden, a.plato_id); setCambiando(null) }}
                      >
                        {linea.elecciones[t.orden] === a.plato_id ? '● ' : '○ '}
                        {a.nombre}
                        {a.recargo > 0 && <small> +{soles(a.recargo)}</small>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )
          })}

          {linea.menu.agregados.length > 0 && (
            <div className="menu-agregados">
              <span className="extras-titulo">Agregar al menú:</span>
              <div className="chips-agregados">
                {linea.menu.agregados.map((a) => {
                  const cantidad = linea.agregados.find((x) => x.agregado.id === a.id)?.cantidad ?? 0
                  return (
                    <span key={a.id} className={`chip-agregado ${cantidad > 0 ? 'chip-activo' : ''}`}>
                      <button
                        className="boton-mini"
                        onClick={() => onCambiarAgregado(a, -1)}
                        disabled={cantidad === 0}
                        aria-label={`Quitar ${a.nombre}`}
                      >−</button>
                      <span className="chip-agregado-texto">
                        {cantidad > 0 && <strong>{cantidad} </strong>}
                        {a.nombre} <small>{soles(a.precio)}</small>
                      </span>
                      <button
                        className="boton-mini"
                        onClick={() => onCambiarAgregado(a, 1)}
                        aria-label={`Agregar ${a.nombre}`}
                      >+</button>
                    </span>
                  )
                })}
              </div>
            </div>
          )}

          <div className="empaques-linea">
            <button className="boton-servicio boton-empaque" onClick={() => onCambiarCantidad(-1)}>
              − Quitar {linea.cantidad === 1 ? 'este menú' : 'uno'}
            </button>
            <button className="boton-servicio boton-empaque" onClick={onDuplicar}>
              + Otro igual
            </button>
            {EMPAQUES.map((e) => (
              <button
                key={e}
                className={`boton-servicio boton-empaque ${linea.empaque === e ? 'servicio-activo' : ''}`}
                onClick={() => onCambiarEmpaque(e)}
              >
                {NOMBRE_EMPAQUE[e]}
              </button>
            ))}
          </div>
          <input
            className="input-nota-plato"
            placeholder="📝 Algún cambio: sin ají, poco arroz…"
            maxLength={150}
            value={linea.nota}
            onChange={(e) => onCambiarNota(e.target.value)}
          />

          <div className="tarjeta-menu-cuenta">
            {(quitados.length > 0 || linea.agregados.length > 0) && (
              <span className="tarjeta-menu-cambios">
                {quitados.length > 0 && `Quitaste: ${quitados.map((t) => t.rotulo.toLowerCase()).join(', ')}${descuento > 0 ? ` (−${soles(descuento * linea.cantidad)})` : ''}`}
                {quitados.length > 0 && linea.agregados.length > 0 && ' · '}
                {linea.agregados.length > 0 &&
                  `Agregaste: ${linea.agregados.map((a) => `${a.cantidad} ${a.agregado.nombre.toLowerCase()} (${soles(a.agregado.precio * a.cantidad)})`).join(', ')}`}
              </span>
            )}
            <span className="tarjeta-menu-total">
              {linea.cantidad > 1 && `${linea.cantidad} × ${soles(precioUnitarioMenu(linea))} · `}
              Total <strong>{soles(subtotalMenu(linea))}</strong>
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
