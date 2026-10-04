"""Intérprete rápido de voz: pedidos simples al instante, sin IA. Todo lo
que necesita criterio devuelve None (va a la IA)."""
import pytest

from app.services.voz_rapida import interpretar_rapido

CHAIRITO, CAUSA, BISTEC, LOCRO, POLLO, TRUCHA = 40, 41, 38, 37, 48, 49
INCA, INCA_LITRO, INCA_MEDIO, COCA = 1, 2, 3, 4


@pytest.fixture()
def contexto():
    """Como el menú del sábado en producción, con sus sinónimos."""
    def alt(plato_id, nombre, *sinonimos):
        return {"plato_id": plato_id, "nombre": nombre, "sinonimos": list(sinonimos), "recargo": 0}

    return {
        "platos": [],
        "menus": [{
            "id": 2, "nombre": "Menú del día", "precio": 11.0, "agregados": [],
            "tiempos": [
                {"orden": 1, "rotulo": "Entrada", "obligatorio": True, "descuento_si_se_quita": 1.0,
                 "alternativas": [
                     alt(CHAIRITO, "Chairito", "chairo", "caldo", "caldito", "sopa", "sopita"),
                     alt(CAUSA, "Causa Rellena de Atún", "causa", "causita"),
                 ]},
                {"orden": 2, "rotulo": "Segundo", "obligatorio": True, "descuento_si_se_quita": 8.0,
                 "alternativas": [
                     alt(BISTEC, "Bistec Frito con Papas Fritas", "bistec"),
                     alt(LOCRO, "Locro de Pecho con Arroz Blanco", "locro", "pecho"),
                     alt(POLLO, "Pollo a la Olla", "pollito a la olla", "pollo"),
                     alt(TRUCHA, "Trucha Frita con Papas Fritas", "trucha"),
                 ]},
            ],
        }],
        "gaseosas": [
            {"id": INCA, "nombre": "Inca Kola personal", "precio": 2.5},
            {"id": INCA_LITRO, "nombre": "Inca Kola 1 L", "precio": 5.0},
            {"id": INCA_MEDIO, "nombre": "Inca Kola 1.5 L", "precio": 7.0},
            {"id": COCA, "nombre": "Coca Cola personal", "precio": 2.5},
        ],
        "mesas": [{"id": 7, "nombre": "3 A"}, {"id": 8, "nombre": "3 B"}, {"id": 5, "nombre": "2 B"}],
    }


def personas(r):
    """Resumen legible: (cantidad, {tiempo: plato}, sin, empaque, empaques propios)."""
    return [
        (p["cantidad"], {e["tiempo_orden"]: e["plato_id"] for e in p["elecciones"]}, p["sin"],
         p["empaque"], {e["tiempo_orden"]: e["empaque"] for e in p["elecciones"] if e["empaque"] != "igual"})
        for p in r["personas"]
    ]


def test_almuerzos_completos_en_bolsa(contexto):
    r = interpretar_rapido("Dos almuerzos con chairito y pollo a la olla en bolsa.", contexto)
    assert personas(r) == [(2, {1: CHAIRITO, 2: POLLO}, [], "bolsa", {})]


def test_almuerzos_sin_platos_para_la_mesa(contexto):
    r = interpretar_rapido("Dos almuerzos para la mesa.", contexto)
    assert personas(r) == [(2, {}, [], "mesa", {})]
    assert r["mesa"] == ""  # "para la mesa" sin número = comer en el local


def test_segundo_solo_para_llevar(contexto):
    r = interpretar_rapido("Un segundo solo de locro para llevar en tupper.", contexto)
    assert personas(r) == [(1, {2: LOCRO}, [1], "taper", {})]


def test_sopa_sola_y_un_almuerzo(contexto):
    r = interpretar_rapido("Una sopa sola y un almuerzo con causa y trucha.", contexto)
    assert personas(r) == [(1, {1: CHAIRITO}, [2], "mesa", {}), (1, {1: CAUSA, 2: TRUCHA}, [], "mesa", {})]


def test_almuerzo_y_gaseosas(contexto):
    r = interpretar_rapido("Un almuerzo con causa y locro, y dos Inca Kola.", contexto)
    assert personas(r) == [(1, {1: CAUSA, 2: LOCRO}, [], "mesa", {})]
    assert r["gaseosas"] == [{"bebida_id": INCA, "cantidad": 2}]


def test_gaseosas_por_tamano(contexto):
    r = interpretar_rapido("un almuerzo con causa y bistec, una inca de litro y medio y una coca", contexto)
    assert sorted((g["bebida_id"], g["cantidad"]) for g in r["gaseosas"]) == [(INCA_MEDIO, 1), (COCA, 1)]


def test_entradas_y_segundos_se_emparejan(contexto):
    r = interpretar_rapido("Dame tres sopas en bolsa y tres locros en tupper", contexto)
    assert personas(r) == [(3, {1: CHAIRITO, 2: LOCRO}, [], "taper", {1: "bolsa"})]


def test_mesa_dicha_con_letra(contexto):
    r = interpretar_rapido("Para la mesa tres be, dos almuerzos con causa y bistec", contexto)
    assert r["mesa"] == "3 B"
    assert personas(r) == [(2, {1: CAUSA, 2: BISTEC}, [], "mesa", {})]


def test_de_entrada_y_de_segundo(contexto):
    r = interpretar_rapido("un almuerzo, de entrada causa y de segundo trucha", contexto)
    assert personas(r) == [(1, {1: CAUSA, 2: TRUCHA}, [], "mesa", {})]


@pytest.mark.parametrize("frase", [
    # Necesitan criterio: a la IA
    "Dame tres almuerzos, un segundo solo. El segundo solo para llevar. Los tres almuerzos "
    "van a ser dos sopas, una causa y de segundos ahorita te digo",
    "Tres almuerzos, dos con chairito y uno con causa, todos con bistec",
    "dos almuerzos con chairito, el segundo después",
    "un almuerzo con causa y locro sin cebolla",
    "un lomo... no, mejor un pollo",
    "dos sopas y un locro",  # ¿cómo se emparejan? criterio
    "para la mesa 9, dos almuerzos con causa y bistec",  # no existe
    "un almuerzo con ceviche y pollo",  # "ceviche" no está hoy
    "dos almuerzos con chairito y causa",  # ¿uno de cada uno?
    "un almuerzo para Juan con causa y bistec",
])
def test_lo_dudoso_va_a_la_ia(contexto, frase):
    assert interpretar_rapido(frase, contexto) is None


def test_varios_menus_va_a_la_ia(contexto):
    contexto["menus"].append({**contexto["menus"][0], "id": 3})
    assert interpretar_rapido("dos almuerzos con chairito y bistec", contexto) is None


def test_mismo_plato_nombrado_dos_veces_seguidas(contexto):
    """"Dos locros de pecho": "locros" y "pecho" son el mismo plato."""
    r = interpretar_rapido("Dame dos sopas, dos locros de pecho para la mesa.", contexto)
    assert personas(r) == [(2, {1: CHAIRITO, 2: LOCRO}, [], "mesa", {})]


def test_mesa_sin_letra_pasa_el_numero(contexto):
    """"Mesa 3" con 3A y 3B: va solo el número y el depurado elige la libre."""
    r = interpretar_rapido("un menú para la 3 con sopa", contexto)
    assert r["mesa"] == "3"
    assert personas(r) == [(1, {1: CHAIRITO}, [], "mesa", {})]  # segundo por elegir
    r = interpretar_rapido("para la mesa 3, dos almuerzos con causa y bistec", contexto)
    assert r["mesa"] == "3"


def test_para_la_numero_es_mesa(contexto):
    r = interpretar_rapido("un almuerzo con causa y locro para la 2 be", contexto)
    assert r["mesa"] == "2 B"
    assert personas(r) == [(1, {1: CAUSA, 2: LOCRO}, [], "mesa", {})]
