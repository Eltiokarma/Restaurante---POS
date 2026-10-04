"""Intérprete RÁPIDO de pedidos por voz: palabras clave, sin IA.

La IA tarda 2–4 s en entender un pedido; la mayoría de pedidos del local
son simples ("dos almuerzos con chairito y pollo a la olla", "un segundo
solo de locro para llevar"). Este intérprete los resuelve al instante con
reglas fijas y los sinónimos que ya tiene cada plato.

Regla de oro: NUNCA adivina. Si queda una sola palabra que no entiende,
o el pedido tiene algo que necesita criterio ("uno con causa y el otro…",
"después", "sin cebolla", correcciones), devuelve None y el pedido va a
la IA como siempre. El resultado tiene el MISMO formato que la IA, así que
pasa por la misma validación (_depurar) y la misma pantalla de
verificación.
"""
import re
import unicodedata

# Palabras que no cambian el pedido
RELLENO = {
    "dame", "deme", "denme", "dar", "quiero", "queremos", "quisiera", "quisieramos", "me", "nos",
    "das", "da", "por", "favor", "porfa", "hola", "buenas", "buenos", "dias", "tardes", "noches",
    "senorita", "senor", "joven", "amigo", "amiga", "casera", "casero", "este", "eh", "em", "mm",
    "ya", "va", "a", "querer", "van", "vamos", "ser", "con", "de", "del", "el", "la", "los", "las",
    "en", "que", "sea", "pues", "tambien", "ademas", "les", "le", "lo", "al", "su", "sus", "mi",
    "pedido", "pedir", "voy", "vas", "vengo", "traeme", "traigame", "manda", "mandame", "porfavor",
    "gracias", "seria", "serian", "sera", "son", "es", "mismo", "nada", "mas", "para",
}

# Si aparece cualquiera de estas, el pedido necesita criterio: a la IA
A_LA_IA = {
    "uno", "otro", "otra", "otros", "otras", "despues", "luego", "ahorita", "todavia", "aun",
    "no", "mejor", "sin", "pero", "cambia", "cambiame", "extra", "doble", "aparte", "cada",
    "todos", "todas", "primero", "segunda", "tercero", "nombre", "llama",
}

NUMEROS = {
    "un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10,
}

LETRAS_MESA = {"a": "a", "be": "b", "b": "b", "ce": "c", "c": "c", "de": "d", "d": "d"}


def normalizar(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn"
    )
    sin_tildes = sin_tildes.replace("tupper", "taper").replace("toper", "taper")
    # Comas y puntos separan; el punto decimal ("1.5") se queda
    sin_tildes = re.sub(r"(?<!\d)[.,;:!?¡¿](?!\d)|[.,;:!?¡¿](?=\s|$)", " , ", sin_tildes)
    sin_tildes = re.sub(r"[^a-z0-9., ]", " ", sin_tildes)
    sin_tildes = " ".join(sin_tildes.split())

    # "mesa tres be" / "mesa 3 b" → "mesa 3b" (la letra suelta no se pierde)
    def _mesa(m: re.Match) -> str:
        numero = m.group(1)
        numero = str(NUMEROS.get(numero, numero))
        letra = LETRAS_MESA.get(m.group(2) or "", "")
        return f"mesa {numero}{letra}"

    numeros = "|".join(NUMEROS)
    letras = "|".join(LETRAS_MESA)
    # "para la 7" / "en la siete" = la mesa ("la una" no: suena a hora)
    numeros_mesa = "|".join(n for n in NUMEROS if n not in ("un", "una"))
    sin_tildes = re.sub(rf"\b(para|en) la (\d+|{numeros_mesa})\b", r"\1 la mesa \2", sin_tildes)
    return re.sub(rf"\bmesa (\d+|{numeros})(?: ({letras})\b)?", _mesa, sin_tildes)


def _variantes(frase: str) -> set[tuple[str, ...]]:
    """La frase y su plural en la última palabra ("sopa" → "sopas")."""
    palabras = tuple(normalizar(frase).replace(",", " ").split())
    if not palabras:
        return set()
    variantes = {palabras}
    # Plural en la última palabra ("sopas") o en la primera ("locros de pecho")
    for sufijo in ("s", "es"):
        variantes.add(palabras[:-1] + (palabras[-1] + sufijo,))
        variantes.add((palabras[0] + sufijo,) + palabras[1:])
    return variantes


class _Lexico:
    def __init__(self, contexto: dict):
        self.frases: dict[tuple[str, ...], tuple] = {}
        menu = contexto["menus"][0]
        self.menu = menu
        tiempos = sorted(menu["tiempos"], key=lambda t: t["orden"])
        self.entrada = tiempos[0]["orden"]
        segundos = [t for t in tiempos if "segundo" in t["rotulo"].lower()]
        self.segundo = (segundos[0] if segundos else tiempos[min(1, len(tiempos) - 1)])["orden"]

        platos: dict[tuple[str, ...], set] = {}
        for t in tiempos:
            for a in t["alternativas"]:
                nombres = [a["nombre"], *a.get("sinonimos", [])]
                # "Locro de Pecho con Arroz Blanco" → también "locro de pecho"
                corto = re.split(r"\s+con\s+", a["nombre"], flags=re.I)[0]
                nombres.append(corto)
                for n in nombres:
                    for v in _variantes(n):
                        platos.setdefault(v, set()).add((t["orden"], a["plato_id"]))
        for frase, destinos in platos.items():
            self.frases[frase] = ("PLATO", destinos)

        claves = {
            ("almuerzo",): ("MENU",), ("almuerzos",): ("MENU",), ("menu",): ("MENU",),
            ("menus",): ("MENU",), ("menues",): ("MENU",),
            ("segundo", "solo"): ("SEG_SOLO",), ("segundos", "solos"): ("SEG_SOLO",),
            ("solo", "segundo"): ("SEG_SOLO",), ("solo", "el", "segundo"): ("SEG_SOLO",),
            ("solo",): ("SOLO",), ("sola",): ("SOLO",), ("solos",): ("SOLO",),
            ("solas",): ("SOLO",), ("nomas",): ("SOLO",),
            ("para", "llevar"): ("EMP", "taper"), ("llevar",): ("EMP", "taper"),
            ("taper",): ("EMP", "taper"), ("tapers",): ("EMP", "taper"),
            ("bolsa",): ("EMP", "bolsa"), ("bolsas",): ("EMP", "bolsa"),
            ("lonchera",): ("EMP", "lonchera"), ("loncheras",): ("EMP", "lonchera"),
            ("para", "comer", "aqui"): ("EMP", "mesa"), ("para", "comer", "aca"): ("EMP", "mesa"),
            ("para", "aqui"): ("EMP", "mesa"), ("para", "aca"): ("EMP", "mesa"),
            ("aqui",): ("EMP", "mesa"), ("aca",): ("EMP", "mesa"),
            ("mesa",): ("MESA",), ("mesas",): ("MESA",),
            ("todo", "junto"): ("ENTREGA", "junto"), ("junto",): ("ENTREGA", "junto"),
            ("juntos",): ("ENTREGA", "junto"),
            ("por", "tiempos"): ("ENTREGA", "separado"), ("separado",): ("ENTREGA", "separado"),
            ("un", "par", "de"): ("NUM", 2), ("par", "de"): ("NUM", 2),
            ("y",): ("Y",), (",",): ("SEP",),
            # "de entrada causa y de segundo locro": el rótulo no cambia nada
            ("de", "entrada"): ("NADA",), ("entrada",): ("NADA",),
            ("de", "segundo"): ("NADA",), ("segundo",): ("NADA",),
        }
        for frase, token in claves.items():
            # Un plato llamado igual que una palabra clave gana la clave
            self.frases.setdefault(frase, token)
        for palabra, n in NUMEROS.items():
            self.frases.setdefault((palabra,), ("NUM", n))

        # Gaseosas: marca ("inca kola") + tamaño ("personal", "1 l", "1.5 l")
        self.gaseosas: dict[tuple[str, str], int] = {}
        for g in contexto.get("gaseosas", []):
            nombre = normalizar(g["nombre"]).replace(",", " ").strip()
            for sufijo, tamano in ((" personal", "personal"), (" 1.5 l", "1.5l"), (" 1 l", "1l")):
                if nombre.endswith(sufijo):
                    marca = nombre[: -len(sufijo)].strip()
                    break
            else:
                continue
            self.gaseosas[(marca, tamano)] = g["id"]
            palabras = marca.split()
            for frase in (_variantes(marca) | _variantes(palabras[0]) | {("".join(palabras),)}):
                self.frases.setdefault(frase, ("MARCA", marca))
        for frase, tam in {
            ("personal",): "personal", ("personales",): "personal", ("chica",): "personal",
            ("chicas",): "personal", ("de", "litro"): "1l", ("litro",): "1l", ("litros",): "1l",
            ("de", "un", "litro"): "1l", ("de", "litro", "y", "medio"): "1.5l",
            ("litro", "y", "medio"): "1.5l", ("1.5",): "1.5l", ("de", "1.5"): "1.5l",
        }.items():
            self.frases.setdefault(frase, ("TAMANO", tam))

        self.mesas = {re.sub(r"\s+", "", normalizar(m["nombre"])): m["id"] for m in contexto.get("mesas", [])}
        self.largo_max = max(len(f) for f in self.frases)

    def tokenizar(self, palabras: list[str]) -> list[tuple] | None:
        tokens: list[tuple] = []
        i = 0
        while i < len(palabras):
            for largo in range(min(self.largo_max, len(palabras) - i), 0, -1):
                trozo = tuple(palabras[i:i + largo])
                if trozo in self.frases:
                    token = self.frases[trozo]
                    # "locro ... pecho": el mismo plato nombrado dos veces seguidas
                    if not (token[0] == "PLATO" and tokens and tokens[-1] == token):
                        tokens.append(token)
                    i += largo
                    break
            else:
                palabra = palabras[i]
                if palabra in A_LA_IA:
                    return None
                if palabra.isdigit():
                    tokens.append(("NUM", int(palabra)))
                elif palabra in RELLENO:
                    pass
                else:
                    tokens.append(("RARO", palabra))
                i += 1
        return tokens


def interpretar_rapido(texto: str, contexto: dict) -> dict | None:
    """El pedido en el formato de la IA, o None si hace falta la IA."""
    if len(contexto.get("menus", [])) != 1:
        return None  # varios menús: hay que decidir cuál, eso es criterio
    lexico = _Lexico(contexto)
    palabras = normalizar(texto).split()
    tokens = lexico.tokenizar(palabras)
    if tokens is None:
        return None

    grupos: list[dict] = []
    gaseosas: dict[int, int] = {}
    mesa = ""
    entrega = "auto"
    pendiente_num: int | None = None
    empaque_suelto: str | None = None  # "para llevar, dos almuerzos…"
    actual: dict | None = None
    corte = False  # hubo "y" o coma desde el último plato

    def nuevo(cantidad: int = 1) -> dict:
        grupo = {"cantidad": cantidad, "clase": "almuerzo", "platos": {}, "menu": False,
                 "empaques": [], "ultimo": None}
        grupos.append(grupo)
        return grupo

    i = 0
    while i < len(tokens):
        token = tokens[i]
        tipo = token[0]
        if tipo == "RARO":
            return None
        if tipo == "NUM":
            if i + 1 < len(tokens) and tokens[i + 1][0] == "MARCA":
                pendiente_num = token[1]
            else:
                actual = nuevo(token[1])
                corte = False
        elif tipo == "MENU":
            if actual is None or actual["menu"] or actual["platos"] or actual["clase"] != "almuerzo":
                actual = nuevo(1)
            actual["menu"] = True
            corte = False
        elif tipo == "SEG_SOLO":
            if actual is None or actual["menu"] or actual["platos"] or actual["clase"] != "almuerzo":
                actual = nuevo(1)
            actual["clase"] = "segundo_solo"
        elif tipo == "PLATO":
            destinos = token[1]
            if len({d[1] for d in destinos}) > 1:
                return None  # "pollo" con dos pollos en el menú: ambiguo
            tiempo, plato_id = next(iter(destinos))
            if actual is None or tiempo in actual["platos"] or (
                corte and actual["platos"] and not actual["menu"] and tiempo in actual["platos"]
            ):
                actual = nuevo(1)
            if actual["clase"] == "segundo_solo" and tiempo == lexico.entrada:
                return None
            if actual["clase"] == "sopa_sola" and tiempo != lexico.entrada:
                return None
            actual["platos"][tiempo] = plato_id
            actual["ultimo"] = tiempo
            corte = False
        elif tipo == "SOLO":
            if actual is None or len(actual["platos"]) != 1:
                return None
            tiempo = next(iter(actual["platos"]))
            actual["clase"] = "sopa_sola" if tiempo == lexico.entrada else "segundo_solo"
        elif tipo == "EMP":
            if actual is None:
                empaque_suelto = token[1]
            else:
                actual["empaques"].append((token[1], actual["ultimo"]))
        elif tipo == "MESA":
            # "para la mesa" sin número = comer en el local; con número = cuál
            siguiente = tokens[i + 1] if i + 1 < len(tokens) else None
            nombre = ""
            usados = 0
            if siguiente is not None and siguiente[0] == "NUM":
                nombre, usados = str(siguiente[1]), 1
            elif siguiente is not None and siguiente[0] == "RARO" and re.fullmatch(r"\d+[a-d]", siguiente[1]):
                nombre, usados = siguiente[1], 1
            if usados:
                # "mesa 3" con 3A/3B/3C vale: el depurado elige la libre
                if nombre not in lexico.mesas and not any(
                    re.fullmatch(rf"{re.escape(nombre)}[a-z]", m) for m in lexico.mesas
                ):
                    return None  # una mesa que no existe: que lo vea la IA
                mesa = nombre
                i += usados
            elif actual is None:
                empaque_suelto = "mesa"
            else:
                actual["empaques"].append(("mesa", actual["ultimo"]))
        elif tipo == "MARCA":
            marca = token[1]
            tamano = "personal"
            if i + 1 < len(tokens) and tokens[i + 1][0] == "TAMANO":
                tamano = tokens[i + 1][1]
                i += 1
            bebida_id = lexico.gaseosas.get((marca, tamano))
            if bebida_id is None:
                return None
            gaseosas[bebida_id] = gaseosas.get(bebida_id, 0) + (pendiente_num or 1)
            pendiente_num = None
        elif tipo == "TAMANO":
            return None  # "de litro" suelto, sin marca
        elif tipo == "ENTREGA":
            entrega = token[1]
        elif tipo in ("Y", "SEP", "NADA"):
            corte = tipo != "NADA" or corte
        i += 1

    if not grupos and not gaseosas:
        return None

    # "Dos sopas y dos locros": entradas y segundos sueltos con la misma
    # cantidad se emparejan en las mismas personas
    unidos: list[dict] = []
    for grupo in grupos:
        previo = unidos[-1] if unidos else None
        if (
            previo is not None and not previo["menu"] and not grupo["menu"]
            and previo["clase"] == grupo["clase"] == "almuerzo"
            and set(previo["platos"]) == {lexico.entrada}
            and set(grupo["platos"]) == {lexico.segundo}
            and previo["cantidad"] == grupo["cantidad"]
        ):
            previo["platos"].update(grupo["platos"])
            previo["empaques"] += [(e, t if t is not None else lexico.segundo) for e, t in grupo["empaques"]]
            continue
        unidos.append(grupo)

    personas = []
    for grupo in unidos:
        if grupo["cantidad"] <= 0 or grupo["cantidad"] > 20:
            return None
        if grupo["clase"] == "almuerzo" and not grupo["menu"] and len(grupo["platos"]) == 1:
            # "dos sopas" a secas: ¿almuerzos o sopas solas? Criterio → IA
            return None
        if grupo["clase"] == "almuerzo" and not grupo["menu"] and not grupo["platos"]:
            return None
        sin = []
        if grupo["clase"] == "segundo_solo":
            sin = [lexico.entrada]
        elif grupo["clase"] == "sopa_sola":
            sin = [lexico.segundo]

        empaques_dichos = grupo["empaques"] or ([(empaque_suelto, None)] if empaque_suelto else [])
        distintos = {e for e, _ in empaques_dichos}
        empaque = "mesa"
        por_plato: dict[int, str] = {}
        if len(distintos) == 1:
            empaque = next(iter(distintos))
        elif len(distintos) > 1:
            # "la sopa en bolsa y el lomo en táper": cada uno al plato que sigue
            for e, tiempo in empaques_dichos:
                if tiempo is None:
                    return None
                por_plato[tiempo] = e
            empaque = por_plato.get(lexico.segundo) or next(iter(por_plato.values()))
        personas.append({
            "menu_id": lexico.menu["id"],
            "cantidad": grupo["cantidad"],
            "elecciones": [
                {"tiempo_orden": t, "plato_id": p,
                 "empaque": por_plato[t] if por_plato.get(t, empaque) != empaque else "igual",
                 "espera": False}
                for t, p in sorted(grupo["platos"].items())
            ],
            "sin": sin,
            "empaque": empaque,
            "entrega": entrega,
            "nombre": "",
            "nota": "",
            "agregados": [],
        })

    return {
        "personas": personas,
        "items": [],
        "gaseosas": [{"bebida_id": b, "cantidad": n} for b, n in gaseosas.items()],
        # El nombre exacto, o solo el número ("3") si no dijo la letra
        "mesa": next((m for m in contexto.get("mesas", [])
                      if re.sub(r"\s+", "", normalizar(m["nombre"])) == mesa), {}).get("nombre", mesa),
        "no_encontrados": [],
        "notas": "",
    }
