"""La base (SQLite en memoria aquí; Postgres en Railway) reproduce el
dataset: los equilibrios salen iguales leyendo desde la base, cada cifra
lleva su origen, y una zona con precio de sondeo manda sobre la ciudad."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from motor import Escenario, cargar_dataset, equilibrio, local_de_ciudad
from motor.bd import Base, Parametro, Zona, bloque, local_desde_bd, motor_bd, sembrar

DATA = cargar_dataset()
ESC = Escenario(segmento="popular", anio=2026, formal=True, balones=5, sueldo_dueno=False)


def _sesion():
    engine = motor_bd("sqlite://")
    Base.metadata.create_all(engine)
    s = Session(engine)
    sembrar(s)
    return s


def test_equilibrios_desde_la_base_iguales_al_dataset():
    s = _sesion()
    nacional = bloque(s, "nacional")
    for c in DATA["ciudades"]:
        assert equilibrio(local_desde_bd(s, c["id"]), ESC, nacional) == \
            equilibrio(local_de_ciudad(c), ESC, DATA["nacional"]), c["id"]


def test_cada_cifra_tiene_origen_y_fuente():
    s = _sesion()
    params = s.scalars(select(Parametro)).all()
    assert params and all(p.origen in ("observado", "estimado", "supuesto") and p.fuente for p in params)
    juliaca = {p.clave: p for p in params if p.ciudad_id == "juliaca" and p.segmento == "popular"}
    assert juliaca["precio"].origen == "estimado"  # S/ 8: estimado, a corregir con sondeo


def test_zona_con_precio_de_sondeo_manda_y_resiembra_no_la_borra():
    s = _sesion()
    zona = Zona(ciudad_id="juliaca", nombre="Centro", tipo="centro")
    s.add(zona)
    s.flush()
    s.add(Parametro(ambito="zona", zona_id=zona.id, segmento="popular", clave="precio", valor=11,
                    rango_min=10, rango_max=13, origen="sondeo", fuente="pizarras de prueba"))
    s.commit()
    local = local_desde_bd(s, "juliaca", "popular", zona_id=zona.id)
    assert local.precio == 11 and local.precio_propio
    sembrar(s)  # recargar el dataset no toca lo de sondeo
    assert local_desde_bd(s, "juliaca", "popular", zona_id=zona.id).precio == 11
