from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..auth import emitir_token

router = APIRouter(prefix="/api/admin", tags=["admin"])


class LoginIn(BaseModel):
    password: str


@router.post("/login")
def login(payload: LoginIn):
    token = emitir_token(payload.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    return {"token": token}
