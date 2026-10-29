import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, clearAdminToken, NOMBRE_ROL } from '../api'
import type { AccionEquipo, PersonaEquipo, Rol } from '../api'
import { CabeceraVista } from './CabeceraVista'

const ROLES: Rol[] = ['cajero', 'mozo', 'admin']

const QUE_HACE: Record<Rol, string> = {
  mozo: 'Toma pedidos en la terminal. Puede marcar «pagó», pero la plata la levanta la caja. '
    + 'Quitar platos o anular necesita el PIN de un admin. No entra a Caja.',
  cajero: 'Todo lo de la caja: cobrar, abrir y cerrar, egresos, cajón, menú del día. Anula sin PIN '
    + 'solo en el primer minuto del pedido; borrar egresos, reabrir la caja o dar una deuda por '
    + 'perdida necesita el PIN de un admin.',
  admin: 'Todo, y su PIN autoriza lo delicado de los demás en el momento.',
}

const NOMBRE_ACCION: Record<string, string> = {
  anular: 'Anuló',
  desanular: 'Des-anuló',
  quitar: 'Quitó',
  levantar_pago: 'Levantó el pago del mozo',
  borrar_egreso: 'Borró un egreso',
  reabrir_caja: 'Reabrió la caja',
  corregir_fondo: 'Corrigió el fondo',
  incobrable: 'Dio por perdida una deuda',
  descartar_cola: 'Descartó la cola de impresión',
}

function hoyIso(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/**
 * Admin → Equipo: quién trabaja en el local, con qué perfil y su PIN; el
 * interruptor que lo enciende, y el registro de lo delicado del día.
 */
export function TabEquipo({ onSesionVencida }: { onSesionVencida: () => void }) {
  const [personas, setPersonas] = useState<PersonaEquipo[]>([])
  const [activo, setActivo] = useState(false)
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')
  const [nombre, setNombre] = useState('')
  const [rol, setRol] = useState<Rol>('cajero')
  const [pin, setPin] = useState('')
  const [cambiandoPin, setCambiandoPin] = useState<number | null>(null)
  const [pinNuevo, setPinNuevo] = useState('')
  const [fecha, setFecha] = useState(hoyIso)
  const [acciones, setAcciones] = useState<AccionEquipo[]>([])

  const fallo = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) {
      clearAdminToken()
      onSesionVencida()
      return
    }
    setMensaje('')
    setError(e instanceof Error ? e.message : 'Algo falló, intenta de nuevo')
  }, [onSesionVencida])

  const cargar = useCallback(async () => {
    try {
      const d = await api.equipoListar()
      setPersonas(d.personas)
      setActivo(d.activo)
    } catch (e) {
      fallo(e)
    }
  }, [fallo])

  useEffect(() => { cargar() }, [cargar])
  useEffect(() => {
    api.equipoAcciones(fecha).then((d) => setAcciones(d.acciones)).catch(fallo)
  }, [fecha, fallo])

  const hecho = (texto: string) => { setError(''); setMensaje(texto); cargar() }
  const adminsActivos = personas.filter((p) => p.activo && p.rol === 'admin').length

  const crear = async () => {
    try {
      await api.equipoCrear(nombre.trim(), rol, pin)
      setNombre('')
      setPin('')
      hecho(`${nombre.trim()} ya está en el equipo ✔`)
    } catch (e) {
      fallo(e)
    }
  }

  const cambiar = async (p: PersonaEquipo, cambios: Parameters<typeof api.equipoCambiar>[1], texto: string) => {
    try {
      await api.equipoCambiar(p.id, cambios)
      hecho(texto)
    } catch (e) {
      fallo(e)
    }
  }

  const encender = async (valor: boolean) => {
    if (valor && adminsActivos === 0 && !window.confirm(
      'No hay ningún admin con PIN: nadie podrá autorizar anulaciones en la tablet. ¿Encender igual?',
    )) return
    try {
      await api.guardarConfig({ equipo_activo: valor })
      hecho(valor ? 'Equipo encendido: las tablets piden «¿Quién eres?» ✔' : 'Equipo apagado: todo como antes')
    } catch (e) {
      fallo(e)
    }
  }

  return (
    <div>
      <CabeceraVista id="equipo" />
      {mensaje && <div className="banner-ok">{mensaje}</div>}
      {error && <div className="banner-error">{error}</div>}

      <div className={`eq-interruptor ${activo ? 'eq-encendido' : ''}`}>
        <div>
          <strong>{activo ? '🟢 Equipo encendido' : '⚪ Equipo apagado'}</strong>
          <p className="nota-admin">
            {activo
              ? 'La terminal y la caja piden «¿Quién eres?» y cada perfil hace solo lo suyo.'
              : 'Mientras esté apagado todo funciona como antes. Arma el equipo y enciéndelo cuando estén listos.'}
          </p>
        </div>
        <button className="boton-grande boton-primario" onClick={() => encender(!activo)}>
          {activo ? 'Apagar' : 'Encender'}
        </button>
      </div>
      {adminsActivos === 0 && (
        <p className="nota-admin nota-advertencia">
          Crea tu propia cuenta de <strong>admin</strong> con PIN: es la que autoriza en la tablet lo que
          los demás no pueden hacer solos.
        </p>
      )}

      <div className="eq-columnas">
        <section className="eq-panel">
          <h2>Personas</h2>
          {personas.length === 0 && <p className="nota-admin">Todavía no hay nadie.</p>}
          {personas.map((p) => (
            <div key={p.id} className={`eq-persona ${p.activo ? '' : 'eq-inactiva'}`}>
              <div className="eq-persona-cabeza">
                <strong>{p.nombre}</strong>
                <select
                  value={p.rol}
                  aria-label={`Perfil de ${p.nombre}`}
                  onChange={(e) => cambiar(p, { rol: e.target.value as Rol }, `${p.nombre} ahora es ${NOMBRE_ROL[e.target.value as Rol]}`)}
                >
                  {ROLES.map((r) => <option key={r} value={r}>{NOMBRE_ROL[r]}</option>)}
                </select>
              </div>
              <div className="eq-persona-acciones">
                <button onClick={() => { setCambiandoPin(cambiandoPin === p.id ? null : p.id); setPinNuevo('') }}>
                  Cambiar PIN
                </button>
                <button onClick={() => cambiar(p, { activo: !p.activo }, p.activo ? `${p.nombre} desactivado` : `${p.nombre} activo otra vez`)}>
                  {p.activo ? 'Desactivar' : 'Activar'}
                </button>
              </div>
              {cambiandoPin === p.id && (
                <div className="eq-pin-nuevo">
                  <input
                    type="password" inputMode="numeric" maxLength={6} placeholder="PIN nuevo (4 a 6)"
                    value={pinNuevo} onChange={(e) => setPinNuevo(e.target.value.replace(/\D/g, ''))}
                  />
                  <button
                    className="boton-primario"
                    disabled={pinNuevo.length < 4}
                    onClick={() => { cambiar(p, { pin: pinNuevo }, `PIN de ${p.nombre} cambiado ✔`); setCambiandoPin(null) }}
                  >
                    Guardar
                  </button>
                </div>
              )}
            </div>
          ))}
        </section>

        <section className="eq-panel">
          <h2>Agregar a alguien</h2>
          <label className="eq-campo">
            Nombre
            <input value={nombre} maxLength={60} onChange={(e) => setNombre(e.target.value)} placeholder="Rosa" />
          </label>
          <div className="eq-roles" role="radiogroup" aria-label="Perfil">
            {ROLES.map((r) => (
              <button
                key={r}
                role="radio"
                aria-checked={rol === r}
                className={`eq-rol ${rol === r ? 'eq-rol-activo' : ''}`}
                onClick={() => setRol(r)}
              >
                {NOMBRE_ROL[r]}
              </button>
            ))}
          </div>
          <p className="nota-admin">{QUE_HACE[rol]}</p>
          <label className="eq-campo">
            PIN (4 a 6 números)
            <input
              type="password" inputMode="numeric" maxLength={6}
              value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
            />
          </label>
          <button
            className="boton-grande boton-primario"
            disabled={!nombre.trim() || pin.length < 4}
            onClick={crear}
          >
            Agregar
          </button>
        </section>
      </div>

      <section className="eq-panel">
        <div className="eq-registro-cabeza">
          <h2>Lo delicado del día</h2>
          <input type="date" value={fecha} max={hoyIso()} onChange={(e) => setFecha(e.target.value)} />
        </div>
        {acciones.length === 0 ? (
          <p className="nota-admin">Nada que reportar ese día.</p>
        ) : (
          <div className="eq-registro">
            {acciones.map((a) => (
              <div key={a.id} className="eq-registro-fila">
                <span className="eq-hora">{a.hora}</span>
                <span>
                  <strong>{a.usuario || '—'}</strong> {(NOMBRE_ACCION[a.accion] ?? a.accion).toLowerCase()}
                  {a.detalle && <> · {a.detalle}</>}
                </span>
                <span className="eq-autorizo">{a.autorizo ? `autorizó ${a.autorizo}` : ''}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
