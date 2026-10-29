"""Autenticación simple de admin para un solo local.

Token stateless: "<timestamp>.<hmac(ADMIN_PASSWORD, timestamp)>", válido 12
horas. Se envía en el header X-Admin-Token (el frontend lo guarda en
localStorage). Suficiente para un restaurante con una laptop; no es un
sistema multiusuario.
"""
import hashlib
import hmac
import os
import time

from fastapi import Header, HTTPException

TOKEN_TTL_SECONDS = 12 * 60 * 60


def _password() -> str:
    pw = os.getenv("ADMIN_PASSWORD", "")
    if not pw:
        raise HTTPException(status_code=500, detail="ADMIN_PASSWORD no configurada en .env")
    return pw


def _firmar(timestamp: str) -> str:
    return hmac.new(_password().encode(), timestamp.encode(), hashlib.sha256).hexdigest()


def emitir_token(password: str) -> str | None:
    if not hmac.compare_digest(password, _password()):
        return None
    ts = str(int(time.time()))
    return f"{ts}.{_firmar(ts)}"


def requiere_admin(x_admin_token: str = Header(default="")) -> None:
    try:
        ts, firma = x_admin_token.split(".", 1)
        valido = hmac.compare_digest(firma, _firmar(ts))
        vigente = (time.time() - int(ts)) < TOKEN_TTL_SECONDS
    except ValueError:
        # Token ausente o malformado. Una ADMIN_PASSWORD sin configurar
        # sí debe propagarse como error 500, no como credencial inválida.
        raise HTTPException(status_code=401, detail="Sesión de admin inválida")
    if not (valido and vigente):
        raise HTTPException(status_code=401, detail="Sesión de admin expirada o inválida")


# ---------- Equipo: cada persona con su PIN (pedido del dueño) ----------
#
# La sesión de una persona es un token igual de simple que el del admin,
# firmado con otra llave derivada de ADMIN_PASSWORD: "u<id>.<ts>.<firma>".
# El rol NO va en el token: se lee de la base en cada pedido, así que
# desactivar a alguien o cambiarle el rol vale al toque.

SESION_EQUIPO_SEG = 14 * 60 * 60  # un turno largo
ITERACIONES_PIN = 60_000


def _firmar_equipo(cuerpo: str) -> str:
    llave = (_password() + ":equipo").encode()
    return hmac.new(llave, cuerpo.encode(), hashlib.sha256).hexdigest()


def emitir_token_equipo(usuario_id: int) -> str:
    cuerpo = f"u{usuario_id}.{int(time.time())}"
    return f"{cuerpo}.{_firmar_equipo(cuerpo)}"


def leer_token_equipo(token: str) -> int | None:
    """El id de la persona si el token es válido y vigente; si no, None."""
    try:
        uid, ts, firma = token.split(".")
        vigente = (time.time() - int(ts)) < SESION_EQUIPO_SEG
        valido = hmac.compare_digest(firma, _firmar_equipo(f"{uid}.{ts}"))
        if not (uid.startswith("u") and vigente and valido):
            return None
        return int(uid[1:])
    except (ValueError, HTTPException):
        # Malformado, o ADMIN_PASSWORD sin configurar: no hay sesión
        return None


def cifrar_pin(pin: str) -> str:
    sal = os.urandom(16)
    huella = hashlib.pbkdf2_hmac("sha256", pin.encode(), sal, ITERACIONES_PIN)
    return f"{sal.hex()}${huella.hex()}"


def pin_correcto(pin: str, guardado: str) -> bool:
    try:
        sal, huella = guardado.split("$")
        calculada = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(sal), ITERACIONES_PIN)
    except ValueError:
        return False
    return hmac.compare_digest(calculada.hex(), huella)


# Un PIN de 4 dígitos se adivina rápido: tras 5 fallos seguidos esa
# persona queda bloqueada 5 minutos. En memoria (un solo proceso).
MAX_FALLOS_PIN = 5
BLOQUEO_PIN_SEG = 5 * 60
_fallos_pin: dict[int, tuple[int, float]] = {}


def segundos_bloqueado(usuario_id: int) -> int:
    fallos, hasta = _fallos_pin.get(usuario_id, (0, 0.0))
    return max(0, int(hasta - time.time())) if fallos >= MAX_FALLOS_PIN else 0


def anotar_intento_pin(usuario_id: int, acerto: bool) -> None:
    if acerto:
        _fallos_pin.pop(usuario_id, None)
        return
    fallos, hasta = _fallos_pin.get(usuario_id, (0, 0.0))
    if fallos >= MAX_FALLOS_PIN and time.time() >= hasta:
        fallos = 0  # ya pasó el castigo: cuenta de nuevo
    fallos += 1
    _fallos_pin[usuario_id] = (fallos, time.time() + BLOQUEO_PIN_SEG if fallos >= MAX_FALLOS_PIN else 0.0)


def reiniciar_intentos_pin() -> None:
    _fallos_pin.clear()
