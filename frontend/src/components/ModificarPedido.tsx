import { useCallback, useEffect, useState } from 'react'
import { api, NOMBRE_EMPAQUE, soles } from '../api'
import type {
  Bebida, DatosLocal, Empaque, MenuHoy, OrdenMenuOut, OrdenOut, RespuestaCambio, TicketBebidaOut,
} from '../api'
import { GaseosasTerminal } from './GaseosasTerminal'
import { TicketBebidaImpreso } from './Ticket'
import { AnularPedido } from './AnularPedido'

interface Props {
  menusHoy: MenuHoy[]
  gaseosas: Bebida[]
  empaques: Empaque[]
  local: DatosLocal
  onCerrar: () => void
}

/**
 * Cambios a un pedido YA confirmado (pedido del dueño): el cliente se
 * arrepiente — ahora sí quiere la sopa, su segundo para llevar, otra
 * persona se suma, una gaseosa más o algo que ya no quiere. Cada cambio
 * va al toque al backend, que recalcula el total y le manda a cocina un
 * ticket "CAMBIO" con solo lo que cambió.
 */
export function ModificarPedido({ menusHoy, gaseosas, empaques, local, onCerrar }: Props) {
  const [ordenes, setOrdenes] = useState<OrdenOut[]>([])
  const [orden, setOrden] = useState<OrdenOut | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [agregandoPersona, setAgregandoPersona] = useState(false)
  const [nuevaPersona, setNuevaPersona] = useState<Record<number, number>>({})
  const [agregandoGaseosas, setAgregandoGaseosas] = useState(false)
  const [gaseosasNuevas, setGaseosasNuevas] = useState<{ bebida: Bebida; cantidad: number }[]>([])
  const [ticketCambio, setTicketCambio] = useState<TicketBebidaOut | null>(null)
  const [anulando, setAnulando] = useState(false)
  const [yaAnulada, setYaAnulada] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const data = await api.ordenesHoy()
      setOrdenes(
        data.ordenes
          .filter((o) => o.estado !== 'anulada' && o.origen !== 'manual')
          .sort((a, b) => b.numero_orden_dia - a.numero_orden_dia),
      )
    } catch {
      setError('No se pudo cargar los pedidos de hoy')
    }
  }, [])

  useEffect(() => { cargar() }, [cargar])

  // En modo terminal el ticket del cambio lo imprime esta pantalla
  useEffect(() => {
    if (!ticketCambio) return
    const t = window.setTimeout(() => {
      window.print()
      setTicketCambio(null)
    }, 300)
    return () => window.clearTimeout(t)
  }, [ticketCambio])

  const aplicar = async (accion: () => Promise<RespuestaCambio | OrdenOut>, hecho: string) => {
    if (ocupado) return
    setOcupado(true)
    setError('')
    try {
      const r = await accion()
      if ('orden' in r) {
        setOrden(r.orden)
        if (r.modo_impresion === 'terminal' && r.ticket_cambio) setTicketCambio(r.ticket_cambio)
      } else {
        setOrden(r)
      }
      setAviso(`${hecho} — cocina ya tiene el aviso`)
      cargar()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo hacer el cambio')
    } finally {
      setOcupado(false)
    }
  }

  const menuDe = (om: OrdenMenuOut) => menusHoy.find((m) => m.id === om.menu_id)
  const alternativasDe = (om: OrdenMenuOut, tiempoOrden: number) =>
    menuDe(om)?.tiempos.find((t) => t.orden === tiempoOrden)?.alternativas ?? []

  if (!orden) {
    return (
      <div className="pantalla pantalla-modificar">
        <div className="mod-cabecera">
          <button className="boton-cancelar-todo" onClick={onCerrar}>← Volver</button>
          <h1>Modificar un pedido</h1>
        </div>
        {error && <div className="mensaje-error">{error}</div>}
        {ordenes.length === 0 && <p className="nota-oferta">Todavía no hay pedidos hoy.</p>}
        <div className="mod-lista">
          {ordenes.map((o) => (
            <button key={o.id} className="mod-orden" onClick={() => { setOrden(o); setAviso('') }}>
              <span className="mod-orden-numero">#{String(o.numero_orden_dia).padStart(3, '0')}</span>
              <span className="mod-orden-detalle">
                {o.hora.slice(0, 5)}
                {o.mesas.length > 0 && ` · Mesa ${o.mesas.join(' + ')}`}
                {' · '}
                {o.menus.map((m, i) => m.nombre_persona || `Persona ${i + 1}`).join(', ') || 'Carta'}
              </span>
              <span className="mod-orden-total">{soles(o.total)}</span>
            </button>
          ))}
        </div>
      </div>
    )
  }

  const sueltos = orden.items.filter((i) => i.nombre !== 'Táper')
  const menuParaAgregar = menusHoy[0]

  return (
    <div className="pantalla pantalla-modificar">
      <div className="mod-cabecera">
        <button className="boton-cancelar-todo" onClick={() => { setOrden(null); setAviso('') }}>← Pedidos</button>
        <h1>
          Pedido #{String(orden.numero_orden_dia).padStart(3, '0')}
          {orden.mesas.length > 0 && <small> · Mesa {orden.mesas.join(' + ')}</small>}
        </h1>
        <span className="mod-total">{soles(orden.total)}</span>
        {/* Se arrepintió del pedido entero (aunque ya pagó) o es duplicado */}
        <button className="mod-quitar mod-anular" disabled={ocupado} onClick={() => setAnulando(true)}>
          🗑 Anular pedido
        </button>
      </div>
      {anulando && (
        <AnularPedido
          orden={orden}
          local={local}
          onAnulado={() => { setYaAnulada(true); cargar() }}
          onCerrar={() => {
            setAnulando(false)
            // Si se anuló, ya no se modifica: de vuelta a la lista
            if (yaAnulada) { setOrden(null); setYaAnulada(false) }
          }}
        />
      )}
      {aviso && <div className="banner-ok">{aviso}</div>}
      {error && <div className="mensaje-error">{error}</div>}

      <div className="mod-personas">
        {orden.menus.map((om, n) => (
          <section className="mod-persona" key={om.id}>
            <div className="mod-persona-cabecera">
              <h2>{om.nombre_persona || `Persona ${n + 1}`}</h2>
              <button
                className="mod-quitar"
                disabled={ocupado}
                onClick={() => {
                  if (window.confirm(`¿Quitar a ${om.nombre_persona || `la persona ${n + 1}`} del pedido?`)) {
                    aplicar(() => api.quitarPersona(orden.id, om.id!), 'Persona quitada')
                  }
                }}
              >
                ✕ Quitar
              </button>
            </div>

            {om.items.filter((i) => !i.es_agregado).map((i) => (
              <div className="mod-plato" key={i.id}>
                <div className="mod-plato-nombre">
                  {i.nombre}{i.es_extra && ' (extra)'}{i.espera && ' (espera)'}
                </div>
                <div className="mod-empaques">
                  {empaques.map((e) => (
                    <button
                      key={e}
                      className={`mod-chip ${i.empaque === e ? 'mod-chip-activo' : ''}`}
                      disabled={ocupado || i.empaque === e}
                      onClick={() => aplicar(() => api.cambiarEmpaqueItem(orden.id, i.id!, e), `${i.nombre}: ${NOMBRE_EMPAQUE[e]}`)}
                    >
                      {NOMBRE_EMPAQUE[e]}
                    </button>
                  ))}
                  {i.es_extra && (
                    <button
                      className="mod-chip mod-chip-quitar"
                      disabled={ocupado}
                      onClick={() => aplicar(() => api.quitarItemDeOrden(orden.id, i.id!), `${i.nombre} quitado`)}
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>
            ))}

            {om.items.filter((i) => i.es_agregado).map((i) => (
              <div className="mod-plato" key={i.id}>
                <div className="mod-plato-nombre">+{i.cantidad > 1 ? `${i.cantidad} ` : ''}{i.nombre}</div>
                <button
                  className="mod-chip mod-chip-quitar"
                  disabled={ocupado}
                  onClick={() => aplicar(() => api.quitarItemDeOrden(orden.id, i.id!), `${i.nombre} quitado`)}
                >
                  ✕ Quitar
                </button>
              </div>
            ))}

            {om.omitidos.map((o) => o.tiempo_orden !== undefined && (
              <div className="mod-plato mod-falta" key={`sin-${o.tiempo_orden}`}>
                <div className="mod-plato-nombre">Sin {o.rotulo.toLowerCase()} — ¿ahora sí?</div>
                <div className="mod-empaques">
                  {alternativasDe(om, o.tiempo_orden).map((a) => (
                    <button
                      key={a.plato_id}
                      className="mod-chip mod-chip-agregar"
                      disabled={ocupado}
                      onClick={() => aplicar(
                        () => api.devolverTiempo(orden.id, om.id!, o.tiempo_orden!, a.plato_id),
                        `${a.nombre} agregado`,
                      )}
                    >
                      + {a.nombre}
                    </button>
                  ))}
                </div>
              </div>
            ))}

            {(om.pendientes_detalle ?? []).map((p) => (
              <div className="mod-plato mod-falta" key={`pend-${p.tiempo_orden}`}>
                <div className="mod-plato-nombre">{p.rotulo} por elegir</div>
                <div className="mod-empaques">
                  {alternativasDe(om, p.tiempo_orden).map((a) => (
                    <button
                      key={a.plato_id}
                      className="mod-chip mod-chip-agregar"
                      disabled={ocupado}
                      onClick={() => aplicar(
                        () => api.elegirPendiente(orden.id, om.id!, p.tiempo_orden, a.plato_id),
                        `${a.nombre} elegido`,
                      )}
                    >
                      {a.nombre}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </section>
        ))}
      </div>

      {sueltos.length > 0 && (
        <section className="mod-persona">
          <h2>Aparte</h2>
          {sueltos.map((i) => (
            <div className="mod-plato" key={i.id}>
              <div className="mod-plato-nombre">{i.cantidad} × {i.nombre}</div>
              <button
                className="mod-chip mod-chip-quitar"
                disabled={ocupado}
                onClick={() => aplicar(() => api.quitarItemDeOrden(orden.id, i.id!), `${i.nombre} quitado`)}
              >
                ✕ Quitar
              </button>
            </div>
          ))}
        </section>
      )}

      <div className="mod-acciones">
        {menuParaAgregar && !agregandoPersona && (
          <button className="boton-grande boton-secundario" onClick={() => { setAgregandoPersona(true); setNuevaPersona({}) }}>
            + Agregar una persona
          </button>
        )}
        {gaseosas.length > 0 && !agregandoGaseosas && (
          <button className="boton-grande boton-secundario" onClick={() => { setAgregandoGaseosas(true); setGaseosasNuevas([]) }}>
            🥤 Agregar gaseosas
          </button>
        )}
      </div>

      {agregandoPersona && menuParaAgregar && (
        <section className="mod-persona mod-nueva">
          <h2>Nueva persona — {menuParaAgregar.nombre} {soles(menuParaAgregar.precio)}</h2>
          {menuParaAgregar.tiempos.filter((t) => t.alternativas.length > 1).map((t) => (
            <div className="mod-plato" key={t.orden}>
              <div className="mod-plato-nombre">{t.rotulo}</div>
              <div className="mod-empaques">
                {t.alternativas.map((a) => (
                  <button
                    key={a.plato_id}
                    className={`mod-chip ${nuevaPersona[t.orden] === a.plato_id ? 'mod-chip-activo' : ''}`}
                    onClick={() => setNuevaPersona((prev) => ({ ...prev, [t.orden]: a.plato_id }))}
                  >
                    {a.nombre}{a.recargo > 0 && ` +${soles(a.recargo)}`}
                  </button>
                ))}
              </div>
            </div>
          ))}
          <div className="mod-acciones">
            <button
              className="boton-grande boton-confirmar"
              disabled={ocupado}
              onClick={async () => {
                await aplicar(() => api.agregarAOrden(orden.id, {
                  menus: [{
                    menu_id: menuParaAgregar.id, cantidad: 1, elecciones: nuevaPersona, extras: [],
                    omitidos: [], agregados: [], empaque: 'mesa', empaques: {},
                  }],
                }), 'Persona agregada')
                setAgregandoPersona(false)
              }}
            >
              ✅ Agregar persona
            </button>
            <button className="boton-grande boton-secundario" onClick={() => setAgregandoPersona(false)}>Cancelar</button>
          </div>
        </section>
      )}

      {agregandoGaseosas && (
        <section className="mod-nueva">
          <GaseosasTerminal
            lista={gaseosas}
            enCarrito={gaseosasNuevas}
            onCambiar={(bebida, delta) => setGaseosasNuevas((prev) => {
              const actual = prev.find((g) => g.bebida.id === bebida.id)?.cantidad ?? 0
              const nueva = actual + delta
              const resto = prev.filter((g) => g.bebida.id !== bebida.id)
              return nueva > 0 ? [...resto, { bebida, cantidad: nueva }] : resto
            })}
          />
          <div className="mod-acciones">
            <button
              className="boton-grande boton-confirmar"
              disabled={ocupado || gaseosasNuevas.length === 0}
              onClick={async () => {
                await aplicar(() => api.agregarAOrden(orden.id, {
                  bebidas: gaseosasNuevas.map((g) => ({ bebida_id: g.bebida.id, cantidad: g.cantidad })),
                }), 'Gaseosas agregadas')
                setAgregandoGaseosas(false)
              }}
            >
              ✅ Agregar gaseosas
            </button>
            <button className="boton-grande boton-secundario" onClick={() => setAgregandoGaseosas(false)}>Cancelar</button>
          </div>
        </section>
      )}

      {ticketCambio && (
        <div className="solo-impresion">
          <TicketBebidaImpreso ticket={ticketCambio} local={local} />
        </div>
      )}
    </div>
  )
}
