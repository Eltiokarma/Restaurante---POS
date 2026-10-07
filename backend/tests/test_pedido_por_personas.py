"""Pedido por personas (cada menú = una persona): entrega por menú, platos
"va a esperar", lo sin elegir en la comanda y el menú del día desde caja."""
import base64
import re

from app.models import Orden
from app.services.escpos import render_orden
from tests.test_menu_encadenado import fonda  # noqa: F401  (fixture)


def _menu(fonda, segundo="Asado con puré", **extra):
    return {
        "menu_id": fonda["menu_id"], "cantidad": 1,
        "elecciones": {"1": fonda["platos"]["Sopa criolla"], "2": fonda["platos"][segundo]},
        **extra,
    }


def test_entrega_por_persona(client, fonda):
    # El bistec sale al momento: SOLO esa persona tiene que ir por tiempos
    r = client.post("/api/orders", json={"entrega": "junto", "menus": [
        _menu(fonda, "Bistec frito"),
        _menu(fonda),
    ]})
    assert r.status_code == 422

    r = client.post("/api/orders", json={"entrega": "junto", "menus": [
        _menu(fonda, "Bistec frito", entrega="separado"),
        _menu(fonda, entrega="junto"),
    ]})
    assert r.status_code == 201
    assert [m["entrega"] for m in r.json()["orden"]["menus"]] == ["separado", "junto"]


def test_entrega_invalida_por_menu(client, fonda):
    r = client.post("/api/orders", json={"menus": [_menu(fonda, entrega="volando")]})
    assert r.status_code == 422


def test_menu_sin_entrega_hereda_la_de_la_orden(client, fonda):
    r = client.post("/api/orders", json={"entrega": "separado", "menus": [_menu(fonda)]})
    assert r.json()["orden"]["menus"][0]["entrega"] == "separado"


def test_plato_va_a_esperar(client, fonda):
    r = client.post("/api/orders", json={"menus": [_menu(fonda, espera=[2])]})
    assert r.status_code == 201
    items = {i["tiempo_orden"]: i["espera"] for i in r.json()["orden"]["menus"][0]["items"]}
    assert items[2] is True and items[1] is False


def test_lo_que_espera_no_entra_a_la_tanda(client, fonda):
    client.post("/api/orders", json={"menus": [_menu(fonda, espera=[2])]})
    tandas = client.get("/api/orders/tandas").json()["tandas"]
    nombres = {p["nombre"] for t in tandas for p in t["platos"]}
    assert "Sopa criolla" in nombres
    assert "Asado con puré" not in nombres


def test_comanda_impresa_dice_espera_sin_elegir_y_entregas(client, db, fonda):
    client.post("/api/orders", json={"entrega": "junto", "menus": [
        _menu(fonda, espera=[2]),
        {"menu_id": fonda["menu_id"], "cantidad": 1,
         "elecciones": {"1": fonda["platos"]["Sopa criolla"]}, "entrega": "separado"},
    ]})
    orden = db.query(Orden).one()
    texto = render_orden(orden, {"nombre": "Fonda"}).decode("cp850", errors="ignore")
    assert "(ESPERA)" in texto
    # Lo que falta elegir va en un recuadro (borde doble) que no se confunde
    # con un plato; cada renglón cabe en la línea (si no, sale roto)
    ancho = 36 - 4  # 42 columnas con letras separadas → 36
    assert "║ " + "SEGUNDO".center(ancho) + " ║" in texto
    assert "║ " + "FALTA ELEGIR".center(ancho) + " ║" in texto
    assert "╔" + "═" * 34 + "╗" in texto
    assert "NO PREPARAR" not in texto  # confundía: solo "FALTA ELEGIR"
    assert "ENTREGA: 1 JUNTO / 1 SEPARADO" in texto


def test_caja_escoge_el_menu_del_dia_sin_admin(client, fonda):
    datos = client.get("/api/menu/caja").json()
    plantilla = datos["plantillas"][0]
    segundos = plantilla["tiempos"][1]["alternativas"]
    assert all(a["activo_hoy"] for a in segundos)

    # Sacar el tallarín de hoy: desaparece de las alternativas vendibles
    r = client.patch(f"/api/menu/platos/{fonda['platos']['Tallarín rojo']}/hoy",
                     json={"activo_hoy": False})
    assert r.status_code == 200
    hoy = client.get("/api/menu/today").json()["menus"][0]
    assert "Tallarín rojo" not in [a["nombre"] for a in hoy["tiempos"][1]["alternativas"]]

    # Apagar el menú entero y volverlo a prender
    client.patch(f"/api/menu/plantillas/{fonda['menu_id']}/hoy", json={"activo_hoy": False})
    assert client.get("/api/menu/today").json()["menus"] == []
    client.patch(f"/api/menu/plantillas/{fonda['menu_id']}/hoy", json={"activo_hoy": True})
    assert len(client.get("/api/menu/today").json()["menus"]) == 1

    assert client.patch("/api/menu/platos/9999/hoy", json={"activo_hoy": True}).status_code == 404


def test_caja_carga_un_menu_guardado(client, admin_headers, fonda):
    client.post("/api/menu/guardados", json={"nombre": "Lunes"}, headers=admin_headers)
    guardado = client.get("/api/menu/caja").json()["guardados"][0]
    client.patch(f"/api/menu/platos/{fonda['platos']['Tallarín rojo']}/hoy",
                 json={"activo_hoy": False})
    r = client.post(f"/api/menu/caja/guardados/{guardado['id']}/cargar")
    assert r.status_code == 200
    hoy = client.get("/api/menu/today").json()["menus"][0]
    assert "Tallarín rojo" in [a["nombre"] for a in hoy["tiempos"][1]["alternativas"]]


def test_nombre_de_la_persona_sale_en_la_comanda(client, db, fonda):
    r = client.post("/api/orders", json={"menus": [
        _menu(fonda, nombre_persona="  Juan "),
        {"menu_id": fonda["menu_id"], "cantidad": 1,
         "elecciones": {"1": fonda["platos"]["Sopa criolla"]}, "nombre_persona": "Ana"},
    ]})
    assert r.status_code == 201
    assert [m["nombre_persona"] for m in r.json()["orden"]["menus"]] == ["Juan", "Ana"]
    orden = db.query(Orden).one()
    texto = render_orden(orden, {"nombre": "Fonda"}).decode("cp850", errors="ignore")
    assert "Asado con puré (JUAN)" in texto
    assert "SEGUNDO (ANA)" in texto and "FALTA ELEGIR" in texto


def test_nombre_demasiado_largo_se_rechaza(client, fonda):
    r = client.post("/api/orders", json={"menus": [_menu(fonda, nombre_persona="x" * 41)]})
    assert r.status_code == 422


def test_cierre_viejo_no_sale_por_el_puente(client, db):
    """Un cierre de hace semanas (el puente estuvo apagado) no se imprime
    de la nada: se descarta de la cola. El de hoy sí sale."""
    from datetime import timedelta

    from app.models import CierreCaja, Config, hoy_lima
    from app.routes.impresion import CLAVE_CIERRE

    viejo = CierreCaja(fecha=hoy_lima() - timedelta(days=20), hora_apertura="08:00:00",
                       monto_apertura=0, hora_cierre="21:00:00")
    db.add(viejo)
    db.commit()
    db.add(Config(clave=CLAVE_CIERRE, valor=str(viejo.id)))
    db.commit()
    trabajos = client.get("/api/print/cola").json()["trabajos"]
    assert [t for t in trabajos if t["tipo"] == "cierre"] == []

    hoy = CierreCaja(fecha=hoy_lima(), hora_apertura="08:00:00", monto_apertura=0,
                     hora_cierre="21:00:00")
    db.add(hoy)
    db.commit()
    db.get(Config, CLAVE_CIERRE).valor = str(hoy.id)
    db.commit()
    trabajos = client.get("/api/print/cola").json()["trabajos"]
    assert [t["tipo"] for t in trabajos] == ["cierre"]


def test_elegir_despues_lo_que_quedo_sin_elegir(client, fonda):
    r = client.post("/api/orders", json={"entrega": "junto", "menus": [{
        "menu_id": fonda["menu_id"], "cantidad": 1,
        "elecciones": {"1": fonda["platos"]["Sopa criolla"]},
    }]})
    orden = r.json()["orden"]
    om = orden["menus"][0]
    assert om["pendientes"] == ["Segundo"]
    total_antes = orden["total"]

    # El bistec tiene recargo S/ 2 y sale al momento
    r = client.post(f"/api/orders/{orden['id']}/menus/{om['id']}/elegir",
                    json={"tiempo_orden": 2, "plato_id": fonda["platos"]["Bistec frito"]})
    assert r.status_code == 200
    despues = r.json()
    menu = despues["menus"][0]
    assert menu["pendientes"] == []
    assert "Bistec frito" in [i["nombre"] for i in menu["items"]]
    assert despues["total"] == round(total_antes + 2.0, 2)
    assert menu["entrega"] == "separado"  # al momento: esa persona va por tiempos

    # Elegir otra vez el mismo tiempo ya no se puede
    r = client.post(f"/api/orders/{orden['id']}/menus/{om['id']}/elegir",
                    json={"tiempo_orden": 2, "plato_id": fonda["platos"]["Tallarín rojo"]})
    assert r.status_code == 409


def test_elegir_fuera_de_las_opciones_se_rechaza(client, fonda):
    r = client.post("/api/orders", json={"menus": [{
        "menu_id": fonda["menu_id"], "cantidad": 1,
        "elecciones": {"1": fonda["platos"]["Sopa criolla"]},
    }]})
    orden = r.json()["orden"]
    om = orden["menus"][0]
    r = client.post(f"/api/orders/{orden['id']}/menus/{om['id']}/elegir",
                    json={"tiempo_orden": 2, "plato_id": fonda["platos"]["Chicha morada"]})
    assert r.status_code == 422


def test_soltar_lo_que_espera_lo_manda_a_la_tanda(client, fonda):
    r = client.post("/api/orders", json={"menus": [_menu(fonda, espera=[2])]})
    item = next(i for i in r.json()["orden"]["menus"][0]["items"] if i["tiempo_orden"] == 2)
    nombres = lambda: {p["nombre"] for t in client.get("/api/orders/tandas").json()["tandas"] for p in t["platos"]}  # noqa: E731
    assert "Asado con puré" not in nombres()
    assert client.post(f"/api/orders/items/{item['id']}/soltar").status_code == 200
    assert "Asado con puré" in nombres()


def test_tiempos_por_persona_en_la_comanda(client, db, fonda):
    client.post("/api/orders", json={"entrega": "junto", "menus": [
        _menu(fonda, "Bistec frito", entrega="separado"),
        _menu(fonda, entrega="junto"),
    ]})
    orden = db.query(Orden).one()
    texto = render_orden(orden, {"nombre": "Fonda"}).decode("cp850", errors="ignore")
    assert "Bistec frito (SEPARADO)" in texto
    assert "Asado con puré (SEPARADO)" not in texto


def test_dos_comandas_salen_dos_veces_por_el_puente(client, fonda):
    from app.models import Config

    r = client.post("/api/orders", json={"menus": [_menu(fonda)], "copias": 2})
    assert r.status_code == 201
    orden = r.json()["orden"]
    assert orden["copias"] == 2
    # En modo puente la orden queda en cola; sus bytes van dos veces
    import base64

    from app.db import SessionLocal

    db = SessionLocal()
    db.merge(Config(clave="modo_impresion", valor="puente"))
    db.commit()
    db.close()
    client.post(f"/api/orders/{orden['id']}/reprint")  # vuelve a la cola…
    trabajo = next(t for t in client.get("/api/print/cola").json()["trabajos"] if t["tipo"] == "orden")
    una = base64.b64decode(trabajo["datos_b64"])
    assert una.count(b"ORDEN #") == 1  # …y la reimpresión sale UNA vez

    r = client.post("/api/orders", json={"menus": [_menu(fonda)], "copias": 2})
    trabajos = [t for t in client.get("/api/print/cola").json()["trabajos"] if t["tipo"] == "orden"]
    nueva = next(t for t in trabajos if t["orden_id"] == r.json()["orden"]["id"])
    assert base64.b64decode(nueva["datos_b64"]).count(b"ORDEN #") == 2


def test_copias_fuera_de_rango_se_rechaza(client, fonda):
    assert client.post("/api/orders", json={"menus": [_menu(fonda)], "copias": 5}).status_code == 422


def test_cola_con_espera_larga_responde_al_entrar_un_ticket(client, fonda):
    """La app de la tablet pide la cola "esperando": sin trabajos espera
    hasta el límite; con un ticket pendiente responde al toque."""
    import threading
    import time as reloj

    from app.db import SessionLocal
    from app.models import Config

    db = SessionLocal()
    db.merge(Config(clave="modo_impresion", valor="puente"))
    db.commit()
    db.close()

    inicio = reloj.monotonic()
    vacia = client.get("/api/print/cola?esperar=1").json()
    assert vacia["trabajos"] == [] and reloj.monotonic() - inicio >= 0.9

    # Un pedido entra mientras la app espera: la respuesta llega antes del límite
    threading.Timer(0.5, lambda: client.post("/api/orders", json={"menus": [_menu(fonda)]})).start()
    inicio = reloj.monotonic()
    con_ticket = client.get("/api/print/cola?esperar=10").json()
    assert [t["tipo"] for t in con_ticket["trabajos"]] == ["orden"]
    assert reloj.monotonic() - inicio < 5


def test_cola_sin_espera_responde_al_toque(client):
    import time as reloj

    inicio = reloj.monotonic()
    assert client.get("/api/print/cola").status_code == 200
    assert reloj.monotonic() - inicio < 1


def test_comanda_plural_y_lineas_que_caben(client, db, fonda):
    """"3 SEGUNDOS" en plural, y ningún renglón pasa del ancho de la
    impresora (antes 64 columnas en una de 48 partían el recuadro)."""
    import re

    client.post("/api/orders", json={"menus": [
        {"menu_id": fonda["menu_id"], "cantidad": 3, "elecciones": {"1": fonda["platos"]["Sopa criolla"]}},
    ]})
    orden = db.query(Orden).one()
    for columnas in (32, 42, 48):
        datos = render_orden(orden, {"nombre": "Fonda"}, columnas=columnas)
        texto = datos.decode("cp850", errors="ignore")
        assert "3 SEGUNDOS" in texto
        # Cada renglón (sin comandos ESC/POS) entra en su ancho: el de los
        # platos lleva letras separadas (2 puntos) y entran menos
        con_espacio = (columnas * 12) // 14
        for linea in re.sub(r"\x1b.|\x1d.|\x1b \x02|\x1dV..", "", texto).split("\n"):
            limpia = re.sub(r"[\x00-\x1f]", "", linea)
            assert len(limpia) <= columnas, (columnas, limpia)
            if "║" in limpia or "╔" in limpia:
                assert len(limpia) == con_espacio


def test_ok_y_pago_en_la_comanda_y_precuenta(client, db, fonda):
    """"OK y pagó": la comanda dice PAGADO y detrás sale la precuenta
    (letra chica). "OK y no pagó": NO PAGO y queda en falta pagar."""
    from app.models import Config

    db.add(Config(clave="modo_impresion", valor="puente"))
    db.add(Config(clave="impresora_ip", valor="192.168.1.77"))
    db.commit()
    menu = {"menu_id": fonda["menu_id"], "cantidad": 1,
            "elecciones": {"1": fonda["platos"]["Sopa criolla"], "2": fonda["platos"]["Asado con puré"]}}
    pagada = client.post("/api/orders", json={"menus": [menu], "pago": "pagado"}).json()["orden"]
    debe = client.post("/api/orders", json={"menus": [menu], "pago": "pendiente"}).json()["orden"]
    assert pagada["pago_al_pedir"] == "pagado" and not pagada["pago_pendiente"]
    assert debe["pago_pendiente"] is True

    trabajos = {t["orden_id"]: base64.b64decode(t["datos_b64"]).decode("cp850", errors="ignore")
                for t in client.get("/api/print/cola").json()["trabajos"]}
    assert "PAGADO" in trabajos[pagada["id"]] and "PRECUENTA" in trabajos[pagada["id"]]
    assert "TOTAL PAGADO S/" in trabajos[pagada["id"]] and "\x1bM\x01" in trabajos[pagada["id"]]
    assert "NO PAGO" in trabajos[debe["id"]] and "PRECUENTA" not in trabajos[debe["id"]]
    assert client.post("/api/orders", json={"menus": [menu], "pago": "quizas"}).status_code == 422


def test_precuenta_corta_a_dos_columnas(client, db, fonda):
    """La precuenta describe la entrada/sopa y el segundo de cada menú en
    un renglón (también el de recargo, lo que falta elegir y la presa o
    el "sin puré"), sin el refresco del menú ni el pie largo."""
    import re

    from app.models import Plato
    from app.services.escpos import render_precuenta

    p = fonda["platos"]
    client.post("/api/orders", json={"pago": "pagado", "entrega": "separado", "menus": [
        {"menu_id": fonda["menu_id"], "cantidad": 2,
         "elecciones": {"1": p["Sopa criolla"], "2": p["Asado con puré"]},
         "variantes": {"2": {"opciones": ["sin_pure"]}}},
        {"menu_id": fonda["menu_id"], "cantidad": 1,
         "elecciones": {"1": p["Papa a la huancaína"], "2": p["Bistec frito"]}},
        {"menu_id": fonda["menu_id"], "cantidad": 1, "elecciones": {"1": p["Sopa criolla"]}},
    ], "items": [{"plato_id": p["Tallarín rojo"], "cantidad": 1},
                 {"plato_id": p["Chicha morada"], "cantidad": 2}]})
    orden = db.query(Orden).one()
    categorias = {pl.id: pl.categoria for pl in db.query(Plato).all()}
    texto = render_precuenta(orden, {"nombre": "Fonda"}, 48, categorias).decode("cp850", errors="ignore")
    lineas = [re.sub(r"[\x00-\x1f]", "", ln)
              for ln in re.sub(r"\x1dV..|\x1b[@taEM \-].|\x1d!.", "", texto).split("\n")]
    platos = [ln for ln in lineas if ln.startswith(("1x", "2x"))]
    assert any("Sopa criolla" in ln and "Asado con puré (sin puré)" in ln and ln.endswith("22.00")
               for ln in platos)
    assert any("Papa a la huancaína" in ln and "Bistec frito" in ln for ln in platos)  # con recargo
    assert any("Segundo: falta elegir" in ln for ln in platos)
    # Los sueltos van de a dos: segundo solo y gaseosas en un renglón
    assert any("Tallarín rojo" in ln and "Chicha morada" in ln for ln in platos)
    assert sum("Chicha morada" in ln for ln in lineas) == 1  # el refresco del menú no sale
    assert "Guarde este papel" not in texto and "Fonda" not in texto
    assert any("TOTAL PAGADO S/ 63.00" in ln for ln in lineas)
    assert all(len(ln) <= 64 for ln in lineas)
    assert len([ln for ln in lineas if ln.strip()]) <= 8


def test_precuenta_parte_nombres_largos_sin_pasarse(client, db, fonda):
    from app.services.escpos import render_precuenta

    p = fonda["platos"]
    client.post("/api/orders", json={"pago": "pagado", "menus": [
        {"menu_id": fonda["menu_id"], "cantidad": 1,
         "elecciones": {"1": p["Papa a la huancaína"], "2": p["Asado con puré"]},
         "variantes": {"2": {"opciones": ["sin_pure", "poco_arroz", "sin_ensalada", "sin_cebolla"]}}},
    ]})
    orden = db.query(Orden).one()
    for columnas in (32, 42, 48):
        texto = render_precuenta(orden, {}, columnas).decode("cp850", errors="ignore")
        for ln in texto.split("\n"):
            limpia = re.sub(r"[\x00-\x1f]", "", re.sub(r"\x1dV..|\x1b[@taEM \-].|\x1d!.", "", ln))
            assert len(limpia) <= columnas * 12 // 9, (columnas, limpia)
        assert "cebolla)" in texto  # partido en renglones, no cortado


def test_menu_de_solo_segundo_no_cuenta_en_la_entrega(client, db, fonda):
    """Ticket #39: un menú completo "separado" + otro de solo segundo que
    llegó "junto". El de un solo plato no tiene nada que separar: la
    comanda dice SEPARADO a secas, sin "(SEPARADO)" en cada plato."""
    from app.models import Plato

    p = fonda["platos"]
    r = client.post("/api/orders", json={"entrega": "separado", "menus": [
        {"menu_id": fonda["menu_id"], "cantidad": 1, "entrega": "separado",
         "elecciones": {"1": p["Papa a la huancaína"], "2": p["Tallarín rojo"]}},
        {"menu_id": fonda["menu_id"], "cantidad": 1, "entrega": "junto", "omitidos": [1],
         "elecciones": {"2": p["Tallarín rojo"]}},
    ]})
    assert r.status_code == 201, r.text
    orden = db.query(Orden).one()
    categorias = {pl.id: pl.categoria for pl in db.query(Plato).all()}
    texto = render_orden(orden, {}, 48, categorias).decode("cp850", errors="ignore")
    assert "ENTREGA: SEPARADO" in texto
    assert "JUNTO" not in texto and "(SEPARADO)" not in texto

    # Dos menús completos con entregas distintas sí se distinguen
    client.post("/api/orders", json={"entrega": "separado", "menus": [
        {"menu_id": fonda["menu_id"], "cantidad": 1, "entrega": "separado",
         "elecciones": {"1": p["Papa a la huancaína"], "2": p["Tallarín rojo"]}},
        {"menu_id": fonda["menu_id"], "cantidad": 1, "entrega": "junto",
         "elecciones": {"1": p["Sopa criolla"], "2": p["Asado con puré"]}},
    ]})
    orden = db.query(Orden).order_by(Orden.id.desc()).first()
    texto = render_orden(orden, {}, 48, categorias).decode("cp850", errors="ignore")
    assert "ENTREGA: 1 JUNTO / 1 SEPARADO" in texto and "(SEPARADO)" in texto
