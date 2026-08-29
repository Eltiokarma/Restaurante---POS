import { useCallback, useEffect, useRef, useState } from 'react'
import { api, soles } from '../api'
import type { Plato, VozItemResuelto, VozResultado } from '../api'

const SILENCIO_MS = 2500
const MAX_GRABACION_MS = 20_000
const UMBRAL_VOZ = 0.02 // RMS mínimo para considerar que está hablando

interface Props {
  platos: Plato[]
  // "✅ Así es, continuar": suma al carrito y sigue al resumen estándar
  onContinuar: (items: VozItemResuelto[]) => void
  // "Usar los botones mejor": suma lo resuelto y vuelve al menú táctil
  onUsarBotones: (items: VozItemResuelto[]) => void
  onCerrar: () => void
}

type Fase = 'grabando' | 'procesando' | 'verificar' | 'error'

/**
 * Flujo de voz. Regla de oro: la voz NUNCA confirma sola — llena esta
 * pantalla de verificación y los dedos deciden. Todo lo posterior
 * (resumen, ventana de 30s, ticket, cocina) es el flujo táctil de siempre.
 */
export function PedidoPorVoz({ platos, onContinuar, onUsarBotones, onCerrar }: Props) {
  const [fase, setFase] = useState<Fase>('grabando')
  const [nivel, setNivel] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')
  const [transcripcion, setTranscripcion] = useState('')
  const [items, setItems] = useState<VozItemResuelto[]>([])
  const [noEncontrados, setNoEncontrados] = useState<string[]>([])
  const [logId, setLogId] = useState<number | null>(null)
  const [editado, setEditado] = useState(false)

  const mediaRef = useRef<{ recorder: MediaRecorder; stream: MediaStream; audioCtx: AudioContext } | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const inicioRef = useRef(0)
  const resultadoEnviado = useRef(false)

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
      setNoEncontrados(r.no_encontrados)
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

  useEffect(() => {
    empezarGrabacion()
    return limpiarMedia
  }, [empezarGrabacion, limpiarMedia])

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

  const total = items.reduce((s, i) => s + i.precio * i.cantidad, 0)

  const continuar = () => {
    marcarResultado(editado ? 'corregido' : 'aceptado')
    onContinuar(items)
  }

  const usarBotones = () => {
    marcarResultado(items.length > 0 ? (editado ? 'corregido' : 'aceptado') : 'descartado')
    onUsarBotones(items)
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
            <h2>🎤 Habla fuerte y claro</h2>
            <p className="texto-countdown">Di tu pedido, por ejemplo: “dos lomos saltados y una chicha”.</p>
            <div className="voz-medidor">
              <div className="voz-medidor-nivel" style={{ width: `${Math.round(nivel * 100)}%` }} />
            </div>
            <button className="boton-grande boton-confirmar" onClick={detener}>
              ✔ Ya pedí
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

            {items.length === 0 && noEncontrados.length === 0 && (
              <p className="texto-countdown">No entendí ningún plato. Intenta de nuevo o usa los botones.</p>
            )}

            <div className="voz-items">
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

            {items.length > 0 && (
              <div className="voz-total">Total por ahora: <strong>{soles(total)}</strong></div>
            )}

            <div className="voz-botones">
              <button
                className="boton-grande boton-confirmar"
                disabled={items.length === 0}
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
