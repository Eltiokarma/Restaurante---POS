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
    except (ValueError, HTTPException):
        raise HTTPException(status_code=401, detail="Sesión de admin inválida")
    if not (valido and vigente):
        raise HTTPException(status_code=401, detail="Sesión de admin expirada o inválida")
