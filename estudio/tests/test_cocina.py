from motor import cocina as coc


def test_dependencias_se_respetan():
    r = coc.plan("domestico", 80, 3)
    fin = {b["id"]: b["fin"] for b in r["manana"]}
    inicio = {b["id"]: b["inicio"] for b in r["manana"]}
    c = coc.cargar()
    for t in c["tareas"]:
        for d in t.get("deps", []):
            antes = [v for k, v in fin.items() if k == d or k.startswith(d + "@")]
            assert inicio[t["id"]] >= min(antes)


def test_nadie_hace_dos_cosas_a_la_vez():
    for modo in coc.MODOS:
        r = coc.plan(modo, 100, 3)
        for tramo in ("manana", "tarde"):
            for p in range(3):
                bs = sorted((b for b in r[tramo] if b["persona"] == p), key=lambda b: b["inicio"])
                for a, b in zip(bs, bs[1:]):
                    assert b["inicio"] >= a["fin_activo"] - 1e-9


def test_domestico_pica_por_plato_y_mise_lo_deja_para_la_tarde():
    dom = coc.plan("domestico", 100, 3)
    mise = coc.plan("mise", 100, 3)
    assert any("@" in b["id"] for b in dom["manana"]) and not dom["tarde"]
    assert mise["tarde"] and all(not b["id"].startswith("cebolla") for b in mise["manana"])
    # picar una sola vez ahorra los tiempos fijos repetidos
    assert mise["trabajo"] - mise["cambios"] < dom["trabajo"]
    assert mise["listo"] < dom["listo"]


def test_estaciones_cada_uno_en_su_puesto():
    r = coc.plan("estaciones", 100, 3)
    assert sorted(x[0] for x in r["puestos"]) == ["fondos", "plancha", "verduras"]


def test_calibracion_reproduce_lo_observado():
    c = coc.cargar()
    cal = c["servicio"]["calibracion"]
    tope = coc.capacidad_cocina(cal["modo"], cal["personas"], c)["servicio"]
    assert abs(tope - cal["menus"]) < 1


def test_mas_gente_y_mas_orden_aguantan_mas():
    c = coc.cargar()
    d = {(m, n): coc.capacidad_cocina(m, n, c)["tope"] for m in coc.MODOS for n in (2, 3)}
    for m in coc.MODOS:
        assert d[(m, 3)] > d[(m, 2)]
    assert d[("mise", 3)] > d[("domestico", 3)]


def test_la_cola_crece_con_la_venta_y_se_vacia():
    s1 = coc.servicio("domestico", 60, 2)
    s2 = coc.servicio("domestico", 90, 2)
    assert s2["espera_maxima"] > s1["espera_maxima"]
    assert s2["tramos"][-1]["cola"] < 1e-6
    total = sum(t["salen"] for t in s2["tramos"])
    assert abs(total - 90) < 1e-6


def test_reparto_de_puestos_con_poca_gente():
    ritmo, grupos = coc._reparto(2, {"a": 1.0, "b": 1.0, "c": 2.0})
    assert sorted(sorted(g) for g in grupos) == [["a", "b"], ["c"]]
    assert abs(ritmo - 0.5) < 1e-9


def test_tareas_largas_van_en_tandas():
    r = coc.plan("bloques", 220, 6)
    tandas = [b for b in r["manana"] if b["id"].startswith("papa#")]
    assert len(tandas) > 1 and all(b["fin_activo"] - b["inicio"] <= coc.TANDA + 10 for b in tandas)
    assert len({b["persona"] for b in tandas}) > 1


def test_minutos_salen_de_la_receta():
    c = coc.cargar()
    papa = next(t for t in c["tareas"] if t["id"] == "papa")
    assert coc.variable(papa) == sum(x["cantidad"] * x["min_por"] for x in papa["partes"])
    lenta = coc.con_velocidad(c, 1.5)
    assert coc.variable(next(t for t in lenta["tareas"] if t["id"] == "papa")) == 1.5 * coc.variable(papa)


def test_bloques_prepara_una_sola_vez_lo_compartido():
    dom = coc.plan("domestico", 74, 3)
    blo = coc.plan("bloques", 74, 3)
    assert blo["trabajo_manana"] - blo["cambios"] < dom["trabajo_manana"]
    assert not blo["tarde"]
