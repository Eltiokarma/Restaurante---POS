import { useState } from 'react'
import { NOMBRE_EMPAQUE, soles } from '../api'
import type { Empaque, MenuCarrito, MenuHoy } from '../api'
import type { DefectoMenu, useCarrito } from '../hooks/useCarrito'

/**
 * Pedido por personas (boceto del dueño): cada tarjeta de menú es una
 * persona. Aquí viven la barra − N personas + con el monto, y las hojas
 * que programan TODAS las tarjetas de un toque: "A todas", 50/50,
 * repartir con deslizador o contadores, y el empaque repartido.
 */

export function BarraPersonas({ menu, personas, total, onMas, onMenos, onDefecto }: {
  menu: MenuHoy
  personas: number
  total: number
  onMas: () => void
  onMenos: () => void
  onDefecto?: () => void // solo caja
}) {
  return (
    <div className="barra-personas">
      {onDefecto && (
        <button className="barra-personas-defecto" onClick={onDefecto}>
          ⚙ Platos por defecto
        </button>
      )}
      <button
        className="barra-personas-boton" onClick={onMenos} disabled={personas === 0}
        aria-label="Una persona menos"
      >−</button>
      <span className="barra-personas-cuenta">
        <strong>{personas}</strong> {personas === 1 ? 'persona' : 'personas'}
        <small>{menu.nombre} · {soles(menu.precio)}</small>
      </span>
      <button className="barra-personas-boton" onClick={onMas} aria-label="Una persona más">+</button>
      <span className="barra-personas-monto">{soles(total)}</span>
    </div>
  )
}

export function Hoja({ titulo, onCerrar, children }: {
  titulo: string
  onCerrar: () => void
  children: React.ReactNode
}) {
  return (
    <div className="rh-fondo" onClick={onCerrar}>
      <div className="rh" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={titulo}>
        <div className="rh-cabecera">
          <h3>{titulo}</h3>
          <button className="rh-cerrar" onClick={onCerrar} aria-label="Cerrar">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

/** Stepper ± con tope: la suma no puede pasar del total de personas. */
function Stepper({ valor, puedeSumar, onCambiar, etiqueta }: {
  valor: number
  puedeSumar: boolean
  onCambiar: (v: number) => void
  etiqueta: string
}) {
  return (
    <span className="stepper-reparto">
      <button onClick={() => onCambiar(valor - 1)} disabled={valor <= 0} aria-label={`Uno menos de ${etiqueta}`}>−</button>
      <strong>{valor}</strong>
      <button onClick={() => onCambiar(valor + 1)} disabled={!puedeSumar} aria-label={`Uno más de ${etiqueta}`}>+</button>
    </span>
  )
}

/** "Para todas": la opción de un tiempo para todas las personas del menú,
 *  50/50 (partes iguales) o un reparto exacto (6 sopa / 4 entrada). */
export function HojaParaTodas({ tiempoOrden, lineas, onCerrar, onATodas, onNadie, onRepartir }: {
  tiempoOrden: number
  lineas: MenuCarrito[] // las tarjetas de ESTE menú, en orden
  onCerrar: () => void
  onATodas: (platoId: number | null) => void
  onNadie: () => void
  onRepartir: (cuotas: [number, number][]) => void
}) {
  const tiempo = lineas[0]?.menu.tiempos.find((t) => t.orden === tiempoOrden)
  const opciones = tiempo?.alternativas ?? []
  const n = lineas.length
  const [cuotas, setCuotas] = useState<number[]>(() =>
    opciones.map((a) =>
      lineas.filter((l) => !l.omitidos.includes(tiempoOrden) && l.elecciones[tiempoOrden] === a.plato_id).length,
    ),
  )
  const suma = cuotas.reduce((a, b) => a + b, 0)
  if (!tiempo) return null
  const rotulo = tiempo.rotulo.toLowerCase()

  const partesIguales = () => {
    const base = Math.floor(n / opciones.length)
    const sobra = n - base * opciones.length
    onRepartir(opciones.map((a, i) => [a.plato_id, base + (i < sobra ? 1 : 0)]))
  }

  return (
    <Hoja titulo={`${tiempo.rotulo} — para las ${n} personas`} onCerrar={onCerrar}>
      <div className="rh-filas">
        {opciones.map((a) => (
          <button key={a.plato_id} className="rh-opcion" onClick={() => onATodas(a.plato_id)}>
            <span>☐ Todas: {a.nombre}</span>
            {a.recargo > 0 && <small>+{soles(a.recargo)}</small>}
          </button>
        ))}
        <div className="rh-fila">
          <button className="rh-opcion rh-opcion-suave" onClick={() => onATodas(null)}>
            Todas sin elegir aún
          </button>
          <button className="rh-opcion rh-opcion-suave" onClick={onNadie}>
            ✕ Nadie lleva {rotulo}
          </button>
        </div>
      </div>

      {opciones.length >= 2 && (
        <div className="rh-reparto">
          <button className="rh-opcion rh-opcion-reparto" onClick={partesIguales}>
            ◐ {opciones.length === 2 ? '50/50' : 'Partes iguales'}
          </button>
          <span className="rh-subtitulo">⇆ Repartir exacto</span>
          {opciones.length === 2 ? (
            // El deslizador del boceto (4.1): de un lado una opción, del otro la otra
            <div className="reparto-deslizador">
              <span><strong>{cuotas[0]}</strong> {opciones[0].nombre}</span>
              <input
                type="range" min={0} max={n} value={n - cuotas[0]}
                onChange={(e) => {
                  const b = Number(e.target.value)
                  setCuotas([n - b, b])
                }}
                aria-label={`Repartir ${rotulo} entre ${opciones[0].nombre} y ${opciones[1].nombre}`}
              />
              <span>{opciones[1].nombre} <strong>{cuotas[1]}</strong></span>
            </div>
          ) : (
            opciones.map((a, i) => (
              <div key={a.plato_id} className="reparto-fila">
                <span>{a.nombre}</span>
                <Stepper
                  etiqueta={a.nombre}
                  valor={cuotas[i]}
                  puedeSumar={suma < n}
                  onCambiar={(v) => setCuotas((prev) => prev.map((x, j) => (j === i ? v : x)))}
                />
              </div>
            ))
          )}
          <p className="reparto-total">
            Total {n}{suma < n && ` · ${n - suma} quedan sin elegir`}
          </p>
          <button
            className="boton-grande boton-confirmar"
            onClick={() => onRepartir(opciones.map((a, i) => [a.plato_id, cuotas[i]]))}
          >
            Aplicar a las {n} personas
          </button>
        </div>
      )}
    </Hoja>
  )
}

/** Empaque de un tiempo repartido entre las personas: 2 mesa, 1 táper… */
export function HojaEmpaqueTodas({ tiempoOrden, lineas, empaques, onCerrar, onRepartir }: {
  tiempoOrden: number
  lineas: MenuCarrito[]
  empaques: Empaque[]
  onCerrar: () => void
  onRepartir: (cuotas: [Empaque, number][]) => void
}) {
  const tiempo = lineas[0]?.menu.tiempos.find((t) => t.orden === tiempoOrden)
  // Solo quienes ya tienen ese plato (la "sin elegir" no lleva empaque aún)
  const activas = lineas.filter(
    (l) => !l.omitidos.includes(tiempoOrden) && l.elecciones[tiempoOrden] !== undefined,
  )
  const total = activas.length
  const [cuotas, setCuotas] = useState<number[]>(() =>
    empaques.map((e) => activas.filter((l) => (l.empaques[tiempoOrden] ?? l.empaque) === e).length),
  )
  const suma = cuotas.reduce((a, b) => a + b, 0)
  if (!tiempo) return null

  return (
    <Hoja titulo={`¿En qué va ${tiempo.rotulo.toLowerCase()}? — ${total} personas`} onCerrar={onCerrar}>
      <div className="rh-filas">
        {empaques.map((e, i) => (
          <div key={e} className="rh-fila">
            <Stepper
              etiqueta={NOMBRE_EMPAQUE[e]}
              valor={cuotas[i]}
              puedeSumar={suma < total}
              onCambiar={(v) => setCuotas((prev) => prev.map((x, j) => (j === i ? v : x)))}
            />
            <span className="rh-fila-nombre">{NOMBRE_EMPAQUE[e]}</span>
            <button className="rh-todas" onClick={() => onRepartir([[e, total]])}>☐ Todas</button>
          </div>
        ))}
      </div>
      <p className="reparto-total">
        {suma} de {total}{suma < total && ` · faltan ${total - suma}`}
      </p>
      <button
        className="boton-grande boton-confirmar"
        disabled={suma !== total}
        onClick={() => onRepartir(empaques.map((e, i) => [e, cuotas[i]]))}
      >
        Aplicar reparto
      </button>
    </Hoja>
  )
}

/** "Platos por defecto" (caja): con qué arranca cada persona nueva. */
export function HojaDefecto({ menu, defecto, empaques, personas, onCerrar, onGuardar }: {
  menu: MenuHoy
  defecto: DefectoMenu
  empaques: Empaque[]
  personas: number
  onCerrar: () => void
  onGuardar: (d: DefectoMenu, aplicarATodas: boolean) => void
}) {
  const [borrador, setBorrador] = useState<DefectoMenu>(defecto)
  const elegir = (t: number, platoId: number | null) =>
    setBorrador((d) => {
      const elecciones = { ...d.elecciones }
      if (platoId === null) delete elecciones[t]
      else elecciones[t] = platoId
      return { ...d, elecciones, omitidos: d.omitidos.filter((o) => o !== t) }
    })
  const omitir = (t: number) =>
    setBorrador((d) => {
      const elecciones = { ...d.elecciones }
      delete elecciones[t]
      return { ...d, elecciones, omitidos: d.omitidos.includes(t) ? d.omitidos : [...d.omitidos, t] }
    })
  const empacar = (t: number, e: Empaque) =>
    setBorrador((d) => ({ ...d, empaques: { ...d.empaques, [t]: e } }))

  return (
    <Hoja titulo="Platos por defecto" onCerrar={onCerrar}>
      <p className="rh-ayuda">Cada persona nueva (+) arranca con esto. Se guarda en esta caja.</p>
      {menu.tiempos.map((t) => {
        const elegido = borrador.elecciones[t.orden]
        const quitado = borrador.omitidos.includes(t.orden)
        return (
          <div key={t.orden} className="defecto-bloque">
            <h4>{t.rotulo}</h4>
            <div className="defecto-chips">
              {t.alternativas.map((a) => (
                <button
                  key={a.plato_id}
                  className={`defecto-chip ${elegido === a.plato_id && !quitado ? 'defecto-chip-activo' : ''}`}
                  onClick={() => elegir(t.orden, a.plato_id)}
                >
                  {a.nombre}
                </button>
              ))}
              {t.alternativas.length > 1 && (
                <button
                  className={`defecto-chip ${elegido === undefined && !quitado ? 'defecto-chip-activo' : ''}`}
                  onClick={() => elegir(t.orden, null)}
                >
                  Sin elegir
                </button>
              )}
              <button
                className={`defecto-chip ${quitado ? 'defecto-chip-activo' : ''}`}
                onClick={() => omitir(t.orden)}
              >
                ✕ No lleva
              </button>
            </div>
            {!quitado && (
              <div className="defecto-chips">
                {empaques.map((e) => (
                  <button
                    key={e}
                    className={`defecto-chip ${(borrador.empaques[t.orden] ?? 'mesa') === e ? 'defecto-chip-activo' : ''}`}
                    onClick={() => empacar(t.orden, e)}
                  >
                    {NOMBRE_EMPAQUE[e]}
                  </button>
                ))}
              </div>
            )}
          </div>
        )
      })}
      <div className="rh-acciones">
        <button className="boton-grande boton-confirmar" onClick={() => onGuardar(borrador, false)}>
          Guardar
        </button>
        {personas > 0 && (
          <button className="boton-grande boton-secundario" onClick={() => onGuardar(borrador, true)}>
            Guardar y aplicar a {personas === 1 ? 'la persona actual' : `las ${personas}`}
          </button>
        )}
      </div>
    </Hoja>
  )
}

// ---------- Platos por defecto guardados en esta caja ----------

const CLAVE_DEFECTO = 'caja_platos_por_defecto_v2'

export function leerDefectos(): Record<number, DefectoMenu> {
  try {
    const datos = JSON.parse(localStorage.getItem(CLAVE_DEFECTO) ?? '{}')
    return datos && typeof datos === 'object' ? datos : {}
  } catch {
    return {}
  }
}

export function guardarDefectos(d: Record<number, DefectoMenu>) {
  try {
    localStorage.setItem(CLAVE_DEFECTO, JSON.stringify(d))
  } catch {
    /* sin almacenamiento: dura hasta recargar la página */
  }
}

// ---------- Cableado común para la caja y la terminal ----------

type Carrito = ReturnType<typeof useCarrito>

/** Maneja la hoja abierta ("para todas" o empaque) y da las props que la
 *  tarjeta necesita. Con una sola persona no aparece nada de esto. */
export function useRepartoMenus(carrito: Carrito, empaques: Empaque[]) {
  const [hoja, setHoja] = useState<{ tipo: 'opciones' | 'empaque'; menuId: number; tiempo: number } | null>(null)

  const propsTarjeta = (linea: MenuCarrito) => {
    const iguales = carrito.menus.filter((m) => m.menu.id === linea.menu.id).length
    if (iguales < 2) return {}
    return {
      onParaTodas: (t: number) => setHoja({ tipo: 'opciones', menuId: linea.menu.id, tiempo: t }),
      onEmpaqueTodas: (t: number) => setHoja({ tipo: 'empaque', menuId: linea.menu.id, tiempo: t }),
    }
  }

  const lineas = hoja ? carrito.menus.filter((m) => m.menu.id === hoja.menuId) : []
  const cerrar = () => setHoja(null)
  const hojas = hoja === null || lineas.length === 0 ? null : hoja.tipo === 'opciones' ? (
    <HojaParaTodas
      key={`o-${hoja.menuId}-${hoja.tiempo}`}
      tiempoOrden={hoja.tiempo}
      lineas={lineas}
      onCerrar={cerrar}
      onATodas={(platoId) => { carrito.eleccionATodos(hoja.menuId, hoja.tiempo, platoId); cerrar() }}
      onNadie={() => { carrito.omitirATodos(hoja.menuId, hoja.tiempo); cerrar() }}
      onRepartir={(cuotas) => { carrito.repartirEleccion(hoja.menuId, hoja.tiempo, cuotas); cerrar() }}
    />
  ) : (
    <HojaEmpaqueTodas
      key={`e-${hoja.menuId}-${hoja.tiempo}`}
      tiempoOrden={hoja.tiempo}
      lineas={lineas}
      empaques={empaques}
      onCerrar={cerrar}
      onRepartir={(cuotas) => { carrito.repartirEmpaque(hoja.menuId, hoja.tiempo, cuotas); cerrar() }}
    />
  )

  return { propsTarjeta, hojas }
}
