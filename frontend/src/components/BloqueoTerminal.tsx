import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api, ApiError, getSesion, NOMBRE_ROL, setSesion } from '../api'
import type { PersonaEquipo, Rol, SesionEquipo } from '../api'
import { TecladoPin } from './TecladoPin'

const CLAVE_BLOQUEADA = 'pos_terminal_bloqueada'

// Cuánto sin tocar la pantalla hasta pedir el PIN otra vez: la terminal de
// pedidos al minuto (pedido del dueño); la caja, que se usa sin parar, a
// los tres
const BLOQUEO_SEG = { terminal: 60, caja: 180 }
// Quién entra a cada pantalla con el equipo activo
const ROLES_PAGINA: Record<Pagina, Rol[]> = {
  terminal: ['admin', 'cajero', 'mozo'],
  caja: ['admin', 'cajero'],
}

type Pagina = keyof typeof BLOQUEO_SEG

function leerBloqueada(): boolean {
  try {
    return localStorage.getItem(CLAVE_BLOQUEADA) === '1'
  } catch {
    return false
  }
}

function guardarBloqueada(valor: boolean) {
  try {
    if (valor) localStorage.setItem(CLAVE_BLOQUEADA, '1')
    else localStorage.removeItem(CLAVE_BLOQUEADA)
  } catch {
    /* sin almacenamiento: el bloqueo vale mientras la página siga abierta */
  }
}

/**
 * Candado de las pantallas del personal. La pantalla sigue montada debajo:
 * el pedido a medio armar no se pierde.
 *
 * - Equipo activo (Admin → Equipo): "¿Quién eres?" con el nombre y el PIN
 *   de cada persona; al apagarse la pantalla o tras un rato sin tocarla se
 *   vuelve a pedir (y ahí puede entrar otra persona: cambio de turno). La
 *   caja solo deja entrar a cajeros y admins.
 * - Equipo apagado: en la terminal, el PIN del cajón (si hay uno puesto);
 *   en la caja, nada (como siempre).
 */
export function BloqueoTerminal({ pagina, children }: { pagina: Pagina; children: ReactNode }) {
  const [equipo, setEquipo] = useState(false)
  const [conPinCajon, setConPinCajon] = useState(false)
  const [sesion, setSesionEstado] = useState<SesionEquipo | null>(getSesion)
  const [bloqueada, setBloqueadaEstado] = useState(leerBloqueada)
  const ultimaActividad = useRef(Date.now())

  const setBloqueada = useCallback((valor: boolean) => {
    guardarBloqueada(valor)
    setBloqueadaEstado(valor)
  }, [])

  // Si el admin enciende el equipo o pone el PIN del cajón, la pantalla se
  // entera sola
  useEffect(() => {
    const cargar = () => api.config()
      .then((c) => { setEquipo(!!c.equipo_activo); setConPinCajon(!!c.gaveta_con_pin) })
      .catch(() => {})
    cargar()
    const intervalo = window.setInterval(cargar, 30_000)
    return () => window.clearInterval(intervalo)
  }, [])

  // La sesión vive en api.ts (localStorage): se escucha para enterarse
  // cuando entra otra persona o cuando venció (401)
  useEffect(() => {
    const alCambiar = () => setSesionEstado(getSesion())
    const alVencer = () => setSesion(null)
    window.addEventListener('sesion-equipo', alCambiar)
    window.addEventListener('sesion-equipo-vencida', alVencer)
    return () => {
      window.removeEventListener('sesion-equipo', alCambiar)
      window.removeEventListener('sesion-equipo-vencida', alVencer)
    }
  }, [])

  // Al abrir, la sesión guardada se confirma (pudieron desactivarla)
  useEffect(() => {
    if (equipo && getSesion()) {
      api.equipoYo().catch((e) => { if (e instanceof ApiError && e.status === 401) setSesion(null) })
    }
  }, [equipo])

  const candado = equipo || (pagina === 'terminal' && conPinCajon)

  useEffect(() => {
    if (!candado) return
    ultimaActividad.current = Date.now()
    const registrar = () => { ultimaActividad.current = Date.now() }
    // Pantalla apagada (o la tablet cambió de app): al volver pide el PIN
    const alOcultar = () => { if (document.visibilityState === 'hidden') setBloqueada(true) }
    const eventos: (keyof WindowEventMap)[] = ['pointerdown', 'touchstart', 'keydown']
    eventos.forEach((e) => window.addEventListener(e, registrar))
    document.addEventListener('visibilitychange', alOcultar)
    // Con la pantalla apagada los timers se congelan: al despertar, la
    // diferencia de reloj igual lo detecta
    const intervalo = window.setInterval(() => {
      if (Date.now() - ultimaActividad.current >= BLOQUEO_SEG[pagina] * 1000) setBloqueada(true)
    }, 1_000)
    return () => {
      eventos.forEach((e) => window.removeEventListener(e, registrar))
      document.removeEventListener('visibilitychange', alOcultar)
      window.clearInterval(intervalo)
    }
  }, [candado, pagina, setBloqueada])

  const desbloquear = () => {
    setBloqueada(false)
    ultimaActividad.current = Date.now()
  }

  if (!equipo) {
    return (
      <>
        {children}
        {pagina === 'terminal' && conPinCajon && bloqueada && <CandadoCajon onAbrir={desbloquear} />}
      </>
    )
  }

  const permitida = sesion !== null && ROLES_PAGINA[pagina].includes(sesion.usuario.rol)
  return (
    <>
      {children}
      {permitida && !bloqueada && (
        <ChipSesion
          sesion={sesion}
          onCambiar={() => setBloqueada(true)}
        />
      )}
      {(!permitida || bloqueada) && (
        <QuienEres
          pagina={pagina}
          actual={permitida ? sesion : null}
          onEntro={desbloquear}
        />
      )}
    </>
  )
}

/** Quién está usando la tablet, en una esquina y compacto (no tapa los
 *  botones de la cabecera): al tocarlo se abre "Cambiar" y "Salir". */
function ChipSesion({ sesion, onCambiar }: { sesion: SesionEquipo; onCambiar: () => void }) {
  const [abierto, setAbierto] = useState(false)
  return (
    <div className="chip-sesion">
      <button
        type="button"
        className="chip-sesion-nombre"
        aria-expanded={abierto}
        onClick={() => setAbierto(!abierto)}
      >
        👤 {sesion.usuario.nombre}
      </button>
      {abierto && (
        <>
          <span>{NOMBRE_ROL[sesion.usuario.rol]}</span>
          <button type="button" onClick={() => { setAbierto(false); onCambiar() }}>Cambiar</button>
          <button type="button" onClick={() => setSesion(null)}>Salir</button>
        </>
      )}
    </div>
  )
}

/** "¿Quién eres?": se toca el nombre y se pone el PIN. Si la pantalla se
 *  bloqueó con alguien adentro, ya viene elegido (solo pone su PIN). */
function QuienEres({ pagina, actual, onEntro }: {
  pagina: Pagina
  actual: SesionEquipo | null
  onEntro: () => void
}) {
  const [personas, setPersonas] = useState<PersonaEquipo[]>([])
  const [elegida, setElegida] = useState<number | null>(actual?.usuario.id ?? null)
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [ocupado, setOcupado] = useState(false)

  useEffect(() => {
    api.equipoQuienes()
      .then((d) => setPersonas(d.personas.filter((p) => ROLES_PAGINA[pagina].includes(p.rol))))
      .catch(() => setError('Sin conexión, intenta de nuevo'))
  }, [pagina])

  const entrar = async () => {
    if (elegida === null || ocupado) return
    setOcupado(true)
    try {
      setSesion(await api.equipoEntrar(elegida, pin))
      setPin('')
      setError('')
      onEntro()
    } catch (e) {
      setPin('')
      setError(
        e instanceof ApiError && (e.status === 403 || e.status === 429) ? e.message : 'Sin conexión, intenta de nuevo',
      )
    } finally {
      setOcupado(false)
    }
  }

  const persona = personas.find((p) => p.id === elegida)
  return (
    <div className="bloqueo-terminal" role="dialog" aria-modal="true" aria-label="¿Quién eres?">
      <div className="bloqueo-terminal-contenido">
        {persona ? (
          <>
            <h1>🔒 {persona.nombre}</h1>
            <p>Pon tu PIN para seguir</p>
            <TecladoPin
              valor={pin}
              onCambiar={(v) => { setPin(v); setError('') }}
              onOk={entrar}
              ocupado={ocupado}
              error={error}
            />
            <button type="button" className="quien-eres-volver" onClick={() => { setElegida(null); setPin(''); setError('') }}>
              No soy {persona.nombre}
            </button>
          </>
        ) : (
          <>
            <h1>¿Quién eres?</h1>
            <p>{pagina === 'caja' ? 'La caja es para cajeros y administradores' : 'Toca tu nombre'}</p>
            {error && <p className="teclado-pin-error">{error}</p>}
            {personas.length === 0 && !error && (
              <p className="teclado-pin-error">
                Todavía no hay nadie en el equipo: el admin lo arma en Admin → Equipo.
              </p>
            )}
            <div className="quien-eres-lista">
              {personas.map((p) => (
                <button key={p.id} type="button" className="quien-eres-persona" onClick={() => setElegida(p.id)}>
                  {p.nombre}
                  <small>{NOMBRE_ROL[p.rol]}</small>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/** Sin equipo: el candado de siempre, con el PIN del cajón. */
function CandadoCajon({ onAbrir }: { onAbrir: () => void }) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [ocupado, setOcupado] = useState(false)

  const verificar = async () => {
    if (ocupado) return
    setOcupado(true)
    try {
      await api.desbloquearTerminal(pin)
      setPin('')
      setError('')
      onAbrir()
    } catch (e) {
      setPin('')
      setError(e instanceof ApiError && e.status === 403 ? 'PIN incorrecto' : 'Sin conexión, intenta de nuevo')
    } finally {
      setOcupado(false)
    }
  }

  return (
    <div className="bloqueo-terminal" role="dialog" aria-modal="true" aria-label="Terminal bloqueada">
      <div className="bloqueo-terminal-contenido">
        <h1>🔒 Terminal bloqueada</h1>
        <p>Ingresa el PIN del cajón para seguir</p>
        <TecladoPin
          valor={pin}
          onCambiar={(v) => { setPin(v); setError('') }}
          onOk={verificar}
          ocupado={ocupado}
          largo={8}
          error={error}
        />
      </div>
    </div>
  )
}
