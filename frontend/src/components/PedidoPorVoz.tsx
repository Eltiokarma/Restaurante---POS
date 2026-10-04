import { useCallback, useEffect, useRef, useState } from 'react'
import { api, NOMBRE_EMPAQUE, personaVozAMenu, soles, subtotalMenu } from '../api'
import type { Bebida, MenuCarrito, MenuHoy, Plato, VozItemResuelto, VozResultado } from '../api'

// Lo normal es tocar "Ya pedí" al terminar (envía al toque, sin esperar
// silencio); el corte por silencio es solo respaldo y largo, para que una
// pausa pensando ("para la mesa 3… eh…") no corte el pedido
const SILENCIO_MS = 8000
const MAX_GRABACION_MS = 40_000
const UMBRAL_VOZ = 0.02 // RMS mínimo para considerar que está hablando

export interface ExtrasVoz {
  gaseosas: { bebida: Bebida; cantidad: number }[]
  mesa: { id: number; nombre: string } | null
}

interface Props {
  platos: Plato[]
  // La lista de gaseosas de la terminal (para mapear lo dictado)
  gaseosasLista: Bebida[]
  // Los menús de hoy: cada persona dictada entra como su ticket
  menus: MenuHoy[]
  // "✅ Así es, continuar": suma al carrito y sigue al resumen estándar
  onContinuar: (items: VozItemResuelto[], menus: MenuCarrito[], extras: ExtrasVoz) => void
  // "Usar los botones mejor": suma lo resuelto y vuelve al menú táctil
  onUsarBotones: (items: VozItemResuelto[], menus: MenuCarrito[], extras: ExtrasVoz) => void
  // Pedido entendido sin dudas: se salta "¿Eso pediste?" y va directo a la
  // ventana de cancelación. Sin esta prop, siempre se verifica.
  onDirecto?: (items: VozItemResuelto[], menus: MenuCarrito[], extras: ExtrasVoz) => void
  onCerrar: () => void
}

type Fase = 'grabando' | 'procesando' | 'verificar' | 'error'

/**
 * Flujo de voz. Con dudas, llena esta pantalla de verificación y los dedos
 * deciden. Sin dudas (pedido simple por reglas, o la IA no adivinó nada) va
 * directo a la ventana de cancelación: lo urgente es que cocina se entere,
 * y lo que salga mal se corrige después ("✏️ Modificar un pedido"). Todo lo
 * posterior (ventana, ticket, cocina) es el flujo táctil de siempre.
 */
export function PedidoPorVoz({ platos, gaseosasLista, menus, onContinuar, onUsarBotones, onDirecto, onCerrar }: Props) {
  const [fase, setFase] = useState<Fase>('grabando')
  const [nivel, setNivel] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')
  const [transcripcion, setTranscripcion] = useState('')
  const [items, setItems] = useState<VozItemResuelto[]>([])
  const [personas, setPersonas] = useState<MenuCarrito[]>([])
  const [gaseosas, setGaseosas] = useState<ExtrasVoz['gaseosas']>([])
  const [mesa, setMesa] = useState<ExtrasVoz['mesa']>(null)
  const [noEncontrados, setNoEncontrados] = useState<string[]>([])
  const [logId, setLogId] = useState<number | null>(null)
  const [editado, setEditado] = useState(false)

  const mediaRef = useRef<{ recorder: MediaRecorder; stream: MediaStream; audioCtx: AudioContext } | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const inicioRef = useRef(0)
  const resultadoEnviado = useRef(false)
  // Menús y gaseosas por ref: la terminal los refresca cada 30 s y, como
  // dependencias, reiniciaban la grabación a mitad de pedido (se "mandaba
  // sola" cortada y la nueva pedía "habla más fuerte")
  const menusRef = useRef(menus)
  const gaseosasRef = useRef(gaseosasLista)
  const onDirectoRef = useRef(onDirecto)
  menusRef.current = menus
  gaseosasRef.current = gaseosasLista
  onDirectoRef.current = onDirecto

  const detener = useCallback(() => {
    const media = mediaRef.current
    if (media && media.recorder.state === 'recording') media.recorder.stop()
  }, [])

  const limpiarMedia = useCallback(() => {
    const media = mediaRef.current
    if (!media) return
    media.stream.getTracks().forEach((t) => t.stop())
    media.audioCtx.close().catch(() => {})
    mediaRef.current = null
  }, [])

  const marcarResultado = useCallback(
    (resultado: VozResultado) => {
      if (logId !== null && !resultadoEnviado.current) {
        resultadoEnviado.current = true
        api.vozResultado(logId, resultado)
      }
    },
    [logId],
  )

  const procesar = useCallback(async (blob: Blob, duracionSeg: number) => {
    setFase('procesando')
    try {
      const r = await api.vozOrden(blob, duracionSeg)
      setTranscripcion(r.transcripcion)
      setItems(r.items_resueltos)
      // Un menú que se agotó entre el audio y la respuesta no entra
      const armadas: MenuCarrito[] = []
      const perdidas: string[] = []
      for (const p of r.personas ?? []) {
        const menu = menusRef.current.find((m) => m.id === p.menu_id)
        if (menu) armadas.push(personaVozAMenu(p, menu))
        else perdidas.push(p.menu_nombre)
      }
      setPersonas(armadas)
      const dictadas: ExtrasVoz['gaseosas'] = []
      for (const g of r.gaseosas ?? []) {
        const bebida = gaseosasRef.current.find((b) => b.id === g.bebida_id)
        if (bebida) dictadas.push({ bebida, cantidad: g.cantidad })
        else perdidas.push(g.nombre)
      }
      const directo = onDirectoRef.current
      const todoEntendido = r.no_encontrados.length === 0 && perdidas.length === 0
      if (r.seguro && directo && todoEntendido && (armadas.length > 0 || r.items_resueltos.length > 0)) {
        resultadoEnviado.current = true
        api.vozResultado(r.log_id, 'aceptado').catch(() => {})
        directo(r.items_resueltos, armadas, { gaseosas: dictadas, mesa: r.mesa ?? null })
        return
      }
      setGaseosas(dictadas)
      setMesa(r.mesa ?? null)
      setNoEncontrados([...r.no_encontrados, ...perdidas])
      setLogId(r.log_id)
      resultadoEnviado.current = false
      setEditado(false)
      setFase('verificar')
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'No te escuché bien, intenta de nuevo o usa los botones')
      setFase('error')
    }
  }, [])

  const empezarGrabacion = useCallback(async () => {
    setFase('grabando')
    setNivel(0)
    chunksRef.current = []
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      const audioCtx = new AudioContext()
      audioCtx.resume().catch(() => {}) // algunos navegadores lo crean suspendido
      const analizador = audioCtx.createAnalyser()
      analizador.fftSize = 512
      audioCtx.createMediaStreamSource(stream).connect(analizador)
      mediaRef.current = { recorder, stream, audioCtx }

      recorder.ondataavailable = (e) => chunksRef.current.push(e.data)
      recorder.onstop = () => {
        const duracion = (Date.now() - inicioRef.current) / 1000
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        limpiarMedia()
        if (duracion < 0.8) {
          setErrorMsg('Casi no te escuché. Habla fuerte y claro, o usa los botones.')
          setFase('error')
          return
        }
        procesar(blob, duracion)
      }

      inicioRef.current = Date.now()
      recorder.start()

      // Medidor de nivel + detección de silencio de 2.5s + tope de 20s
      const datos = new Uint8Array(analizador.frequencyBinCount)
      let ultimaVoz = Date.now()
      const intervalo = window.setInterval(() => {
        if (!mediaRef.current || recorder.state !== 'recording') {
          window.clearInterval(intervalo)
          return
        }
        analizador.getByteTimeDomainData(datos)
        let suma = 0
        for (const d of datos) {
          const x = (d - 128) / 128
          suma += x * x
        }
        const rms = Math.sqrt(suma / datos.length)
        setNivel(Math.min(1, rms * 6))
        const ahora = Date.now()
        if (rms > UMBRAL_VOZ) ultimaVoz = ahora
        const hablo = ultimaVoz - inicioRef.current > 300
        if ((hablo && ahora - ultimaVoz > SILENCIO_MS) || ahora - inicioRef.current > MAX_GRABACION_MS) {
          window.clearInterval(intervalo)
          recorder.stop()
        }
      }, 150)
    } catch {
      setErrorMsg('No pude usar el micrófono. Usa los botones, por favor.')
      setFase('error')
    }
  }, [limpiarMedia, procesar])

  // Graba UNA vez al abrir; "Repetir" e "Intentar de nuevo" son explícitos
  useEffect(() => {
    empezarGrabacion()
    return limpiarMedia
  }, [])

  // ---- Correcciones táctiles sobre lo interpretado ----
  const cambiar = (platoId: number, delta: number) => {
    setEditado(true)
    setItems((prev) =>
      prev
        .map((i) => (i.plato_id === platoId ? { ...i, cantidad: i.cantidad + delta } : i))
        .filter((i) => i.cantidad > 0),
    )
  }

  const quitar = (platoId: number) => {
    setEditado(true)
    setItems((prev) => prev.filter((i) => i.plato_id !== platoId))
  }

  const agregarPlato = (plato: Plato, reemplaza: string) => {
    setEditado(true)
    setItems((prev) => {
      const existente = prev.find((i) => i.plato_id === plato.id)
      if (existente) {
        return prev.map((i) => (i.plato_id === plato.id ? { ...i, cantidad: i.cantidad + 1 } : i))
      }
      return [...prev, { plato_id: plato.id, nombre: plato.nombre, precio: plato.precio, cantidad: 1 }]
    })
    setNoEncontrados((prev) => prev.filter((n) => n !== reemplaza))
  }

  const cambiarPersona = (indice: number, delta: number) => {
    setEditado(true)
    setPersonas((prev) =>
      prev
        .map((p, i) => (i === indice ? { ...p, cantidad: p.cantidad + delta } : p))
        .filter((p) => p.cantidad > 0),
    )
  }

  const quitarPersona = (indice: number) => {
    setEditado(true)
    setPersonas((prev) => prev.filter((_, i) => i !== indice))
  }

  const cambiarGaseosa = (bebidaId: number, delta: number) => {
    setEditado(true)
    setGaseosas((prev) =>
      prev
        .map((g) => (g.bebida.id === bebidaId ? { ...g, cantidad: g.cantidad + delta } : g))
        .filter((g) => g.cantidad > 0),
    )
  }

  const total = items.reduce((s, i) => s + i.precio * i.cantidad, 0)
    + personas.reduce((s, p) => s + subtotalMenu(p), 0)
    + gaseosas.reduce((s, g) => s + g.bebida.precio * g.cantidad, 0)
  const hayAlgo = items.length > 0 || personas.length > 0 || gaseosas.length > 0

  const continuar = () => {
    marcarResultado(editado ? 'corregido' : 'aceptado')
    onContinuar(items, personas, { gaseosas, mesa })
  }

  const usarBotones = () => {
    marcarResultado(hayAlgo ? (editado ? 'corregido' : 'aceptado') : 'descartado')
    onUsarBotones(items, personas, { gaseosas, mesa })
  }

  const repetir = () => {
    marcarResultado('descartado')
    setLogId(null)
    empezarGrabacion()
  }

  const cerrar = () => {
    marcarResultado('descartado')
    detener()
    limpiarMedia()
    onCerrar()
  }

  return (
    <div className="modal-fondo voz-fondo">
      <div className="modal voz-modal">
        <button className="voz-cerrar" onClick={cerrar} aria-label="Cerrar">✕</button>

        {fase === 'grabando' && (
          <>
            <h2>🎤 Te escucho… di tu pedido</h2>
            <p className="texto-countdown">
              Cuando termines, toca <strong>YA PEDÍ</strong>. Por ejemplo:{' '}
              {menus.length > 0
                ? '“un menú con caldo y lomo, y otro sin sopa con pollo para llevar”.'
                : '“dos lomos saltados y una chicha”.'}
            </p>
            <div className="voz-medidor">
              <div className="voz-medidor-nivel" style={{ width: `${Math.round(nivel * 100)}%` }} />
            </div>
            <button className="boton-grande boton-confirmar voz-ya-pedi" onClick={detener}>
              ✔ YA PEDÍ
            </button>
          </>
        )}

        {fase === 'procesando' && (
          <>
            <h2>Entendiendo tu pedido…</h2>
            <div className="voz-spinner" aria-hidden="true" />
          </>
        )}

        {fase === 'verificar' && (
          <>
            <h2>¿Eso pediste?</h2>
            <p className="voz-transcripcion">“{transcripcion}”</p>

            {!hayAlgo && noEncontrados.length === 0 && (
              <p className="texto-countdown">No entendí ningún plato. Intenta de nuevo o usa los botones.</p>
            )}

            <div className="voz-items">
              {personas.map((p, n) => {
                const elegidos = p.menu.tiempos
                  .filter((t) => p.elecciones[t.orden] !== undefined && t.alternativas.length > 1)
                  .map((t) => {
                    const nombre = t.alternativas.find((a) => a.plato_id === p.elecciones[t.orden])?.nombre
                    const propio = p.empaques[t.orden]
                    const despues = p.espera?.includes(t.orden) ? ' (después)' : ''
                    return (propio ? `${nombre} (${NOMBRE_EMPAQUE[propio]})` : nombre) + despues
                  })
                const faltan = p.menu.tiempos
                  .filter((t) => p.elecciones[t.orden] === undefined && !p.omitidos.includes(t.orden))
                  .map((t) => t.rotulo)
                const sin = p.menu.tiempos.filter((t) => p.omitidos.includes(t.orden)).map((t) => t.rotulo)
                return (
                  <div className="voz-item voz-persona" key={n}>
                    <div className="voz-item-info">
                      <span className="voz-item-nombre">
                        {p.nombre_persona ? `${p.nombre_persona} · ` : ''}{elegidos.join(' + ') || p.menu.nombre}
                      </span>
                      {/* Para llevar a la vista: en gris chiquito se perdía */}
                      {p.empaque !== 'mesa' && (
                        <span className="voz-persona-empaque">{NOMBRE_EMPAQUE[p.empaque]}</span>
                      )}
                      <span className="voz-item-precio">
                        {[
                          p.menu.nombre,
                          ...sin.map((r) => `sin ${r.toLowerCase()}`),
                          ...p.agregados.map((a) => `+${a.cantidad > 1 ? `${a.cantidad} ` : ''}${a.agregado.nombre}`),
                          p.nota,
                        ].filter(Boolean).join(' · ')}
                      </span>
                      {faltan.length > 0 && (
                        <span className="voz-persona-falta">Falta elegir: {faltan.join(', ')}</span>
                      )}
                    </div>
                    <div className="tarjeta-plato-controles">
                      <button className="boton-cantidad" onClick={() => cambiarPersona(n, -1)}>−</button>
                      <span className="tarjeta-plato-cantidad">{p.cantidad}</span>
                      <button className="boton-cantidad boton-mas" onClick={() => cambiarPersona(n, 1)}>+</button>
                      <button className="boton-cantidad voz-quitar" onClick={() => quitarPersona(n)}>✕</button>
                    </div>
                  </div>
                )
              })}
              {gaseosas.map((g) => (
                <div className="voz-item" key={`gaseosa-${g.bebida.id}`}>
                  <div className="voz-item-info">
                    <span className="voz-item-nombre">🥤 {g.bebida.nombre}</span>
                    <span className="voz-item-precio">{soles(g.bebida.precio)} c/u</span>
                  </div>
                  <div className="tarjeta-plato-controles">
                    <button className="boton-cantidad" onClick={() => cambiarGaseosa(g.bebida.id, -1)}>−</button>
                    <span className="tarjeta-plato-cantidad">{g.cantidad}</span>
                    <button className="boton-cantidad boton-mas" onClick={() => cambiarGaseosa(g.bebida.id, 1)}>+</button>
                    <button className="boton-cantidad voz-quitar" onClick={() => cambiarGaseosa(g.bebida.id, -g.cantidad)}>✕</button>
                  </div>
                </div>
              ))}
              {mesa && (
                <div className="voz-item">
                  <div className="voz-item-info">
                    <span className="voz-item-nombre">🪑 Mesa {mesa.nombre}</span>
                  </div>
                  <div className="tarjeta-plato-controles">
                    <button
                      className="boton-cantidad voz-quitar"
                      onClick={() => { setEditado(true); setMesa(null) }}
                      aria-label="Quitar la mesa"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              )}
              {items.map((i) => (
                <div className="voz-item" key={i.plato_id}>
                  <div className="voz-item-info">
                    <span className="voz-item-nombre">{i.nombre}</span>
                    <span className="voz-item-precio">{soles(i.precio)} c/u</span>
                  </div>
                  <div className="tarjeta-plato-controles">
                    <button className="boton-cantidad" onClick={() => cambiar(i.plato_id, -1)}>−</button>
                    <span className="tarjeta-plato-cantidad">{i.cantidad}</span>
                    <button className="boton-cantidad boton-mas" onClick={() => cambiar(i.plato_id, 1)}>+</button>
                    <button className="boton-cantidad voz-quitar" onClick={() => quitar(i.plato_id)}>✕</button>
                  </div>
                </div>
              ))}
            </div>

            {noEncontrados.map((nombre) => (
              <div className="voz-no-encontrado" key={nombre}>
                <p>No encontré <strong>“{nombre}”</strong> en el menú de hoy. ¿Quisiste decir…?</p>
                <div className="voz-sugerencias">
                  {platos.map((p) => (
                    <button key={p.id} onClick={() => agregarPlato(p, nombre)}>
                      {p.nombre}
                    </button>
                  ))}
                  <button
                    className="voz-descartar-no-encontrado"
                    onClick={() => setNoEncontrados((prev) => prev.filter((n) => n !== nombre))}
                  >
                    Nada, ignorar
                  </button>
                </div>
              </div>
            ))}

            {hayAlgo && (
              <div className="voz-total">Total por ahora: <strong>{soles(total)}</strong></div>
            )}

            <div className="voz-botones">
              <button
                className="boton-grande boton-confirmar"
                disabled={!hayAlgo}
                onClick={continuar}
              >
                ✅ Así es, continuar
              </button>
              <button className="boton-grande boton-secundario" onClick={repetir}>
                🎤 Repetir
              </button>
              <button className="boton-grande boton-secundario" onClick={usarBotones}>
                Usar los botones mejor
              </button>
            </div>
          </>
        )}

        {fase === 'error' && (
          <>
            <h2>😕 {errorMsg}</h2>
            <div className="voz-botones">
              <button className="boton-grande boton-primario" onClick={empezarGrabacion}>
                🎤 Intentar de nuevo
              </button>
              <button className="boton-grande boton-secundario" onClick={cerrar}>
                Usar los botones
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
