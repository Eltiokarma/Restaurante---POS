"""Puente de impresión del local.

Corre en cualquier PC o aparato de la red del restaurante y conecta el
POS (aunque viva en la nube, ej. Railway) con la impresora térmica de
red: pide la cola cada 3 segundos, manda los bytes ESC/POS a la impresora
(puerto RAW, normalmente 9100) y confirma cada ticket impreso.

No necesita instalar nada: solo Python 3 (librería estándar).

Uso:
    python puente_impresion.py --url https://TU-POS.up.railway.app --pin 1234

La IP y el puerto de la impresora se configuran en el POS:
Admin → Configuración → "Impresora de tickets" (modo "puente").
"""
import argparse
import base64
import json
import socket
import sys
import time
import urllib.error
import urllib.request

INTERVALO_SEG = 3
TIMEOUT_IMPRESORA_SEG = 10


def api(url_base: str, pin: str, ruta: str, metodo: str = "GET") -> dict:
    peticion = urllib.request.Request(url_base + ruta, method=metodo)
    if pin:
        peticion.add_header("X-Pin-Local", pin)
    if metodo == "POST":
        peticion.add_header("Content-Type", "application/json")
        peticion.data = b"{}"
    with urllib.request.urlopen(peticion, timeout=15) as respuesta:
        return json.loads(respuesta.read())


def imprimir(ip: str, puerto: int, datos: bytes) -> None:
    with socket.create_connection((ip, puerto), timeout=TIMEOUT_IMPRESORA_SEG) as conexion:
        conexion.sendall(datos)


def ciclo(url_base: str, pin: str) -> None:
    aviso_sin_ip = False
    print(f"🖨  Puente de impresión conectado a {url_base}")
    print("    (deja esta ventana abierta; Ctrl+C para salir)")
    while True:
        try:
            cola = api(url_base, pin, "/api/print/cola")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print("✖ El POS rechazó el PIN. Revisa el valor de --pin y vuelve a iniciar.")
                sys.exit(1)
            print(f"… el POS respondió {e.code}; reintento en {INTERVALO_SEG} s")
            time.sleep(INTERVALO_SEG)
            continue
        except Exception as e:
            print(f"… sin conexión con el POS ({e}); reintento en {INTERVALO_SEG} s")
            time.sleep(INTERVALO_SEG)
            continue

        impresora = cola.get("impresora") or {}
        ip = (impresora.get("ip") or "").strip()
        puerto = int(impresora.get("puerto") or 9100)
        trabajos = cola.get("trabajos") or []

        if trabajos and not ip:
            if not aviso_sin_ip:
                print("⚠ Hay tickets en cola pero falta la IP de la impresora:")
                print("  ponla en Admin → Configuración → Impresora de tickets.")
                aviso_sin_ip = True
            time.sleep(INTERVALO_SEG)
            continue
        aviso_sin_ip = False

        for trabajo in trabajos:
            datos = base64.b64decode(trabajo["datos_b64"])
            try:
                imprimir(ip, puerto, datos)
            except Exception as e:
                print(f"✖ No se pudo imprimir #{trabajo['numero']}: {e}")
                print(f"  Revisa que la impresora esté prendida y su IP sea {ip}:{puerto}.")
                break  # el ticket sigue en cola; se reintenta en el próximo ciclo
            if trabajo["tipo"] == "orden":
                try:
                    api(url_base, pin, f"/api/orders/{trabajo['orden_id']}/printed", "POST")
                except Exception:
                    pass  # si no se pudo confirmar, el próximo ciclo lo reintenta
            print(f"✔ Ticket #{trabajo['numero']} impreso")

        time.sleep(INTERVALO_SEG)


def main() -> None:
    parser = argparse.ArgumentParser(description="Puente de impresión del POS")
    parser.add_argument("--url", required=True, help="URL del POS (ej. https://tu-pos.up.railway.app o http://192.168.1.50:8000)")
    parser.add_argument("--pin", default="", help="PIN_LOCAL del POS (si está configurado)")
    argumentos = parser.parse_args()
    try:
        ciclo(argumentos.url.rstrip("/"), argumentos.pin)
    except KeyboardInterrupt:
        print("\nPuente detenido. ¡Hasta luego!")


if __name__ == "__main__":
    main()
