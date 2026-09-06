import json
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlalchemy.orm import selectinload

from ..auth import requiere_admin
from ..db import get_db
from ..models import (
    MenuAgregado, MenuAlternativa, MenuGuardado, MenuPlantilla, MenuTiempo, Plato,
    ahora_lima, hoy_lima,
)

router = APIRouter(prefix="/api/menu", tags=["menu"])

CATEGORIAS = ["entrada", "fondo", "bebida", "postre"]


class PlatoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    categoria: str
    precio: float
    activo_hoy: bool
    sale_al_momento: bool = False
    # Porciones que entran por tanda en cocina (0 = sin límite)
    capacidad_tanda: int = 0
    foto: str | None = None
    sinonimos: list[str] = []

    @field_validator("sinonimos", mode="before")
    @classmethod
    def _desde_json(cls, v):
        # En BD viven como texto JSON; hacia afuera siempre como lista
        if isinstance(v, str):
            try:
                return json.loads(v or "[]")
            except json.JSONDecodeError:
                return []
        return v or []


class PlatoIn(BaseModel):
    id: int | None = None
    nombre: str = Field(min_length=1, max_length=120)
    categoria: str
    precio: float = Field(gt=0)
    activo_hoy: bool = True
    sale_al_momento: bool = False
    capacidad_tanda: int = Field(default=0, ge=0, le=99)
    sinonimos: list[str] = Field(default_factory=list, max_length=30)


class MenuUpdate(BaseModel):
    platos: list[PlatoIn]


def _menus_activos(db: Session) -> list[dict]:
    """Menús encadenados vendibles hoy, con solo alternativas disponibles.

    Un tiempo con UNA alternativa se informa como incluido (la terminal no
    dibuja selector); un menú cuyo tiempo obligatorio quedó sin alternativas
    (todo agotado) no se ofrece.
    """
    plantillas = db.scalars(
        select(MenuPlantilla)
        .options(selectinload(MenuPlantilla.tiempos).selectinload(MenuTiempo.alternativas))
        .where(MenuPlantilla.activo_hoy == True)  # noqa: E712
        .order_by(MenuPlantilla.precio, MenuPlantilla.nombre)
    ).all()
    platos = {p.id: p for p in db.scalars(select(Plato)).all()}
    agregados = db.scalars(
        select(MenuAgregado).where(MenuAgregado.activo == True)  # noqa: E712
        .order_by(MenuAgregado.orden, MenuAgregado.nombre)
    ).all()
    menus = []
    for plantilla in plantillas:
        tiempos = []
        vendible = True
        for tiempo in plantilla.tiempos:
            alternativas = [
                {
                    "plato_id": a.plato_id,
                    "nombre": platos[a.plato_id].nombre,
                    "precio": platos[a.plato_id].precio,
                    "recargo": a.recargo,
                    "sale_al_momento": platos[a.plato_id].sale_al_momento,
                }
                for a in tiempo.alternativas
                if a.plato_id in platos and platos[a.plato_id].activo_hoy
            ]
            if not alternativas and tiempo.obligatorio:
                vendible = False
                break
            tiempos.append({
                "orden": tiempo.orden,
                "rotulo": tiempo.rotulo,
                "obligatorio": tiempo.obligatorio,
                "precio_extra": tiempo.precio_extra,
                "descuento_si_se_quita": tiempo.descuento_si_se_quita,
                "alternativas": alternativas,
            })
        if vendible:
            menus.append({
                "id": plantilla.id,
                "nombre": plantilla.nombre,
                "precio": plantilla.precio,
                "tiempos": tiempos,
                # Porciones que se pueden sumar (+presa, +refresco): las de
                # todos los menús (menu_id NULL) y las propias de este
                "agregados": [
                    {"id": a.id, "nombre": a.nombre, "precio": a.precio}
                    for a in agregados
                    if a.menu_id is None or a.menu_id == plantilla.id
                ],
            })
    return menus


@router.get("/today")
def menu_de_hoy(db: Session = Depends(get_db)):
    platos = db.scalars(
        select(Plato).where(Plato.activo_hoy == True).order_by(Plato.categoria, Plato.nombre)  # noqa: E712
    ).all()
    return {
        "categorias": CATEGORIAS,
        "platos": [PlatoOut.model_validate(p).model_dump() for p in platos],
        "menus": _menus_activos(db),
    }


@router.put("/today", dependencies=[Depends(requiere_admin)])
def actualizar_menu(payload: MenuUpdate, db: Session = Depends(get_db)):
    """Reemplaza el menú del día.

    Platos con id se actualizan; sin id se crean (y quedan en el catálogo).
    Todo plato que no venga en la lista se desactiva para hoy.
    """
    hoy = hoy_lima()
    ids_activos: set[int] = set()

    for p in payload.platos:
        if p.categoria not in CATEGORIAS:
            p.categoria = "fondo"
        sinonimos_json = json.dumps(
            [s.strip() for s in p.sinonimos if s.strip()], ensure_ascii=False
        )
        if p.id is not None:
            plato = db.get(Plato, p.id)
            if plato is None:
                continue
            plato.nombre = p.nombre
            plato.categoria = p.categoria
            plato.precio = round(p.precio, 2)
            plato.activo_hoy = p.activo_hoy
            plato.sale_al_momento = p.sale_al_momento
            plato.capacidad_tanda = p.capacidad_tanda
            plato.sinonimos = sinonimos_json
        else:
            plato = Plato(
                nombre=p.nombre,
                categoria=p.categoria,
                precio=round(p.precio, 2),
                activo_hoy=p.activo_hoy,
                en_catalogo=True,
                sale_al_momento=p.sale_al_momento,
                capacidad_tanda=p.capacidad_tanda,
                sinonimos=sinonimos_json,
            )
            db.add(plato)
            db.flush()
        if plato.activo_hoy:
            plato.ultima_vez_activo = hoy
        ids_activos.add(plato.id)

    for plato in db.scalars(select(Plato).where(Plato.activo_hoy == True)).all():  # noqa: E712
        if plato.id not in ids_activos:
            plato.activo_hoy = False

    db.commit()
    return menu_de_hoy(db)


@router.get("/catalog", dependencies=[Depends(requiere_admin)])
def catalogo(db: Session = Depends(get_db)):
    platos = db.scalars(
        select(Plato).where(Plato.en_catalogo == True).order_by(Plato.categoria, Plato.nombre)  # noqa: E712
    ).all()
    return {"platos": [PlatoOut.model_validate(p).model_dump() for p in platos]}


@router.get("/previous", dependencies=[Depends(requiere_admin)])
def menu_anterior(db: Session = Depends(get_db)):
    """Platos del último día de servicio anterior a hoy ("menú de ayer")."""
    hoy = hoy_lima()
    ultima_fecha = db.scalars(
        select(Plato.ultima_vez_activo)
        .where(Plato.ultima_vez_activo != None, Plato.ultima_vez_activo < hoy)  # noqa: E711
        .order_by(Plato.ultima_vez_activo.desc())
        .limit(1)
    ).first()
    if ultima_fecha is None:
        return {"fecha": None, "platos": []}
    platos = db.scalars(
        select(Plato)
        .where(Plato.ultima_vez_activo == ultima_fecha)
        .order_by(Plato.categoria, Plato.nombre)
    ).all()
    return {
        "fecha": ultima_fecha.isoformat(),
        "platos": [PlatoOut.model_validate(p).model_dump() for p in platos],
    }


# ---------- Fotos de plato (§4) ----------
#
# Las fotos viven junto a la base de datos (<carpeta de la BD>/fotos): en
# Railway eso es el volumen /data y sobreviven los despliegues. El nombre
# lleva un timestamp para que el navegador no sirva una foto vieja de caché.

EXTENSION_POR_TIPO = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_FOTO_BYTES = 5 * 1024 * 1024  # 5 MB de sobra para una foto de celular
PATRON_FOTO = re.compile(r"^plato-\d+-\d+\.(jpg|png|webp)$")


def _fotos_dir() -> Path:
    from ..db import DATABASE_PATH

    carpeta = Path(DATABASE_PATH).parent / "fotos"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _borrar_foto_anterior(plato: Plato) -> None:
    if plato.foto and PATRON_FOTO.match(plato.foto):
        anterior = _fotos_dir() / plato.foto
        if anterior.is_file():
            anterior.unlink()


@router.post("/platos/{plato_id}/foto", dependencies=[Depends(requiere_admin)])
async def subir_foto(plato_id: int, archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    plato = db.get(Plato, plato_id)
    if plato is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")
    extension = EXTENSION_POR_TIPO.get(archivo.content_type or "")
    if extension is None:
        raise HTTPException(status_code=422, detail="La foto debe ser JPG, PNG o WebP")
    contenido = await archivo.read()
    if len(contenido) > MAX_FOTO_BYTES:
        raise HTTPException(status_code=422, detail="La foto pesa más de 5 MB: achícala un poco")
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo llegó vacío")

    _borrar_foto_anterior(plato)
    nombre = f"plato-{plato.id}-{time.time_ns()}.{extension}"
    (_fotos_dir() / nombre).write_bytes(contenido)
    plato.foto = nombre
    db.commit()
    return {"plato_id": plato.id, "foto": nombre}


@router.delete("/platos/{plato_id}/foto", dependencies=[Depends(requiere_admin)])
def quitar_foto(plato_id: int, db: Session = Depends(get_db)):
    plato = db.get(Plato, plato_id)
    if plato is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")
    _borrar_foto_anterior(plato)
    plato.foto = None
    db.commit()
    return {"plato_id": plato.id, "foto": None}


@router.get("/fotos/{archivo}")
def servir_foto(archivo: str):
    """Sirve la foto de un plato. Sin auth ni PIN: la usa el <img> de la
    terminal (una etiqueta img no puede mandar headers) y una foto del
    menú no es información sensible."""
    if not PATRON_FOTO.match(archivo):
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    ruta = _fotos_dir() / archivo
    if not ruta.is_file():
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    # El nombre cambia con cada subida: cachear fuerte es seguro
    return FileResponse(ruta, headers={"Cache-Control": "public, max-age=86400"})


# ---------- Menús encadenados (plantillas) — admin ----------


class AlternativaIn(BaseModel):
    plato_id: int
    recargo: float = Field(default=0.0, ge=0)


class TiempoIn(BaseModel):
    rotulo: str = Field(min_length=1, max_length=60)
    obligatorio: bool = True
    # Precio de UNA porción adicional pedida con el menú (0 = no se ofrece)
    precio_extra: float = Field(default=0.0, ge=0)
    # Cuánto baja el menú si el cliente quita este tiempo (0 = no baja)
    descuento_si_se_quita: float = Field(default=0.0, ge=0)
    alternativas: list[AlternativaIn] = Field(default_factory=list, max_length=30)


class PlantillaIn(BaseModel):
    id: int | None = None
    nombre: str = Field(min_length=1, max_length=120)
    precio: float = Field(gt=0)
    activo_hoy: bool = True
    tiempos: list[TiempoIn] = Field(min_length=1, max_length=6)


class PlantillasUpdate(BaseModel):
    plantillas: list[PlantillaIn]


def _plantilla_a_dict(plantilla: MenuPlantilla, platos: dict[int, Plato]) -> dict:
    return {
        "id": plantilla.id,
        "nombre": plantilla.nombre,
        "precio": plantilla.precio,
        "activo_hoy": plantilla.activo_hoy,
        "tiempos": [
            {
                "orden": t.orden,
                "rotulo": t.rotulo,
                "obligatorio": t.obligatorio,
                "precio_extra": t.precio_extra,
                "descuento_si_se_quita": t.descuento_si_se_quita,
                "alternativas": [
                    {
                        "plato_id": a.plato_id,
                        "nombre": platos[a.plato_id].nombre if a.plato_id in platos else f"#{a.plato_id}",
                        "recargo": a.recargo,
                    }
                    for a in t.alternativas
                ],
            }
            for t in plantilla.tiempos
        ],
    }


@router.get("/plantillas", dependencies=[Depends(requiere_admin)])
def plantillas(db: Session = Depends(get_db)):
    """Todas las plantillas del catálogo (activas o no), para el admin."""
    lista = db.scalars(
        select(MenuPlantilla)
        .options(selectinload(MenuPlantilla.tiempos).selectinload(MenuTiempo.alternativas))
        .where(MenuPlantilla.en_catalogo == True)  # noqa: E712
        .order_by(MenuPlantilla.precio, MenuPlantilla.nombre)
    ).all()
    platos = {p.id: p for p in db.scalars(select(Plato)).all()}
    return {"plantillas": [_plantilla_a_dict(p, platos) for p in lista]}


@router.put("/plantillas", dependencies=[Depends(requiere_admin)])
def guardar_plantillas(payload: PlantillasUpdate, db: Session = Depends(get_db)):
    """Reemplaza las plantillas de menú (mismo criterio que el menú del día).

    Con id se actualiza (los tiempos se reemplazan enteros: el histórico
    vive en snapshots, no aquí); sin id se crea. Una plantilla del
    catálogo que no venga en la lista se retira (en_catalogo = False).
    """
    ids_enviados: set[int] = set()
    for p in payload.plantillas:
        if p.id is not None:
            plantilla = db.get(MenuPlantilla, p.id)
            if plantilla is None:
                continue
            plantilla.nombre = p.nombre
            plantilla.precio = round(p.precio, 2)
            plantilla.activo_hoy = p.activo_hoy
            plantilla.en_catalogo = True
            plantilla.tiempos.clear()
        else:
            plantilla = MenuPlantilla(
                nombre=p.nombre, precio=round(p.precio, 2),
                activo_hoy=p.activo_hoy, en_catalogo=True,
            )
            db.add(plantilla)
        for numero, t in enumerate(p.tiempos, start=1):
            tiempo = MenuTiempo(
                orden=numero,
                rotulo=t.rotulo.strip(),
                obligatorio=t.obligatorio,
                precio_extra=round(t.precio_extra, 2),
                descuento_si_se_quita=round(t.descuento_si_se_quita, 2),
            )
            for a in t.alternativas:
                tiempo.alternativas.append(
                    MenuAlternativa(plato_id=a.plato_id, recargo=round(a.recargo, 2))
                )
            plantilla.tiempos.append(tiempo)
        db.flush()
        ids_enviados.add(plantilla.id)

    for plantilla in db.scalars(
        select(MenuPlantilla).where(MenuPlantilla.en_catalogo == True)  # noqa: E712
    ).all():
        if plantilla.id not in ids_enviados:
            plantilla.en_catalogo = False
            plantilla.activo_hoy = False

    db.commit()
    return plantillas(db)


# ---------- Menús guardados ("el menú de los jueves") ----------
#
# Snapshot con nombre del menú del día completo (platos activos + plantillas
# con sus alternativas). Guardar con el mismo nombre lo actualiza; cargar
# uno reemplaza el menú de hoy con un toque.


class GuardadoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)


def _snapshot_de_hoy(db: Session) -> dict:
    activos = db.scalars(
        select(Plato).where(Plato.activo_hoy == True)  # noqa: E712
    ).all()
    plantillas_cat = db.scalars(
        select(MenuPlantilla)
        .options(selectinload(MenuPlantilla.tiempos).selectinload(MenuTiempo.alternativas))
        .where(MenuPlantilla.en_catalogo == True)  # noqa: E712
    ).all()
    return {
        "platos": [p.id for p in activos],
        "plantillas": [
            {
                "id": pl.id,
                "nombre": pl.nombre,
                "precio": pl.precio,
                "activo_hoy": pl.activo_hoy,
                "tiempos": [
                    {
                        "rotulo": t.rotulo,
                        "obligatorio": t.obligatorio,
                        "precio_extra": t.precio_extra,
                        "descuento_si_se_quita": t.descuento_si_se_quita,
                        "alternativas": [
                            {"plato_id": a.plato_id, "recargo": a.recargo}
                            for a in t.alternativas
                        ],
                    }
                    for t in pl.tiempos
                ],
            }
            for pl in plantillas_cat
        ],
    }


def _guardado_a_dict(g: MenuGuardado, platos: dict[int, Plato]) -> dict:
    datos = json.loads(g.datos_json)
    nombres = [platos[i].nombre for i in datos.get("platos", []) if i in platos]
    resumen = ", ".join(nombres[:6]) + ("…" if len(nombres) > 6 else "")
    return {
        "id": g.id,
        "nombre": g.nombre,
        "actualizado": g.actualizado.date().isoformat(),
        "cuantos_platos": len(nombres),
        "resumen": resumen,
    }


@router.get("/guardados", dependencies=[Depends(requiere_admin)])
def menus_guardados(db: Session = Depends(get_db)):
    platos = {p.id: p for p in db.scalars(select(Plato)).all()}
    lista = db.scalars(select(MenuGuardado).order_by(MenuGuardado.nombre)).all()
    return {"guardados": [_guardado_a_dict(g, platos) for g in lista]}


@router.post("/guardados", dependencies=[Depends(requiere_admin)], status_code=201)
def guardar_menu_de_hoy(payload: GuardadoIn, db: Session = Depends(get_db)):
    """Guarda el menú de hoy con un nombre; si ya existe, lo actualiza."""
    snapshot = _snapshot_de_hoy(db)
    if not snapshot["platos"]:
        raise HTTPException(status_code=422, detail="Hoy no hay platos activos que guardar")
    nombre = payload.nombre.strip()
    registro = db.scalar(
        select(MenuGuardado).where(MenuGuardado.nombre.ilike(nombre))
    )
    if registro is None:
        registro = MenuGuardado(nombre=nombre)
        db.add(registro)
    registro.nombre = nombre
    registro.datos_json = json.dumps(snapshot, ensure_ascii=False)
    registro.actualizado = ahora_lima()
    db.commit()
    return menus_guardados(db)


@router.post("/guardados/{guardado_id}/cargar", dependencies=[Depends(requiere_admin)])
def cargar_menu_guardado(guardado_id: int, db: Session = Depends(get_db)):
    """Convierte un menú guardado en el menú de HOY: activa sus platos
    (desactiva el resto) y restaura las plantillas con sus alternativas."""
    registro = db.get(MenuGuardado, guardado_id)
    if registro is None:
        raise HTTPException(status_code=404, detail="Ese menú guardado ya no existe")
    datos = json.loads(registro.datos_json)

    hoy = hoy_lima()
    ids = set(datos.get("platos", []))
    for plato in db.scalars(select(Plato)).all():
        if plato.id in ids:
            plato.activo_hoy = True
            plato.ultima_vez_activo = hoy
        elif plato.activo_hoy:
            plato.activo_hoy = False

    plantillas_in = []
    for p in datos.get("plantillas", []):
        obj = PlantillaIn(**p)
        # La plantilla pudo borrarse desde que se guardó: se recrea
        if obj.id is not None and db.get(MenuPlantilla, obj.id) is None:
            obj.id = None
        plantillas_in.append(obj)
    if plantillas_in:
        guardar_plantillas(PlantillasUpdate(plantillas=plantillas_in), db)

    db.commit()
    return menu_de_hoy(db)


@router.delete("/guardados/{guardado_id}", dependencies=[Depends(requiere_admin)])
def borrar_menu_guardado(guardado_id: int, db: Session = Depends(get_db)):
    registro = db.get(MenuGuardado, guardado_id)
    if registro is not None:
        db.delete(registro)
        db.commit()
    return menus_guardados(db)


# ---------- Agregados del menú (+presa, +refresco…) ----------


class AgregadoIn(BaseModel):
    id: int | None = None
    nombre: str = Field(min_length=1, max_length=60)
    precio: float = Field(gt=0)
    activo: bool = True


class AgregadosUpdate(BaseModel):
    agregados: list[AgregadoIn] = Field(max_length=30)


def _listar_agregados(db: Session) -> dict:
    lista = db.scalars(
        select(MenuAgregado).where(MenuAgregado.menu_id == None)  # noqa: E711
        .order_by(MenuAgregado.orden, MenuAgregado.nombre)
    ).all()
    return {"agregados": [
        {"id": a.id, "nombre": a.nombre, "precio": a.precio, "activo": a.activo}
        for a in lista
    ]}


@router.get("/agregados", dependencies=[Depends(requiere_admin)])
def agregados(db: Session = Depends(get_db)):
    """Los agregados comunes a todos los menús, para el admin."""
    return _listar_agregados(db)


@router.put("/agregados", dependencies=[Depends(requiere_admin)])
def guardar_agregados(payload: AgregadosUpdate, db: Session = Depends(get_db)):
    """Reemplaza la lista de agregados comunes (mismo criterio que las
    plantillas). Las órdenes históricas no cambian: guardan snapshot."""
    ids_enviados: set[int] = set()
    for numero, a in enumerate(payload.agregados, start=1):
        if a.id is not None:
            agregado = db.get(MenuAgregado, a.id)
            if agregado is None or agregado.menu_id is not None:
                continue
        else:
            agregado = MenuAgregado(menu_id=None)
            db.add(agregado)
        agregado.nombre = a.nombre.strip()
        agregado.precio = round(a.precio, 2)
        agregado.activo = a.activo
        agregado.orden = numero
        db.flush()
        ids_enviados.add(agregado.id)

    for agregado in db.scalars(
        select(MenuAgregado).where(MenuAgregado.menu_id == None)  # noqa: E711
    ).all():
        if agregado.id not in ids_enviados:
            db.delete(agregado)

    db.commit()
    return _listar_agregados(db)
