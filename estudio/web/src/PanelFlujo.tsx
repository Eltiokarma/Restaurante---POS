import type { Escenario, Flujo, Regimen, SupuestosFlujo } from './api'
import { Barra, Chips, Dato } from './Controles'
import { anios, pct, soles } from './formato'
import { GraficoFlujo } from './Graficos'

interface Props {
  esc: Escenario
  setEsc: React.Dispatch<React.SetStateAction<Escenario>>
  sup: SupuestosFlujo
  setSup: React.Dispatch<React.SetStateAction<SupuestosFlujo>>
  flujo: Flujo | null
}

const REGIMENES: { valor: Regimen; texto: string }[] = [
  { valor: 'informal', texto: 'Informal' },
  { valor: 'nuevo_rus', texto: 'Nuevo RUS' },
  { valor: 'rer', texto: 'RER' },
  { valor: 'mype', texto: 'MYPE' },
]

const p1 = (v: number) => pct(v, 1)

export function PanelFlujo({ esc, setEsc, sup, setSup, flujo }: Props) {
  const cambiar = <K extends keyof SupuestosFlujo>(k: K) => (v: SupuestosFlujo[K]) =>
    setSup((s) => ({ ...s, [k]: v }))

  return (
    <div className="es-cuerpo">
      <aside className="es-controles">
        <h2>Régimen tributario</h2>
        <Chips valor={sup.regimen} onChange={cambiar('regimen')} opciones={REGIMENES} />

        <h2>Arranque</h2>
        <Barra
          etiqueta="Inversión para montar el local"
          valor={sup.inversion}
          min={0}
          max={200000}
          paso={500}
          onChange={cambiar('inversion')}
          formato={(v) => soles(v)}
        />
        <Barra
          etiqueta="Menús al día con el local lleno"
          valor={esc.q}
          min={5}
          max={400}
          paso={1}
          onChange={(v) => setEsc((e) => ({ ...e, q: v }))}
        />
        <Barra
          etiqueta="Meses hasta llenarse"
          valor={sup.meses_arranque}
          min={0}
          max={24}
          paso={1}
          onChange={cambiar('meses_arranque')}
        />
        <Barra
          etiqueta="El primer mes vendes"
          valor={sup.arranque_desde}
          min={0.1}
          max={1}
          paso={0.05}
          onChange={cambiar('arranque_desde')}
          formato={(v) => `${Math.round(v * 100)} % de lo lleno`}
        />
        <Barra
          etiqueta="Crecimiento de la clientela al año"
          valor={sup.crecimiento_q}
          min={-0.1}
          max={0.1}
          paso={0.005}
          onChange={cambiar('crecimiento_q')}
          formato={p1}
        />

        <h2>Precios en el tiempo</h2>
        <Barra
          etiqueta="Inflación de costos al año"
          valor={sup.inflacion}
          min={0}
          max={0.1}
          paso={0.0025}
          onChange={cambiar('inflacion')}
          formato={p1}
          base={0.025}
        />
        <Barra
          etiqueta="Subida del precio del menú al año"
          valor={sup.alza_precio}
          min={0}
          max={0.1}
          paso={0.0025}
          onChange={cambiar('alza_precio')}
          formato={p1}
          base={0.025}
        />
        <Barra
          etiqueta="Subida del sueldo mínimo desde 2029"
          valor={sup.alza_rmv}
          min={0}
          max={0.1}
          paso={0.0025}
          onChange={cambiar('alza_rmv')}
          formato={p1}
          base={0.037}
        />
        <Barra
          etiqueta="Tasa de descuento"
          valor={sup.tasa_descuento}
          min={0}
          max={0.4}
          paso={0.01}
          onChange={cambiar('tasa_descuento')}
          formato={(v) => pct(v, 0)}
          base={0.15}
        />
        <p className="es-nota">
          El precio, los insumos, el alquiler y los sueldos de partida salen del simulador del mes. La tasa de
          descuento es lo que te rendiría la plata en otro negocio con un riesgo parecido.
        </p>
      </aside>

      <section className="es-resultados">
        {!flujo ? (
          <p className="es-nota">Calculando…</p>
        ) : (
          <>
            {flujo.alertas.map((a) => (
              <p key={a} className="es-alerta">
                ⚠ {a}
              </p>
            ))}
            <div className="es-datos">
              <Dato
                titulo="VAN (valor actual neto)"
                valor={soles(flujo.van)}
                nota={flujo.van >= 0 ? 'rinde más que la tasa de descuento' : 'rinde menos que la tasa de descuento'}
                tono={flujo.van >= 0 ? 'bien' : 'mal'}
              />
              <Dato
                titulo="TIR"
                valor={flujo.tir === null ? 'no hay' : pct(flujo.tir, 0)}
                nota="rentabilidad anual de la inversión"
                tono={flujo.tir !== null && flujo.tir >= sup.tasa_descuento ? 'bien' : 'mal'}
              />
              <Dato titulo="Recuperas la inversión en" valor={anios(flujo.recupero)} />
              <Dato
                titulo="Recupero descontado"
                valor={anios(flujo.recupero_descontado)}
                nota="contando lo que rendiría la plata en otro lado"
              />
            </div>

            <GraficoFlujo inversion={sup.inversion} anios={flujo.anios} />

            <div className="es-tabla-caja">
              <table className="es-tabla es-tabla-regimenes">
                <caption>Los cuatro regímenes con los mismos supuestos (toca uno para verlo)</caption>
                <thead>
                  <tr>
                    <th>Régimen</th>
                    <th>VAN</th>
                    <th>TIR</th>
                    <th>Recupero</th>
                    <th>IGV + impuestos en 10 años</th>
                    <th>Caja en 10 años</th>
                  </tr>
                </thead>
                <tbody>
                  {flujo.comparacion.map((c) => (
                    <tr
                      key={c.regimen}
                      className={c.regimen === sup.regimen ? 'es-fila-sel' : undefined}
                      onClick={() => cambiar('regimen')(c.regimen)}
                    >
                      <th>
                        {c.nombre}
                        {c.alertas.length > 0 && <span className="es-no-aplica"> · no aplica</span>}
                      </th>
                      <td>{soles(c.van)}</td>
                      <td>{c.tir === null ? '—' : pct(c.tir, 0)}</td>
                      <td>{anios(c.recupero)}</td>
                      <td>{soles(c.impuestos_10a)}</td>
                      <td>{soles(c.flujo_10a)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="es-tabla-caja">
              <table className="es-tabla es-tabla-anios">
                <caption>{flujo.nombre}, año por año</caption>
                <thead>
                  <tr>
                    <th>Año</th>
                    <th>IGV</th>
                    <th>Sueldo mínimo</th>
                    <th>Precio</th>
                    <th>Menús/día</th>
                    <th>Ventas</th>
                    <th>IGV pagado</th>
                    <th>Utilidad</th>
                    <th>Impuesto</th>
                    <th>Caja del año</th>
                    <th>Acumulado</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th>Inicio</th>
                    <td colSpan={8} className="es-izq">
                      Inversión para montar el local
                    </td>
                    <td>{soles(-sup.inversion)}</td>
                    <td>{soles(-sup.inversion)}</td>
                  </tr>
                  {flujo.anios.map((a) => (
                    <tr key={a.anio}>
                      <th>{a.anio}</th>
                      <td>{a.igv} %</td>
                      <td>{soles(a.rmv)}</td>
                      <td>{soles(a.precio, 2)}</td>
                      <td>{a.menus_dia}</td>
                      <td>{soles(a.ventas)}</td>
                      <td>{soles(a.igv_pagado)}</td>
                      <td>{soles(a.utilidad_operativa)}</td>
                      <td>{soles(a.impuesto)}</td>
                      <td className={a.flujo < 0 ? 'es-mal' : undefined}>{soles(a.flujo)}</td>
                      <td className={a.acumulado < 0 ? 'es-mal' : undefined}>{soles(a.acumulado)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <details className="es-supuestos">
              <summary>Supuestos que no son ley</summary>
              <ul>
                {Object.entries(flujo.supuestos).map(([k, v]) => (
                  <li key={k}>{v}</li>
                ))}
                <li>
                  “Utilidad” ya descuenta tu sueldo si está marcado “Con tu sueldo” en el simulador: la caja es lo que
                  queda encima de eso.
                </li>
              </ul>
            </details>
          </>
        )}
      </section>
    </div>
  )
}
