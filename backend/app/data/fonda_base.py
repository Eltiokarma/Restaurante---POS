"""Bases pregrabadas del kardex: despensa típica de una fonda de menú y
recetas base por plato, por porción. TODO es editable después desde el
admin — son un punto de partida para no arrancar de cero.

Costos referenciales en soles (Lima, mercado mayorista) por unidad del
insumo: sirven para ver márgenes desde el día uno; el costo real se
recalcula solo con cada compra registrada.
"""
import unicodedata

# (nombre, unidad, costo referencial S/ por unidad, stock mínimo sugerido)
INSUMOS_BASE: list[tuple[str, str, float, float]] = [
    # Base y granos
    ("Arroz", "kg", 4.0, 10),
    ("Papa blanca", "kg", 2.5, 10),
    ("Papa amarilla", "kg", 4.0, 5),
    ("Fideo tallarín", "kg", 5.5, 3),
    ("Fideo cabello de ángel", "kg", 5.5, 1),
    ("Frejol canario", "kg", 9.0, 3),
    ("Lenteja", "kg", 7.0, 2),
    ("Pan", "unidad", 0.3, 20),
    ("Harina", "kg", 4.5, 2),
    ("Pan rallado", "kg", 8.0, 1),
    ("Quinua", "kg", 12.0, 1),
    ("Trigo", "kg", 6.0, 1),
    ("Choclo", "unidad", 2.0, 5),
    ("Yuca", "kg", 3.0, 3),
    ("Olluco", "kg", 5.0, 2),
    # Proteínas
    ("Pollo entero", "kg", 9.5, 8),
    ("Pechuga de pollo", "kg", 14.0, 4),
    ("Carne de res (bistec)", "kg", 28.0, 4),
    ("Carne de res (guiso)", "kg", 22.0, 4),
    ("Mondongo", "kg", 12.0, 2),
    ("Pescado (filete)", "kg", 20.0, 3),
    ("Huevo", "unidad", 0.6, 30),
    ("Queso fresco", "kg", 22.0, 1),
    ("Leche evaporada", "l", 5.5, 3),
    # Verduras y aderezo
    ("Cebolla roja", "kg", 3.0, 5),
    ("Tomate", "kg", 4.0, 3),
    ("Ajo", "kg", 12.0, 1),
    ("Ají amarillo", "kg", 6.0, 2),
    ("Ají panca", "kg", 8.0, 1),
    ("Zanahoria", "kg", 2.5, 3),
    ("Arveja", "kg", 6.0, 2),
    ("Zapallo", "kg", 2.5, 3),
    ("Apio", "kg", 3.0, 1),
    ("Poro", "kg", 3.5, 1),
    ("Culantro", "kg", 8.0, 0.5),
    ("Perejil", "kg", 6.0, 0.5),
    ("Espinaca", "kg", 5.0, 1),
    ("Albahaca", "kg", 10.0, 0.5),
    ("Lechuga", "unidad", 2.0, 5),
    ("Limón", "kg", 5.0, 3),
    ("Camote", "kg", 2.5, 3),
    ("Palta", "kg", 8.0, 1),
    ("Aceituna", "kg", 14.0, 0.5),
    # Despensa
    ("Aceite", "l", 8.0, 5),
    ("Sal", "kg", 1.5, 2),
    ("Azúcar", "kg", 3.5, 3),
    ("Comino", "kg", 30.0, 0.2),
    ("Pimienta", "kg", 40.0, 0.2),
    ("Orégano", "kg", 30.0, 0.2),
    ("Sillao", "l", 7.0, 1),
    ("Vinagre", "l", 4.0, 1),
    ("Pasta de tomate", "kg", 9.0, 1),
    ("Mantequilla", "kg", 24.0, 0.5),
    ("Galleta de soda", "kg", 9.0, 0.5),
    ("Maní", "kg", 12.0, 0.5),
    # Bebidas y postres
    ("Maíz morado", "kg", 6.0, 3),
    ("Piña", "unidad", 4.0, 3),
    ("Manzana", "kg", 4.0, 2),
    ("Maracuyá", "kg", 5.0, 2),
    ("Canela y clavo", "kg", 40.0, 0.2),
    ("Chuño", "kg", 10.0, 0.5),
    ("Gelatina en polvo", "kg", 20.0, 0.5),
]

# Recetas base por porción: {plato: [(insumo, cantidad en la unidad del insumo)]}
# Los nombres de plato son "claves" que se buscan dentro del nombre real
# ("Seco de res con frejoles" encuentra "seco de res").
RECETAS_BASE: dict[str, list[tuple[str, float]]] = {
    # ---- Entradas y sopas ----
    "sopa criolla": [("Carne de res (guiso)", 0.06), ("Fideo cabello de ángel", 0.05),
                     ("Cebolla roja", 0.04), ("Tomate", 0.04), ("Ají panca", 0.01),
                     ("Huevo", 1), ("Leche evaporada", 0.05), ("Pan", 1), ("Aceite", 0.01),
                     ("Sal", 0.005)],
    "sopa de pollo": [("Pollo entero", 0.12), ("Fideo cabello de ángel", 0.04),
                      ("Papa blanca", 0.08), ("Zanahoria", 0.03), ("Apio", 0.01),
                      ("Poro", 0.01), ("Sal", 0.005)],
    "caldo de gallina": [("Pollo entero", 0.2), ("Fideo tallarín", 0.06), ("Papa blanca", 0.1),
                         ("Huevo", 1), ("Ajo", 0.005), ("Sal", 0.005)],
    "sopa a la minuta": [("Carne de res (guiso)", 0.06), ("Fideo cabello de ángel", 0.05),
                         ("Cebolla roja", 0.03), ("Tomate", 0.03), ("Leche evaporada", 0.05),
                         ("Huevo", 1), ("Orégano", 0.001), ("Sal", 0.005)],
    "chupe": [("Pescado (filete)", 0.08), ("Papa blanca", 0.1), ("Arroz", 0.03),
              ("Huevo", 1), ("Leche evaporada", 0.06), ("Queso fresco", 0.02),
              ("Ají panca", 0.01), ("Cebolla roja", 0.03), ("Sal", 0.005)],
    "menestrón": [("Carne de res (guiso)", 0.06), ("Fideo tallarín", 0.04), ("Papa blanca", 0.06),
                  ("Zapallo", 0.06), ("Frejol canario", 0.02), ("Albahaca", 0.005),
                  ("Espinaca", 0.02), ("Queso fresco", 0.01), ("Sal", 0.005)],
    "dieta de pollo": [("Pechuga de pollo", 0.1), ("Fideo cabello de ángel", 0.04),
                       ("Papa blanca", 0.08), ("Zanahoria", 0.03), ("Sal", 0.005)],
    "papa a la huancaína": [("Papa blanca", 0.2), ("Queso fresco", 0.04), ("Ají amarillo", 0.03),
                            ("Leche evaporada", 0.04), ("Galleta de soda", 0.01), ("Aceite", 0.01),
                            ("Huevo", 0.5), ("Aceituna", 0.01), ("Lechuga", 0.1)],
    "ocopa": [("Papa blanca", 0.2), ("Queso fresco", 0.03), ("Ají amarillo", 0.02),
              ("Maní", 0.02), ("Galleta de soda", 0.01), ("Leche evaporada", 0.04),
              ("Huevo", 0.5), ("Aceite", 0.01), ("Lechuga", 0.1)],
    "causa": [("Papa amarilla", 0.2), ("Ají amarillo", 0.02), ("Limón", 0.03),
              ("Pechuga de pollo", 0.05), ("Palta", 0.05), ("Huevo", 0.5),
              ("Aceituna", 0.01), ("Aceite", 0.01), ("Sal", 0.003)],
    "palta rellena": [("Palta", 0.15), ("Pechuga de pollo", 0.05), ("Zanahoria", 0.02),
                      ("Arveja", 0.02), ("Huevo", 0.5), ("Lechuga", 0.1)],
    "ensalada": [("Lechuga", 0.3), ("Tomate", 0.06), ("Cebolla roja", 0.02), ("Limón", 0.02),
                 ("Aceite", 0.01), ("Sal", 0.002)],
    "solterito": [("Choclo", 0.5), ("Queso fresco", 0.04), ("Cebolla roja", 0.03), ("Tomate", 0.04),
                  ("Arveja", 0.03), ("Aceituna", 0.01), ("Limón", 0.02), ("Sal", 0.002)],
    "ceviche": [("Pescado (filete)", 0.15), ("Limón", 0.12), ("Cebolla roja", 0.06),
                ("Ají amarillo", 0.01), ("Camote", 0.1), ("Choclo", 0.5), ("Culantro", 0.005),
                ("Sal", 0.003)],
    # ---- Segundos ----
    "lomo saltado": [("Carne de res (bistec)", 0.15), ("Papa blanca", 0.2), ("Cebolla roja", 0.08),
                     ("Tomate", 0.08), ("Ají amarillo", 0.01), ("Sillao", 0.02), ("Vinagre", 0.01),
                     ("Aceite", 0.04), ("Arroz", 0.1), ("Culantro", 0.003), ("Sal", 0.003)],
    "ají de gallina": [("Pechuga de pollo", 0.12), ("Ají amarillo", 0.04), ("Pan", 1),
                       ("Leche evaporada", 0.06), ("Queso fresco", 0.02), ("Cebolla roja", 0.05),
                       ("Ajo", 0.005), ("Papa blanca", 0.12), ("Huevo", 0.5), ("Aceituna", 0.01),
                       ("Arroz", 0.1), ("Aceite", 0.02), ("Sal", 0.003)],
    "seco de res": [("Carne de res (guiso)", 0.15), ("Culantro", 0.02), ("Cebolla roja", 0.05),
                    ("Ají amarillo", 0.02), ("Ajo", 0.005), ("Arveja", 0.03), ("Zanahoria", 0.03),
                    ("Papa blanca", 0.1), ("Frejol canario", 0.05), ("Arroz", 0.1),
                    ("Aceite", 0.02), ("Sal", 0.003)],
    "seco de pollo": [("Pollo entero", 0.2), ("Culantro", 0.02), ("Cebolla roja", 0.05),
                      ("Ají amarillo", 0.02), ("Ajo", 0.005), ("Arveja", 0.03), ("Zanahoria", 0.03),
                      ("Papa blanca", 0.1), ("Arroz", 0.1), ("Aceite", 0.02), ("Sal", 0.003)],
    "arroz con pollo": [("Pollo entero", 0.2), ("Arroz", 0.12), ("Culantro", 0.02),
                        ("Cebolla roja", 0.04), ("Ají amarillo", 0.02), ("Arveja", 0.03),
                        ("Zanahoria", 0.03), ("Choclo", 0.25), ("Aceite", 0.02), ("Sal", 0.003)],
    "arroz chaufa": [("Arroz", 0.15), ("Pollo entero", 0.1), ("Huevo", 1), ("Sillao", 0.03),
                     ("Cebolla roja", 0.03), ("Ajo", 0.003), ("Aceite", 0.03), ("Sal", 0.002)],
    "tallarín rojo": [("Fideo tallarín", 0.12), ("Pollo entero", 0.15), ("Tomate", 0.08),
                      ("Pasta de tomate", 0.02), ("Cebolla roja", 0.04), ("Ajo", 0.005),
                      ("Zanahoria", 0.02), ("Aceite", 0.02), ("Sal", 0.003)],
    "tallarín verde": [("Fideo tallarín", 0.12), ("Espinaca", 0.05), ("Albahaca", 0.02),
                       ("Queso fresco", 0.03), ("Leche evaporada", 0.04), ("Ajo", 0.005),
                       ("Aceite", 0.02), ("Carne de res (bistec)", 0.1), ("Sal", 0.003)],
    "tallarín saltado": [("Fideo tallarín", 0.12), ("Carne de res (bistec)", 0.1),
                         ("Cebolla roja", 0.06), ("Tomate", 0.06), ("Sillao", 0.02),
                         ("Ají amarillo", 0.01), ("Aceite", 0.03), ("Sal", 0.003)],
    "estofado de pollo": [("Pollo entero", 0.2), ("Papa blanca", 0.12), ("Zanahoria", 0.03),
                          ("Arveja", 0.03), ("Tomate", 0.04), ("Cebolla roja", 0.04),
                          ("Ají panca", 0.01), ("Arroz", 0.1), ("Aceite", 0.02), ("Sal", 0.003)],
    "pollo guisado": [("Pollo entero", 0.2), ("Papa blanca", 0.12), ("Zanahoria", 0.03),
                      ("Arveja", 0.03), ("Cebolla roja", 0.04), ("Ají panca", 0.01),
                      ("Arroz", 0.1), ("Aceite", 0.02), ("Sal", 0.003)],
    "bistec a lo pobre": [("Carne de res (bistec)", 0.15), ("Papa blanca", 0.2), ("Huevo", 1),
                          ("Arroz", 0.1), ("Aceite", 0.04), ("Sal", 0.003)],
    "bistec": [("Carne de res (bistec)", 0.15), ("Papa blanca", 0.15), ("Arroz", 0.1),
               ("Cebolla roja", 0.03), ("Tomate", 0.03), ("Aceite", 0.03), ("Sal", 0.003)],
    "milanesa": [("Pechuga de pollo", 0.15), ("Pan rallado", 0.03), ("Huevo", 0.5),
                 ("Papa blanca", 0.15), ("Arroz", 0.1), ("Aceite", 0.04), ("Sal", 0.003)],
    "apanado": [("Carne de res (bistec)", 0.13), ("Pan rallado", 0.03), ("Huevo", 0.5),
                ("Papa blanca", 0.15), ("Arroz", 0.1), ("Aceite", 0.04), ("Sal", 0.003)],
    "chicharrón de pollo": [("Pechuga de pollo", 0.15), ("Harina", 0.02), ("Ajo", 0.003),
                            ("Papa blanca", 0.15), ("Cebolla roja", 0.03), ("Limón", 0.02),
                            ("Aceite", 0.05), ("Sal", 0.003)],
    "pescado frito": [("Pescado (filete)", 0.18), ("Harina", 0.02), ("Papa blanca", 0.12),
                      ("Arroz", 0.1), ("Cebolla roja", 0.03), ("Limón", 0.02), ("Aceite", 0.05),
                      ("Sal", 0.003)],
    "sudado": [("Pescado (filete)", 0.18), ("Cebolla roja", 0.06), ("Tomate", 0.08),
               ("Ají amarillo", 0.02), ("Culantro", 0.005), ("Papa blanca", 0.1), ("Yuca", 0.08),
               ("Arroz", 0.1), ("Aceite", 0.01), ("Sal", 0.003)],
    "olluquito": [("Olluco", 0.15), ("Carne de res (guiso)", 0.08), ("Ají panca", 0.01),
                  ("Cebolla roja", 0.04), ("Ajo", 0.003), ("Perejil", 0.003), ("Arroz", 0.1),
                  ("Aceite", 0.02), ("Sal", 0.003)],
    "carapulcra": [("Papa blanca", 0.15), ("Carne de res (guiso)", 0.08), ("Pollo entero", 0.06),
                   ("Ají panca", 0.02), ("Maní", 0.02), ("Cebolla roja", 0.04), ("Ajo", 0.005),
                   ("Arroz", 0.1), ("Aceite", 0.02), ("Sal", 0.003)],
    "cau cau": [("Mondongo", 0.15), ("Papa blanca", 0.15), ("Ají amarillo", 0.02),
                ("Cebolla roja", 0.04), ("Arveja", 0.02), ("Perejil", 0.003), ("Arroz", 0.1),
                ("Aceite", 0.02), ("Sal", 0.003)],
    "pollo al horno": [("Pollo entero", 0.25), ("Papa blanca", 0.15), ("Ají panca", 0.01),
                       ("Ajo", 0.005), ("Arroz", 0.1), ("Aceite", 0.02), ("Sal", 0.003)],
    "frejoles": [("Frejol canario", 0.08), ("Arroz", 0.1), ("Cebolla roja", 0.03), ("Ajo", 0.003),
                 ("Aceite", 0.01), ("Sal", 0.003)],
    "lentejas": [("Lenteja", 0.08), ("Arroz", 0.1), ("Cebolla roja", 0.03), ("Ajo", 0.003),
                 ("Aceite", 0.01), ("Sal", 0.003)],
    "arroz a la cubana": [("Arroz", 0.12), ("Huevo", 1), ("Papa blanca", 0.1), ("Aceite", 0.03),
                          ("Sal", 0.002)],
    # ---- Refrescos y postres ----
    "chicha morada": [("Maíz morado", 0.05), ("Piña", 0.1), ("Manzana", 0.03), ("Azúcar", 0.03),
                      ("Limón", 0.01), ("Canela y clavo", 0.001)],
    "limonada": [("Limón", 0.06), ("Azúcar", 0.03)],
    "maracuyá": [("Maracuyá", 0.08), ("Azúcar", 0.03)],
    "emoliente": [("Trigo", 0.02), ("Limón", 0.01), ("Azúcar", 0.02)],
    "mazamorra morada": [("Maíz morado", 0.05), ("Chuño", 0.02), ("Azúcar", 0.04), ("Piña", 0.05),
                         ("Manzana", 0.03), ("Canela y clavo", 0.001), ("Limón", 0.01)],
    "arroz con leche": [("Arroz", 0.04), ("Leche evaporada", 0.08), ("Azúcar", 0.03),
                        ("Canela y clavo", 0.001)],
    "gelatina": [("Gelatina en polvo", 0.015), ("Azúcar", 0.01)],
    "flan": [("Huevo", 1), ("Leche evaporada", 0.06), ("Azúcar", 0.03)],
}


def normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())


def buscar_receta_base(nombre_plato: str) -> tuple[str, list[tuple[str, float]]] | None:
    """La clave más larga que aparezca dentro del nombre del plato.

    "Seco de res con frejoles" → "seco de res"; "Tallarín rojo con pollo"
    → "tallarín rojo"; "Bistec a lo pobre" gana sobre "bistec".
    """
    nombre = normalizar(nombre_plato)
    mejor: tuple[str, list[tuple[str, float]]] | None = None
    for clave, items in RECETAS_BASE.items():
        if normalizar(clave) in nombre and (mejor is None or len(clave) > len(mejor[0])):
            mejor = (clave, items)
    return mejor


def insumo_base(nombre: str) -> tuple[str, str, float, float] | None:
    objetivo = normalizar(nombre)
    for fila in INSUMOS_BASE:
        if normalizar(fila[0]) == objetivo:
            return fila
    return None
