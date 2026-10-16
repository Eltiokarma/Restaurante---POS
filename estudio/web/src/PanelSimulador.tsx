import type { Calculo, Ciudad, Escenario, ValoresLocal } from './api'
import { Barra, Chips, Dato } from './Controles'
import { soles, pct } from './formato'
import { CurvaUtilidad } from './Graficos'

interface Props {
  ciudades: Ciudad[]
  esc: Escenario
  setEsc: React.Dispatch<React.SetStateAction<Escenario>>
  base: ValoresLocal | null
  calculo: Calculo | null
}

const s0 = (v: number) => soles(v)
const s2 = (v: number) => soles(v, 2)

export function PanelSimulador({ ciudades, esc, setEsc, base, calculo }: Props) {
  const cambiar = <K extends keyof Escenario>(k: K) => (v: Escenario[K]) => setEsc((e) => ({ ...e, [k]: v }))
  const ciudad = ciudades.find((c) => c.id === esc.ciudad_id)
  const m = calculo?.mes_a_q
  const mc = calculo?.anio_montecarlo

  return (
    <div className="es-cuerpo">
      <aside className="es-controles">
        <h2>Dónde y cómo</h2>
        <select
          value={esc.ciudad_id}
          onChange={(e) => setEsc((x) => ({ ...x, ciudad_id: e.target.value, zona_id: null }))}
        >
          {ciudades.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nombre}
            </option>
          ))}
        </select>
        {ciudad && ciudad.zonas.length > 0 && (
          <select
            value={esc.zona_id ?? ''}
            onChange={(e) => cambiar('zona_id')(e.target.value === '' ? null : Number(e.target.value))}
          >
            <option value="">Toda la ciudad</option>
            {ciudad.zonas.map((z) => (
              <option key={z.id} value={z.id}>
                {z.nombre}
              </option>
            ))}
          </select>
        )}
        <Chips
          valor={esc.segmento}
          onChange={cambiar('segmento')}
          opciones={[
            { valor: 'popular', texto: 'Menú popular' },
            { valor: 'ejecutivo', texto: 'Ejecutivo' },
          ]}
        />
        <Chips
          valor={esc.anio}
          onChange={cambiar('anio')}
          opciones={[
            { valor: 2026, texto: '2026 · IGV 10.5 %' },
            { valor: 2027, texto: '2027 · 15 %' },
            { valor: 2028, texto: '2028 · 18 %' },
          ]}
        />
        <Chips
          valor={esc.formal}
          onChange={cambiar('formal')}
          opciones={[
            { valor: true, texto: 'Formal' },
            { valor: false, texto: 'Informal' },
          ]}
        />
        <Chips
          valor={esc.sueldo_dueno}
          onChange={cambiar('sueldo_dueno')}
          opciones={[
            { valor: true, texto: 'Con tu sueldo' },
            { valor: false, texto: 'Sin tu sueldo' },
          ]}
        />

        <h2>Ventas</h2>
        <Barra etiqueta="Menús al día" valor={esc.q} min={5} max={400} paso={1} onChange={cambiar('q')} />
        <Barra
          etiqueta="Precio del menú"
          valor={esc.precio ?? 0}
          min={4}
          max={30}
          paso={0.5}
          onChange={cambiar('precio')}
          formato={s2}
          base={base?.precio}
        />

        <h2>Costos</h2>
        <Barra
          etiqueta="Insumos por menú"
          valor={esc.insumos ?? 0}
          min={1}
          max={15}
          paso={0.05}
          onChange={cambiar('insumos')}
          formato={s2}
          base={base?.insumos}
        />
        <Barra
          etiqueta="Alquiler al mes"
          valor={esc.alquiler_mes ?? 0}
          min={0}
          max={8000}
          paso={50}
          onChange={cambiar('alquiler_mes')}
          formato={s0}
          base={base?.alquiler_mes}
        />
        <Barra
          etiqueta="Sueldo del cocinero"
          valor={esc.sueldo_cocinero ?? 0}
          min={0}
          max={5000}
          paso={10}
          onChange={cambiar('sueldo_cocinero')}
          formato={s0}
          base={base?.sueldo_cocinero}
        />
        <Barra
          etiqueta="Sueldo del ayudante de cocina"
          valor={esc.sueldo_ayudante ?? 0}
          min={0}
          max={4000}
          paso={10}
          onChange={cambiar('sueldo_ayudante')}
          formato={s0}
          base={base?.sueldo_ayudante}
        />
        <Barra
          etiqueta="Sueldo del mozo"
          valor={esc.sueldo_mozo ?? 0}
          min={0}
          max={4000}
          paso={10}
          onChange={cambiar('sueldo_mozo')}
          formato={s0}
          base={base?.sueldo_mozo}
        />
        <Barra etiqueta="Balones de gas al mes" valor={esc.balones} min={0} max={20} paso={1} onChange={cambiar('balones')} />
        <Barra
          etiqueta="Precio del balón de 45 kg"
          valor={esc.gas_balon45 ?? 0}
          min={30}
          max={400}
          paso={5}
          onChange={cambiar('gas_balon45')}
          formato={s0}
          base={base?.gas_balon45}
        />
        <Barra
          etiqueta="Luz, agua e internet al mes"
          valor={esc.servicios_mes ?? 0}
          min={0}
          max={3000}
          paso={10}
          onChange={cambiar('servicios_mes')}
          formato={s0}
          base={base?.servicios_mes}
        />
        <p className="es-nota">
          Las barras arrancan con los valores de la ciudad. Si mueves una, aparece “Volver a…” para regresar.
          Además se suman S/ 400 al mes de otros gastos fijos.
        </p>
      </aside>

      <section className="es-resultados">
        {!calculo || !m || !mc ? (
          <p className="es-nota">Calculando…</p>
        ) : (
          <>
            <div className="es-datos">
              <Dato
                titulo="Equilibrio"
                valor={calculo.equilibrio_menus_dia === null ? 'más de 600' : `${calculo.equilibrio_menus_dia} menús/día`}
                nota="lo mínimo para no perder"
              />
              <Dato
                titulo={`Utilidad del mes a ${esc.q} menús`}
                valor={soles(m.utilidad)}
                nota={`margen ${pct(m.margen)}`}
                tono={m.utilidad >= 0 ? 'bien' : 'mal'}
              />
              <Dato
                titulo={`Precio mínimo a ${esc.q} menús`}
                valor={soles(calculo.precio_minimo_a_q, 2)}
                nota={`cobras ${soles(esc.precio ?? 0, 2)}`}
                tono={(esc.precio ?? 0) >= calculo.precio_minimo_a_q ? 'bien' : 'mal'}
              />
              <Dato
                titulo="Probabilidad de perder en el año"
                valor={pct(mc.prob_perdida, 0)}
                nota="2,000 años simulados"
                tono={mc.prob_perdida < 0.3 ? 'bien' : 'mal'}
              />
            </div>

            <CurvaUtilidad puntos={calculo.curva} q={esc.q} equilibrio={calculo.equilibrio_menus_dia} />

            <div className="es-tabla-caja">
              <table className="es-tabla">
                <caption>El mes a {esc.q} menús al día (26 días)</caption>
                <tbody>
                  <tr>
                    <th>Ventas (con IGV)</th>
                    <td>{soles(m.ventas)}</td>
                  </tr>
                  <tr>
                    <th>Precio sin IGV</th>
                    <td>{soles(m.precio_sin_igv, 2)}</td>
                  </tr>
                  <tr>
                    <th>Costo variable por menú (insumos + 5 % merma + descartables)</th>
                    <td>{soles(m.costo_variable_menu, 2)}</td>
                  </tr>
                  <tr>
                    <th>
                      Personal ({m.cocina} en cocina, {m.mozos} {m.mozos === 1 ? 'mozo' : 'mozos'}
                      {esc.sueldo_dueno ? ', y tu sueldo' : ''})
                    </th>
                    <td>{soles(m.personal)}</td>
                  </tr>
                  <tr>
                    <th>Alquiler</th>
                    <td>{soles(m.alquiler)}</td>
                  </tr>
                  <tr>
                    <th>Gas</th>
                    <td>{soles(m.gas)}</td>
                  </tr>
                  <tr>
                    <th>Gastos fijos en total</th>
                    <td>{soles(m.fijos)}</td>
                  </tr>
                  <tr className="es-total">
                    <th>Utilidad del mes</th>
                    <td>{soles(m.utilidad)}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="es-datos es-datos-3">
              <Dato titulo="Año malo (1 de cada 10)" valor={soles(mc.p10)} tono={mc.p10 >= 0 ? 'bien' : 'mal'} />
              <Dato titulo="Año típico" valor={soles(mc.p50)} tono={mc.p50 >= 0 ? 'bien' : 'mal'} />
              <Dato titulo="Año bueno (1 de cada 10)" valor={soles(mc.p90)} tono={mc.p90 >= 0 ? 'bien' : 'mal'} />
            </div>
            <p className="es-nota">
              Simulación de un año: la clientela, el precio de los insumos y el precio se mueven al azar, y en
              ciudades con paros se pierden de 2 a 8 semanas.
            </p>
          </>
        )}
      </section>
    </div>
  )
}
