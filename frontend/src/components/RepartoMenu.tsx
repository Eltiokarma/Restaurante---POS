import { useState } from 'react'
import { entregaDeMenu, menuConAlMomento, NOMBRE_EMPAQUE, soles, subtotalMenu, tiemposPendientes } from '../api'
import type { Empaque, Entrega, MenuCarrito, MenuHoy } from '../api'
import { TarjetaMenuCarrito } from './TarjetaMenuCarrito'
import type { DefectoMenu, useCarrito } from '../hooks/useCarrito'

/**
 * Pedido por personas (boceto del dueño): cada tarjeta de menú es una
 * persona. Aquí viven la barra − N personas + con el monto, y las hojas
 * que programan TODAS las tarjetas de un toque: "A todas", 50/50,
 * repartir con deslizador o contadores, y el empaque repartido.
 */

export function BarraPersonas({ menu, personas, total, onMas, onMenos, onDefecto, onAplicarDefecto }: {
  menu: MenuHoy
  personas: number
  total: number
  onMas: () => void
  onMenos: () => void
  onDefecto?: () => void // abre la configuración de los platos por defecto
  // Pone los platos por defecto a todas las personas (undefined = aún no hay)
  onAplicarDefecto?: () => void
}) {
  return (
    <div className="barra-personas">
      {onDefecto && (
        <div className="barra-personas-defectos">
          <button
            className="barra-personas-defecto barra-personas-aplicar"
            onClick={onAplicarDefecto}
            disabled={!onAplicarDefecto || personas === 0}
            title={onAplicarDefecto ? 'Poner los platos por defecto a todas las personas' : 'Primero configura los platos por defecto'}
          >
            ✓ Aplicar por defecto
          </button>
          <button className="barra-personas-defecto" onClick={onDefecto}>
            ⚙ Configurar
          </button>
        </div>
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

/** Hoja de UN tiempo (dibujo 4 y 7): tocar el plato del ticket abre las
 *  opciones. Arriba, para ESTA persona; con varias personas, al lado de
 *  cada opción "☐ Todas", y abajo 50/50 y el reparto exacto (dibujo 4.1:
 *  deslizador con 2 opciones, contadores con más). */
export function HojaTiempo({ tiempoOrden, persona, lineas, onCerrar, onEsta, onSinElegir, onNoLleva, onATodas, onNadie, onRepartir }: {
  tiempoOrden: number
  persona: number // posición (0..) dentro de `lineas`
  lineas: MenuCarrito[] // las tarjetas de ESTE menú, en orden
  onCerrar: () => void
  onEsta: (platoId: number) => void
  onSinElegir: () => void
  onNoLleva: () => void
  onATodas: (platoId: number | null) => void
  onNadie: () => void
  onRepartir: (cuotas: [number, number][]) => void
}) {
  const linea = lineas[persona]
  const tiempo = linea?.menu.tiempos.find((t) => t.orden === tiempoOrden)
  const opciones = tiempo?.alternativas ?? []
  const n = lineas.length
  const [cuotas, setCuotas] = useState<number[]>(() =>
    opciones.map((a) =>
      lineas.filter((l) => !l.omitidos.includes(tiempoOrden) && l.elecciones[tiempoOrden] === a.plato_id).length,
    ),
  )
  const [repartiendo, setRepartiendo] = useState(false)
  const suma = cuotas.reduce((a, b) => a + b, 0)
  if (!tiempo || !linea) return null
  const rotulo = tiempo.rotulo.toLowerCase()
  const elegido = linea.omitidos.includes(tiempoOrden) ? undefined : linea.elecciones[tiempoOrden]

  const partesIguales = () => {
    const base = Math.floor(n / opciones.length)
    const sobra = n - base * opciones.length
    onRepartir(opciones.map((a, i) => [a.plato_id, base + (i < sobra ? 1 : 0)]))
  }

  return (
    <Hoja titulo={`${tiempo.rotulo} — Persona ${persona + 1}`} onCerrar={onCerrar}>
      <div className="rh-filas">
        {opciones.map((a) => (
          <div key={a.plato_id} className="rh-fila">
            <button
              className={`rh-opcion ${elegido === a.plato_id ? 'rh-opcion-activa' : ''}`}
              onClick={() => onEsta(a.plato_id)}
            >
              <span>{elegido === a.plato_id ? '● ' : '○ '}{a.nombre}</span>
              {a.recargo > 0 && <small>+{soles(a.recargo)}</small>}
            </button>
            {n > 1 && (
              <button className="rh-todas" onClick={() => onATodas(a.plato_id)} aria-label={`${a.nombre} para todas`}>
                ☐ Todas
              </button>
            )}
          </div>
        ))}
        <div className="rh-fila">
          {opciones.length > 1 && (
            <button className="rh-opcion rh-opcion-suave" onClick={onSinElegir}>Sin elegir aún</button>
          )}
          <button
            className={`rh-opcion rh-opcion-suave ${linea.omitidos.includes(tiempoOrden) ? 'rh-opcion-activa' : ''}`}
            onClick={onNoLleva}
          >
            ✕ No lleva {rotulo}
            {tiempo.descuento_si_se_quita > 0 && ` (−${soles(tiempo.descuento_si_se_quita)})`}
          </button>
          {n > 1 && <button className="rh-todas" onClick={onNadie}>✕ Nadie</button>}
        </div>
      </div>

      {n > 1 && opciones.length >= 2 && (
        <div className="rh-reparto">
          <div className="rh-fila">
            <button className="rh-opcion rh-opcion-reparto" onClick={partesIguales}>
              ◐ {opciones.length === 2 ? '50/50' : 'Partes iguales'}
            </button>
            <button className="rh-opcion rh-opcion-reparto" onClick={() => setRepartiendo((r) => !r)}>
              ⇆ Repartir…
            </button>
          </div>
          {repartiendo && (
            <>
              {opciones.length === 2 ? (
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
            </>
          )}
        </div>
      )}
    </Hoja>
  )
}

/** Hoja de empaque (dibujo 5): tocar la letra M/T del ticket. Tocar un
 *  empaque lo pone a ESTA persona; con varias, contadores ± que reparten
 *  entre todas (la suma no pasa de las personas que tienen ese plato). */
export function HojaEmpaque({ tiempoOrden, persona, lineas, empaques, onCerrar, onEsta, onRepartir }: {
  tiempoOrden: number
  persona: number
  lineas: MenuCarrito[]
  empaques: Empaque[]
  onCerrar: () => void
  onEsta: (e: Empaque) => void
  onRepartir: (cuotas: [Empaque, number][]) => void
}) {
  const linea = lineas[persona]
  const tiempo = linea?.menu.tiempos.find((t) => t.orden === tiempoOrden)
  // Solo quienes ya tienen ese plato (la "sin elegir" no lleva empaque aún)
  const activas = lineas.filter(
    (l) => !l.omitidos.includes(tiempoOrden) && l.elecciones[tiempoOrden] !== undefined,
  )
  const total = activas.length
  const [cuotas, setCuotas] = useState<number[]>(() =>
    empaques.map((e) => activas.filter((l) => (l.empaques[tiempoOrden] ?? l.empaque) === e).length),
  )
  const suma = cuotas.reduce((a, b) => a + b, 0)
  if (!tiempo || !linea) return null
  const actual = linea.empaques[tiempoOrden] ?? linea.empaque

  return (
    <Hoja titulo={`¿En qué va ${tiempo.rotulo.toLowerCase()}? — Persona ${persona + 1}`} onCerrar={onCerrar}>
      <div className="rh-filas">
        {empaques.map((e, i) => (
          <div key={e} className="rh-fila">
            {total > 1 && (
              <Stepper
                etiqueta={NOMBRE_EMPAQUE[e]}
                valor={cuotas[i]}
                puedeSumar={suma < total}
                onCambiar={(v) => setCuotas((prev) => prev.map((x, j) => (j === i ? v : x)))}
              />
            )}
            <button className={`rh-opcion ${actual === e ? 'rh-opcion-activa' : ''}`} onClick={() => onEsta(e)}>
              <span>{actual === e ? '● ' : '○ '}{NOMBRE_EMPAQUE[e]}</span>
            </button>
            {total > 1 && <button className="rh-todas" onClick={() => onRepartir([[e, total]])}>☐ Todas</button>}
          </div>
        ))}
      </div>
      {total > 1 && (
        <div className="rh-reparto">
          <p className="reparto-total">
            Reparto entre las {total} con {tiempo.rotulo.toLowerCase()}: {suma} de {total}
            {suma < total && ` · faltan ${total - suma}`}
          </p>
          <button
            className="boton-grande boton-confirmar"
            disabled={suma !== total}
            onClick={() => onRepartir(empaques.map((e, i) => [e, cuotas[i]]))}
          >
            Aplicar reparto
          </button>
        </div>
      )}
    </Hoja>
  )
}

const LETRA_EMPAQUE: Record<Empaque, string> = { mesa: 'M', taper: 'T', bolsa: 'B', lonchera: 'L' }

/** El ticket de UNA persona (dibujo 3): rectángulo vertical con sus
 *  platos; a la derecha de cada uno el circulito "va a esperar" (caja) y
 *  la letra del empaque. Tocar el plato abre sus opciones; tocar la letra,
 *  el empaque. Lo demás (agregados, porciones, nota) en "＋ Más". */
export function TicketPersona({ linea, numero, domId, conEspera, onTiempo, onEmpaque, onEspera, onEntrega, onMas, onQuitar, onNombre }: {
  linea: MenuCarrito
  numero: number
  domId: string
  conEspera: boolean
  onTiempo: (tiempoOrden: number) => void
  onEmpaque: (tiempoOrden: number) => void
  onEspera: (tiempoOrden: number) => void
  onEntrega: (e: Entrega) => void
  onMas: () => void
  onQuitar: () => void
  onNombre: (nombre: string) => void
}) {
  const espera = linea.espera ?? []
  const alMomento = menuConAlMomento(linea)
  const entrega = entregaDeMenu(linea)
  const pendientes = tiemposPendientes(linea).length
  const extras =
    linea.extras.reduce((s, e) => s + e.cantidad, 0) + linea.agregados.reduce((s, a) => s + a.cantidad, 0)
  return (
    <div className={`ticket-persona ${pendientes > 0 ? 'ticket-persona-falta' : ''}`} id={domId}>
      <div className="ticket-persona-cabecera">
        <strong>Persona {numero}</strong>
        <span>{soles(subtotalMenu(linea))}</span>
        <button className="ticket-persona-quitar" onClick={onQuitar} aria-label={`Quitar persona ${numero}`}>✕</button>
      </div>
      {/* Nombre opcional: sale en la comanda de cocina ("Lomo (JUAN)") */}
      <input
        className="ticket-persona-nombre"
        placeholder="Nombre (opcional)"
        maxLength={40}
        value={linea.nombre_persona ?? ''}
        onChange={(e) => onNombre(e.target.value)}
        aria-label={`Nombre de la persona ${numero} (opcional)`}
      />
      {linea.menu.tiempos.filter((t) => t.alternativas.length > 0).map((t) => {
        const quitado = linea.omitidos.includes(t.orden)
        const elegida = t.alternativas.find((a) => a.plato_id === linea.elecciones[t.orden])
        const empaque = linea.empaques[t.orden] ?? linea.empaque
        return (
          <div key={t.orden} className={`ticket-persona-linea ${quitado ? 'linea-tachada' : ''}`}>
            <button className="ticket-persona-plato" onClick={() => onTiempo(t.orden)}>
              <small>{t.rotulo}</small>
              <span className={!quitado && !elegida ? 'linea-sin-elegir' : ''}>
                {quitado ? `Sin ${t.rotulo.toLowerCase()}` : elegida ? elegida.nombre : 'toca para elegir'}
              </span>
            </button>
            {conEspera && (
              <button
                className={`boton-espera ${espera.includes(t.orden) ? 'boton-espera-activo' : ''}`}
                disabled={quitado || !elegida}
                onClick={() => onEspera(t.orden)}
                aria-pressed={espera.includes(t.orden)}
                aria-label={`${t.rotulo}: va a esperar (reservado)`}
              >
                <span />
              </button>
            )}
            <button
              className={`ticket-persona-empaque empaque-${empaque}`}
              disabled={quitado}
              onClick={() => onEmpaque(t.orden)}
              aria-label={`${t.rotulo}: ${NOMBRE_EMPAQUE[empaque]}`}
            >
              {LETRA_EMPAQUE[empaque]}
            </button>
          </div>
        )
      })}
      <div className="ticket-persona-pie">
        <button
          className={`ticket-persona-entrega ${entrega === 'separado' ? 'entrega-tiempos' : ''}`}
          disabled={alMomento}
          onClick={() => onEntrega(entrega === 'junto' ? 'separado' : 'junto')}
          title={alMomento ? 'Lleva un plato al momento: sale por tiempos' : 'Cambiar cómo sale'}
        >
          {entrega === 'junto' ? '🍽 Junto' : '⏱ Tiempos'}
        </button>
        <button className="ticket-persona-mas" onClick={onMas}>
          ＋ Más{extras > 0 ? ` (${extras})` : ''}{linea.nota.trim() ? ' 📝' : ''}
        </button>
      </div>
    </div>
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

type HojaAbierta =
  | { tipo: 'tiempo' | 'empaque'; idx: number; tiempo: number }
  | { tipo: 'mas'; idx: number }

/** La grilla de tickets por persona y sus hojas. `conEspera` (caja)
 *  muestra el circulito "va a esperar". */
export function useTicketsPersonas(carrito: Carrito, opciones: {
  empaques: Empaque[]
  precioTaper: number
  conEspera: boolean
}) {
  const [hoja, setHoja] = useState<HojaAbierta | null>(null)
  const cerrar = () => setHoja(null)

  const lineaAbierta = hoja ? carrito.menus[hoja.idx] : undefined
  // Las tarjetas del mismo menú, en orden, y la posición de la abierta
  const delMenu = lineaAbierta
    ? carrito.menus.map((m, i) => ({ m, i })).filter(({ m }) => m.menu.id === lineaAbierta.menu.id)
    : []
  const lineas = delMenu.map(({ m }) => m)
  const persona = hoja ? delMenu.findIndex(({ i }) => i === hoja.idx) : -1

  let hojas: React.ReactNode = null
  if (hoja && lineaAbierta) {
    const menuId = lineaAbierta.menu.id
    if (hoja.tipo === 'tiempo') {
      const t = hoja.tiempo
      hojas = (
        <HojaTiempo
          key={`t-${hoja.idx}-${t}`}
          tiempoOrden={t}
          persona={persona}
          lineas={lineas}
          onCerrar={cerrar}
          onEsta={(platoId) => { carrito.cambiarEleccion(hoja.idx, t, platoId); cerrar() }}
          onSinElegir={() => { carrito.quitarEleccion(hoja.idx, t); cerrar() }}
          onNoLleva={() => {
            if (!lineaAbierta.omitidos.includes(t)) carrito.alternarOmitido(hoja.idx, t)
            cerrar()
          }}
          onATodas={(platoId) => { carrito.eleccionATodos(menuId, t, platoId); cerrar() }}
          onNadie={() => { carrito.omitirATodos(menuId, t); cerrar() }}
          onRepartir={(cuotas) => { carrito.repartirEleccion(menuId, t, cuotas); cerrar() }}
        />
      )
    } else if (hoja.tipo === 'empaque') {
      const t = hoja.tiempo
      hojas = (
        <HojaEmpaque
          key={`e-${hoja.idx}-${t}`}
          tiempoOrden={t}
          persona={persona}
          lineas={lineas}
          empaques={opciones.empaques}
          onCerrar={cerrar}
          onEsta={(e) => { carrito.cambiarEmpaqueTiempo(hoja.idx, t, e); cerrar() }}
          onRepartir={(cuotas) => { carrito.repartirEmpaque(menuId, t, cuotas); cerrar() }}
        />
      )
    } else {
      // "＋ Más": la tarjeta completa de siempre (agregados, porciones, nota…)
      const idx = hoja.idx
      hojas = (
        <Hoja titulo={`Persona ${persona + 1} — más opciones`} onCerrar={cerrar}>
          <TarjetaMenuCarrito
            linea={lineaAbierta}
            numero={persona + 1}
            abrirTic={1}
            onCambiarEleccion={(t, p) => carrito.cambiarEleccion(idx, t, p)}
            onAlternarOmitido={(t) => carrito.alternarOmitido(idx, t)}
            onCambiarAgregado={(a, d) => carrito.cambiarAgregado(idx, a, d)}
            onCambiarExtra={(t, pl, d) => carrito.cambiarExtraMenu(idx, t, pl, d)}
            onCambiarCantidad={(d) => { carrito.cambiarCantidadMenu(idx, d); if (d < 0) cerrar() }}
            onDuplicar={() => { carrito.duplicarMenu(idx); cerrar() }}
            onCambiarEmpaque={(e) => carrito.cambiarEmpaqueMenu(idx, e)}
            onCambiarEmpaqueTiempo={(t, e) => carrito.cambiarEmpaqueTiempo(idx, t, e)}
            onCambiarNota={(n) => carrito.cambiarNotaMenu(idx, n)}
            empaquesOfrecidos={opciones.empaques}
            precioTaper={opciones.precioTaper}
          />
          <button className="boton-grande boton-confirmar rh-listo" onClick={cerrar}>Listo</button>
        </Hoja>
      )
    }
  }

  const grilla = (
    <div className="tickets-personas">
      {carrito.menus.map((m, idx) => {
        const numero = carrito.menus.slice(0, idx + 1).filter((x) => x.menu.id === m.menu.id).length
        return (
          <TicketPersona
            key={`persona-${idx}`}
            linea={m}
            numero={numero}
            domId={`ticket-persona-${idx}`}
            conEspera={opciones.conEspera}
            onTiempo={(t) => setHoja({ tipo: 'tiempo', idx, tiempo: t })}
            onEmpaque={(t) => setHoja({ tipo: 'empaque', idx, tiempo: t })}
            onEspera={(t) => carrito.alternarEspera(idx, t)}
            onEntrega={(e) => carrito.cambiarEntregaMenu(idx, e)}
            onMas={() => setHoja({ tipo: 'mas', idx })}
            onQuitar={() => carrito.quitarMenu(idx)}
            onNombre={(n) => carrito.cambiarNombreMenu(idx, n)}
          />
        )
      })}
    </div>
  )

  return {
    grilla,
    hojas,
    // La guía de la terminal ("IR AHÍ") abre directo el plato que falta
    abrirTiempo: (idx: number, tiempo: number) => setHoja({ tipo: 'tiempo', idx, tiempo }),
  }
}
