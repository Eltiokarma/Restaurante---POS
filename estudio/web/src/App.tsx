import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  ErrorToken,
  guardarToken,
  tokenGuardado,
  usarToken,
  type Calculo,
  type Ciudad,
  type Escenario,
  type Flujo,
  type Guardado,
  type SupuestosFlujo,
  type ValoresLocal,
} from './api'
import { Escenarios } from './Escenarios'
import { PanelComparar } from './PanelComparar'
import { PanelFlujo } from './PanelFlujo'
import { PanelPlatos } from './PanelPlatos'
import { PanelSensibilidad } from './PanelSensibilidad'
import { PanelSimulador } from './PanelSimulador'

const ESCENARIO_INICIAL: Escenario = {
  ciudad_id: 'juliaca',
  zona_id: null,
  segmento: 'popular',
  anio: 2026,
  formal: true,
  balones: 5,
  sueldo_dueno: true,
  q: 80,
  dias: 26,
  planilla: [],
  noche: null,
}

export const SUPUESTOS_INICIALES: SupuestosFlujo = {
  inversion: 30000,
  meses_arranque: 6,
  arranque_desde: 0.4,
  crecimiento_q: 0,
  inflacion: 0.025,
  alza_precio: 0.025,
  alza_rmv: 0.037,
  tasa_descuento: 0.15,
  regimen: 'mype',
}

const CLAVES_LOCAL: (keyof ValoresLocal)[] = [
  'precio',
  'insumos',
  'alquiler_mes',
  'sueldo_cocinero',
  'sueldo_ayudante',
  'sueldo_mozo',
  'gas_balon45',
  'servicios_mes',
]

function Entrada({ onEntrar }: { onEntrar: (t: string) => void }) {
  const [t, setT] = useState('')
  const [error, setError] = useState('')
  const probar = async () => {
    usarToken(t.trim())
    try {
      await api.ciudades()
      onEntrar(t.trim())
    } catch (e) {
      setError(e instanceof ErrorToken ? 'Ese token no es.' : 'No se pudo conectar con el estudio.')
    }
  }
  return (
    <main className="es-entrada">
      <h1>Estudio del menú</h1>
      <p>Pon el token del estudio (la variable ESTUDIO_TOKEN de Railway).</p>
      <input
        type="password"
        value={t}
        onChange={(e) => setT(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && probar()}
        placeholder="Token"
        autoFocus
      />
      <button type="button" className="es-principal" onClick={probar} disabled={!t.trim()}>
        Entrar
      </button>
      {error && <p className="es-error">{error}</p>}
    </main>
  )
}

type Pestana = 'simulador' | 'flujo' | 'sensibilidad' | 'platos' | 'comparar'
const PESTANAS: { id: Pestana; texto: string }[] = [
  { id: 'simulador', texto: 'Mes' },
  { id: 'flujo', texto: '10 años' },
  { id: 'sensibilidad', texto: 'Sensibilidad' },
  { id: 'platos', texto: 'Platos' },
  { id: 'comparar', texto: 'Comparar' },
]

type Tema = 'light' | 'dark'

function temaInicial(): Tema {
  try {
    const t = localStorage.getItem('estudio-tema')
    if (t === 'light' || t === 'dark') return t
  } catch {
    /* sin almacenamiento: se sigue al sistema */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export default function App() {
  const [tema, setTema] = useState<Tema>(temaInicial)
  useEffect(() => {
    document.documentElement.dataset.theme = tema
    try {
      localStorage.setItem('estudio-tema', tema)
    } catch {
      /* no pasa nada */
    }
  }, [tema])

  const [token, setToken] = useState(tokenGuardado())
  const [ciudades, setCiudades] = useState<Ciudad[]>([])
  const [esc, setEsc] = useState<Escenario>(ESCENARIO_INICIAL)
  const [base, setBase] = useState<ValoresLocal | null>(null)
  const [sup, setSup] = useState<SupuestosFlujo>(SUPUESTOS_INICIALES)
  const [calculo, setCalculo] = useState<Calculo | null>(null)
  const [flujo, setFlujo] = useState<Flujo | null>(null)
  const [pestana, setPestana] = useState<Pestana>('simulador')
  const [error, setError] = useState('')
  // Al cargar un escenario guardado no hay que pisar sus barras con las de la ciudad
  const conservarBarras = useRef(false)

  const salir = useCallback(() => {
    guardarToken('')
    usarToken('')
    setToken('')
  }, [])

  const manejar = useCallback(
    (e: unknown) => {
      if (e instanceof ErrorToken) salir()
      else setError(e instanceof Error ? e.message : 'Error')
    },
    [salir],
  )

  useEffect(() => {
    if (!token) return
    api.ciudades().then(setCiudades).catch(manejar)
  }, [token, manejar])

  // Valores de la ciudad/zona/segmento: son la "base" de las barras
  useEffect(() => {
    if (!token) return
    const { ciudad_id, zona_id, segmento } = esc
    api
      .calcular({ ...ESCENARIO_INICIAL, ciudad_id, zona_id, segmento })
      .then((r) => {
        const valores = Object.fromEntries(CLAVES_LOCAL.map((k) => [k, r.local[k]])) as unknown as ValoresLocal
        setBase(valores)
        if (conservarBarras.current) conservarBarras.current = false
        else setEsc((e) => ({ ...e, ...valores }))
      })
      .catch(manejar)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, esc.ciudad_id, esc.zona_id, esc.segmento, manejar])

  // Recalcula al mover cualquier barra (con una pequeña espera)
  useEffect(() => {
    if (!token || !base) return
    const t = setTimeout(() => {
      setError('')
      api.calcular(esc).then(setCalculo).catch(manejar)
      api.flujo(esc, sup).then(setFlujo).catch(manejar)
    }, 250)
    return () => clearTimeout(t)
  }, [token, base, esc, sup, manejar])

  const cargar = (g: Guardado) => {
    const nuevo = { ...ESCENARIO_INICIAL, ...g.datos.escenario }
    if (nuevo.ciudad_id !== esc.ciudad_id || nuevo.zona_id !== esc.zona_id || nuevo.segmento !== esc.segmento)
      conservarBarras.current = true
    setEsc(nuevo)
    setSup({ ...SUPUESTOS_INICIALES, ...g.datos.supuestos })
  }

  if (!token)
    return (
      <Entrada
        onEntrar={(t) => {
          guardarToken(t)
          setToken(t)
        }}
      />
    )

  return (
    <div className="es-app">
      <header className="es-cabecera">
        <h1>Estudio del menú</h1>
        <nav className="es-pestanas">
          {PESTANAS.map((p) => (
            <button
              key={p.id}
              type="button"
              className={pestana === p.id ? 'es-pestana es-pestana-on' : 'es-pestana'}
              onClick={() => setPestana(p.id)}
            >
              {p.texto}
            </button>
          ))}
        </nav>
        <button
          type="button"
          className="es-salir"
          aria-label={tema === 'dark' ? 'Pasar a modo día' : 'Pasar a modo noche'}
          onClick={() => setTema((t) => (t === 'dark' ? 'light' : 'dark'))}
        >
          {tema === 'dark' ? '☀️ Día' : '🌙 Noche'}
        </button>
        <button type="button" className="es-salir" onClick={salir}>
          Salir
        </button>
      </header>

      <Escenarios esc={esc} sup={sup} onCargar={cargar} onError={manejar} />
      {error && <p className="es-error">{error}</p>}

      {pestana === 'simulador' && (
        <PanelSimulador ciudades={ciudades} esc={esc} setEsc={setEsc} base={base} calculo={calculo} />
      )}
      {pestana === 'flujo' && <PanelFlujo esc={esc} setEsc={setEsc} sup={sup} setSup={setSup} flujo={flujo} />}
      {pestana === 'sensibilidad' && <PanelSensibilidad esc={esc} onError={manejar} />}
      {pestana === 'comparar' && (
        <PanelComparar
          onAbrir={(g) => {
            cargar(g)
            setPestana('simulador')
          }}
          onError={manejar}
        />
      )}
      {pestana === 'platos' && (
        <PanelPlatos
          esc={esc}
          onUsarCosto={(insumos) => {
            setEsc((e) => ({ ...e, insumos }))
            setPestana('simulador')
          }}
          onError={manejar}
        />
      )}
    </div>
  )
}
